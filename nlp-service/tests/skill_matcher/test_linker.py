"""Fast unit tests for :class:`skill_matcher.linker.Linker`.

Uses a hand-rolled ``_ControlledEncoder`` that maps each input string to
a caller-specified unit vector. Cosine similarity reduces to the dot
product (since both vectors are unit-norm), so tests can dial in any
similarity value by choosing vectors at known angles. Unknown texts
fall back to a zero vector (yielding similarity 0 against any other
unit vector) -- that lets each test focus on the strings it cares
about without enumerating every anchor or concept text upfront.

The real :class:`SentenceTransformerEncoder` is exercised by a slow
end-to-end test gated behind ``@pytest.mark.slow``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from skill_extractor.models import SkillExtractionResult, SkillMatch
from skill_matcher.config import SkillMatcherConfig
from skill_matcher.esco_loader import EscoConcept
from skill_matcher.linker import Linker, _section_evidence_text

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


_DIM = 4
"""Small embedding dimension keeps test vectors readable. 4D unit
sphere has enough room to pick distinct angles without precision
loss in float32."""


class _ControlledEncoder:
    """Encoder that returns caller-specified vectors for known strings.

    Unknown strings encode to the zero vector (cosine 0 against any
    unit vector). Vectors must already be L2-normalised by the
    test -- the helper does not normalise so tests stay explicit
    about what they configured.

    Attributes
    ----------
    model_name
        Carried so the Linker's pipeline_version string is stable.
    embedding_dim
        Mirrors :class:`Encoder` Protocol.
    vectors
        Mutable map; tests typically set entries in fixture setup.
    """

    def __init__(self, vectors: dict[str, NDArray[np.float32]] | None = None) -> None:
        self.embedding_dim = _DIM
        self.model_name = "controlled-test-encoder"
        self.vectors: dict[str, NDArray[np.float32]] = dict(vectors or {})

    def encode(
        self, texts: list[str], *, batch_size: int = 32
    ) -> NDArray[np.float32]:
        _ = batch_size
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        rows = [
            self.vectors.get(t, np.zeros(self.embedding_dim, dtype=np.float32))
            for t in texts
        ]
        return np.vstack(rows).astype(np.float32, copy=False)


class _StubIndex:
    """Duck-typed :class:`EscoIndex` substitute for fast tests.

    Linker only calls ``.query_batch(window_embeddings, top_k=...)``;
    the stub returns whatever the test pre-loaded into
    ``per_window_topk``. The Linker also reads no other attributes
    so we don't need to mock anything else.
    """

    def __init__(
        self,
        per_window_topk: list[list[tuple[str, float]]] | None = None,
    ) -> None:
        # If None, every window returns an empty hit list.
        self.per_window_topk: list[list[tuple[str, float]]] = (
            list(per_window_topk) if per_window_topk is not None else []
        )

    def query_batch(
        self,
        query_embeddings: NDArray[np.float32],
        top_k: int = 5,
    ) -> list[list[tuple[str, float]]]:
        _ = top_k
        n = int(query_embeddings.shape[0])
        if not self.per_window_topk:
            return [[] for _ in range(n)]
        # Cycle through the configured hits if fewer than n provided.
        return [
            self.per_window_topk[i % len(self.per_window_topk)]
            for i in range(n)
        ]


def _unit_vec(i: int, dim: int = _DIM) -> NDArray[np.float32]:
    """Return the ``i``-th standard basis vector (already L2-norm 1.0)."""
    v = np.zeros(dim, dtype=np.float32)
    v[i % dim] = 1.0
    return v


def _vec_at_angle(angle_deg: float) -> NDArray[np.float32]:
    """Return a 4D unit vector at ``angle_deg`` from ``_unit_vec(0)``.

    Lives in the (e0, e1) plane: ``(cos, sin, 0, 0)``. Useful for
    dialing in a target cosine similarity against the e0 reference.
    """
    rad = math.radians(angle_deg)
    return np.array([math.cos(rad), math.sin(rad), 0.0, 0.0], dtype=np.float32)


def _make_skill_match(
    *,
    uri: str = "esco:test/skill1",
    label: str = "Python",
    matched_text: str = "Python",
    spans: list[tuple[int, int]] | None = None,
    section: str = "skills",
    confidence: float = 0.8,
    frequency: int = 1,
) -> SkillMatch:
    """Construct a valid :class:`SkillMatch` with sensible defaults."""
    return SkillMatch(
        esco_uri=uri,
        preferred_label=label,
        matched_text=matched_text,
        skill_type="knowledge",
        spans=spans if spans is not None else [(10, 16)],
        section=section,
        frequency=frequency,
        confidence=confidence,
    )


def _make_extraction(
    skills: list[SkillMatch] | None = None,
    language: str = "en",
) -> SkillExtractionResult:
    skills = skills or []
    return SkillExtractionResult(
        language=language,
        skills=skills,
        skill_count=len(skills),
        processing_time_ms=1.0,
    )


def _make_concept(uri: str, label: str = "Python") -> EscoConcept:
    return EscoConcept(
        uri=uri,
        pref_label=label,
        alt_labels=(),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )


def _identity_concept_text(concept: EscoConcept) -> str:
    """Test-only concept-text builder: returns ``concept.uri`` verbatim.

    Sidesteps the real bounded-a formatter so the controlled-encoder
    lookup table can key directly on URIs.
    """
    return concept.uri


# ---------------------------------------------------------------------------
# Band assignment
# ---------------------------------------------------------------------------


def test_rescoring_band_assignment(default_config: SkillMatcherConfig) -> None:
    """Three Module 2 candidates land in three different bands.

    With keep_threshold=0.55 and drop_threshold=0.45 (defaults), pick
    target similarities 0.95 / 0.50 / 0.20 to land in
    kept / ambiguous / dropped respectively.
    """
    # Sim values we target:
    #   uri_kept:      sim ~= 0.95  -> kept (boosted)
    #   uri_ambig:     sim ~= 0.50  -> kept (demoted, ambiguous band)
    #   uri_dropped:   sim ~= 0.20  -> dropped
    #
    # Each uri's concept_text is the URI itself (via _identity_concept_text).
    # Each anchor's text is the ±50-char slice of CV text around the span.
    cv_text = "Profile: Python developer with strong backend chops."
    span = (cv_text.index("Python"), cv_text.index("Python") + len("Python"))
    # Same span re-used for all three matches; the anchor text is the
    # same for all three -> we can route similarity by varying the
    # CONCEPT vector while the ANCHOR vector is fixed to e0.
    anchor_text_kept = cv_text[max(0, span[0] - 50): min(len(cv_text), span[1] + 50)].strip()
    # All three matches use the same span so their anchors are identical.

    enc = _ControlledEncoder()
    enc.vectors[anchor_text_kept] = _unit_vec(0)
    enc.vectors["uri_kept"] = _vec_at_angle(math.degrees(math.acos(0.95)))
    enc.vectors["uri_ambig"] = _vec_at_angle(math.degrees(math.acos(0.50)))
    enc.vectors["uri_dropped"] = _vec_at_angle(math.degrees(math.acos(0.20)))

    concepts = {
        "uri_kept": _make_concept("uri_kept", "Kept"),
        "uri_ambig": _make_concept("uri_ambig", "Ambig"),
        "uri_dropped": _make_concept("uri_dropped", "Dropped"),
    }

    # Step 8 bumped keep_threshold from 0.55 -> 0.50 and drop from
    # 0.45 -> 0.40. The test's three target similarities (0.95 / 0.50 /
    # 0.20) were calibrated for the Step 4 bands, so pin them here to
    # keep the three-bucket semantics ("kept" / "ambiguous-kept" /
    # "dropped") regardless of future default movement.
    cfg = default_config.model_copy(
        update={"drop_threshold": 0.45, "keep_threshold": 0.55}
    )
    linker = Linker(
        config=cfg,
        encoder=enc,
        index=_StubIndex(),
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([
        _make_skill_match(uri="uri_kept", label="Kept", spans=[span]),
        _make_skill_match(uri="uri_ambig", label="Ambig", spans=[span]),
        _make_skill_match(uri="uri_dropped", label="Dropped", spans=[span]),
    ])

    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    # Three buckets observed.
    sources = {c.source for c in result.candidates}
    assert "lexical_kept" in sources
    assert "lexical_dropped" in sources

    # Headline counters.
    assert stats.n_lexical_kept == 2  # kept + ambiguous-kept
    assert stats.n_lexical_ambiguous == 1
    assert stats.n_lexical_dropped == 1
    assert stats.n_expansion == 0
    assert stats.n_unknown_uris == 0

    # Verify per-URI buckets.
    by_uri = {c.skill_uri: c for c in result.candidates}
    assert by_uri["uri_kept"].source == "lexical_kept"
    assert by_uri["uri_kept"].similarity_score == pytest.approx(0.95, abs=1e-5)
    assert by_uri["uri_ambig"].source == "lexical_kept"  # ambiguous = kept-with-demote
    assert by_uri["uri_ambig"].similarity_score == pytest.approx(0.50, abs=1e-5)
    assert by_uri["uri_dropped"].source == "lexical_dropped"
    assert by_uri["uri_dropped"].similarity_score == pytest.approx(0.20, abs=1e-5)


# ---------------------------------------------------------------------------
# Boost / demote math
# ---------------------------------------------------------------------------


def test_boost_formula(default_config: SkillMatcherConfig) -> None:
    """``_boost_confidence(0.8, 0.7) == 0.75`` exactly."""
    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    assert linker._boost_confidence(0.8, 0.7) == pytest.approx(0.75, abs=1e-12)


def test_boost_clamps_at_one(default_config: SkillMatcherConfig) -> None:
    """Boost saturates at 1.0 -- the confidence band is closed."""
    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    assert linker._boost_confidence(1.0, 1.0) == 1.0


def test_demote_formula(default_config: SkillMatcherConfig) -> None:
    """``_demote_confidence(0.8, 0.5)`` with keep=0.55 returns ~0.7272..."""
    # Step 8 bumped keep_threshold from 0.55 -> 0.50. The arithmetic
    # documented above assumes keep=0.55, so pin it via model_copy so
    # the test stays a formula-correctness check rather than a default-
    # value check.
    cfg = default_config.model_copy(update={"keep_threshold": 0.55})
    linker = Linker(
        config=cfg,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    expected = 0.8 * 0.5 / 0.55
    assert linker._demote_confidence(0.8, 0.5) == pytest.approx(expected, rel=1e-9)


def test_demote_continuity_at_keep_boundary(default_config: SkillMatcherConfig) -> None:
    """``sim == keep_threshold`` -> demote returns ``original`` exactly.

    Continuity at the band boundary -- no discontinuity between the
    "boosted" and "demoted" formulas as sim crosses the keep
    threshold.
    """
    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    keep = default_config.keep_threshold
    assert linker._demote_confidence(0.8, keep) == pytest.approx(0.8, abs=1e-12)


# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------


def test_expansion_emits_new_uri(default_config: SkillMatcherConfig) -> None:
    """A URI absent from Module 2 but firing above expansion_threshold
    appears as an expansion candidate.
    """
    cv_text = "Backend engineer skilled in containerisation and CI pipelines."

    enc = _ControlledEncoder()
    # Configure ONE specific window's text to retrieve a high-sim URI.
    # We don't know the exact sliding-window slicing -- but we can
    # control behaviour through the index stub directly. The encoder
    # outputs are irrelevant to a stubbed `query_batch`.
    concepts = {"esco:docker": _make_concept("esco:docker", "Docker")}

    stub_index = _StubIndex(per_window_topk=[
        [("esco:docker", 0.9)],
    ])

    linker = Linker(
        config=default_config,
        encoder=enc,
        index=stub_index,
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([])  # No Module 2 candidates.
    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    expansions = [c for c in result.candidates if c.source == "expansion"]
    assert len(expansions) == 1
    assert expansions[0].skill_uri == "esco:docker"
    assert expansions[0].similarity_score == pytest.approx(0.9, abs=1e-5)
    assert expansions[0].confidence == pytest.approx(0.9, abs=1e-5)
    assert expansions[0].lexical_confidence is None
    assert stats.n_expansion == 1


def test_expansion_dedup_against_lexical_kept(default_config: SkillMatcherConfig) -> None:
    """A URI Module 2 returned (even as dropped) MUST NOT also be emitted as expansion."""
    cv_text = "Some CV text with a Python mention here."
    span = (cv_text.index("Python"), cv_text.index("Python") + len("Python"))

    enc = _ControlledEncoder()
    anchor = cv_text[max(0, span[0] - 50): min(len(cv_text), span[1] + 50)].strip()
    enc.vectors[anchor] = _unit_vec(0)
    # Drive Module 2's URI into the lexical_dropped bucket (sim ~= 0.0).
    enc.vectors["esco:python"] = _unit_vec(1)  # orthogonal => sim 0.0

    concepts = {"esco:python": _make_concept("esco:python", "Python")}
    # Even though the stub index would return python with sim 1.0, the
    # Linker must dedup -- python was in Module 2's input set.
    stub_index = _StubIndex(per_window_topk=[
        [("esco:python", 1.0)],
    ])

    linker = Linker(
        config=default_config,
        encoder=enc,
        index=stub_index,
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([
        _make_skill_match(uri="esco:python", label="Python", spans=[span], confidence=0.9),
    ])
    result, _ = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    expansions = [c for c in result.candidates if c.source == "expansion"]
    assert expansions == []
    # And confirm the Module 2 candidate is still present (as dropped).
    dropped = [c for c in result.candidates if c.source == "lexical_dropped"]
    assert len(dropped) == 1
    assert dropped[0].skill_uri == "esco:python"


def test_expansion_threshold_filters_low_sim(default_config: SkillMatcherConfig) -> None:
    """A URI with similarity below ``expansion_threshold`` is NOT emitted."""
    cv_text = "Some other content here."
    concepts = {"esco:rare": _make_concept("esco:rare", "Rare")}
    stub_index = _StubIndex(per_window_topk=[
        # Below the default expansion_threshold (0.75).
        [("esco:rare", 0.70)],
    ])

    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=stub_index,
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=_make_extraction([]))
    assert all(c.source != "expansion" for c in result.candidates)
    assert stats.n_expansion == 0


def test_expansion_disabled(default_config: SkillMatcherConfig) -> None:
    """``enable_expansion=False`` -> no expansion candidates, no windows generated."""
    cv_text = "Some CV text with a Python mention here."
    cfg = default_config.model_copy(update={"enable_expansion": False})

    stub_index = _StubIndex(per_window_topk=[
        [("esco:docker", 0.99)],
    ])
    concepts = {"esco:docker": _make_concept("esco:docker", "Docker")}

    linker = Linker(
        config=cfg,
        encoder=_ControlledEncoder(),
        index=stub_index,
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=_make_extraction([]))
    assert all(c.source != "expansion" for c in result.candidates)
    assert stats.n_expansion == 0
    assert stats.n_windows == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_byte_identical_json(default_config: SkillMatcherConfig) -> None:
    """Two calls with identical inputs produce byte-identical model_dump_json."""
    cv_text = "Profile: Python developer with strong backend chops."
    span = (cv_text.index("Python"), cv_text.index("Python") + len("Python"))
    anchor = cv_text[max(0, span[0] - 50): min(len(cv_text), span[1] + 50)].strip()

    enc = _ControlledEncoder()
    enc.vectors[anchor] = _unit_vec(0)
    enc.vectors["esco:py"] = _vec_at_angle(math.degrees(math.acos(0.80)))

    concepts = {"esco:py": _make_concept("esco:py", "Python")}
    linker = Linker(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([
        _make_skill_match(uri="esco:py", label="Python", spans=[span], confidence=0.8),
    ])

    r1, _ = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)
    r2, _ = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    # Strip the timestamp-free fields and compare full JSON.
    assert r1.model_dump_json() == r2.model_dump_json()


# ---------------------------------------------------------------------------
# Empty / edge inputs
# ---------------------------------------------------------------------------


def test_empty_inputs(default_config: SkillMatcherConfig) -> None:
    """Empty CV text + no lexical candidates -> empty result, no errors."""
    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    result, stats = linker.link(cv_id="cv1", cv_text="", lexical=_make_extraction([]))
    assert result.candidates == []
    assert stats.n_lexical_kept == 0
    assert stats.n_lexical_ambiguous == 0
    assert stats.n_lexical_dropped == 0
    assert stats.n_expansion == 0
    assert stats.n_windows == 0
    assert stats.n_unknown_uris == 0


def test_unknown_uri_silent_skip(default_config: SkillMatcherConfig) -> None:
    """Module 2 returns a URI absent from concepts_by_uri -> skipped + counted."""
    cv_text = "Python developer."
    extraction = _make_extraction([
        _make_skill_match(uri="esco:unknown_uri", spans=[(0, 6)]),
    ])

    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},  # empty -> every URI is unknown
        concept_text_builder=_identity_concept_text,
    )

    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)
    # No candidates emitted for the unknown URI.
    assert all(c.skill_uri != "esco:unknown_uri" for c in result.candidates)
    assert stats.n_unknown_uris == 1


# ---------------------------------------------------------------------------
# One MatchCandidate per (uri, span)
# ---------------------------------------------------------------------------


def test_one_candidate_per_uri_span_pair(default_config: SkillMatcherConfig) -> None:
    """A SkillMatch with N spans produces N MatchCandidates (Q4 default = R1a)."""
    cv_text = "Python here. More Python over there. And Python once more."
    spans = []
    start = 0
    while True:
        idx = cv_text.find("Python", start)
        if idx == -1:
            break
        spans.append((idx, idx + len("Python")))
        start = idx + 1
    assert len(spans) == 3

    enc = _ControlledEncoder()
    for span in spans:
        anchor = cv_text[max(0, span[0] - 50): min(len(cv_text), span[1] + 50)].strip()
        enc.vectors[anchor] = _unit_vec(0)
    enc.vectors["esco:py"] = _unit_vec(0)  # perfect match -> kept band for all 3

    concepts = {"esco:py": _make_concept("esco:py", "Python")}
    linker = Linker(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([
        _make_skill_match(uri="esco:py", label="Python", spans=spans, frequency=3),
    ])
    result, stats = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    per_uri = [c for c in result.candidates if c.skill_uri == "esco:py"]
    assert len(per_uri) == 3
    assert {c.cv_evidence_offset for c in per_uri} == set(spans)
    assert stats.n_lexical_kept == 3


# ---------------------------------------------------------------------------
# Sort stability
# ---------------------------------------------------------------------------


def test_sort_stability_on_tied_confidence(default_config: SkillMatcherConfig) -> None:
    """Two candidates with identical confidence sort lexicographically by URI."""
    cv_text = "Skills: Python and Java."
    span_py = (cv_text.index("Python"), cv_text.index("Python") + len("Python"))
    span_jv = (cv_text.index("Java"), cv_text.index("Java") + len("Java"))

    enc = _ControlledEncoder()
    anchor_py = cv_text[max(0, span_py[0] - 50): min(len(cv_text), span_py[1] + 50)].strip()
    anchor_jv = cv_text[max(0, span_jv[0] - 50): min(len(cv_text), span_jv[1] + 50)].strip()
    enc.vectors[anchor_py] = _unit_vec(0)
    enc.vectors[anchor_jv] = _unit_vec(0)
    enc.vectors["aaa:python"] = _unit_vec(0)
    enc.vectors["bbb:java"] = _unit_vec(0)

    concepts = {
        "aaa:python": _make_concept("aaa:python", "Python"),
        "bbb:java": _make_concept("bbb:java", "Java"),
    }

    linker = Linker(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
    )

    extraction = _make_extraction([
        _make_skill_match(uri="bbb:java", label="Java", spans=[span_jv], confidence=0.9),
        _make_skill_match(uri="aaa:python", label="Python", spans=[span_py], confidence=0.9),
    ])
    result, _ = linker.link(cv_id="cv1", cv_text=cv_text, lexical=extraction)

    kept = [c for c in result.candidates if c.source == "lexical_kept"]
    # Same boosted confidence (both at sim=1.0, orig=0.9) -> URIs sort alphabetically.
    assert [c.skill_uri for c in kept] == ["aaa:python", "bbb:java"]


# ---------------------------------------------------------------------------
# Construction-time validation
# ---------------------------------------------------------------------------


def test_threshold_band_ordering_enforced(default_config: SkillMatcherConfig) -> None:
    """drop > keep raises at construction time -- fail loud, not silently."""
    bad = default_config.model_copy(update={"drop_threshold": 0.9, "keep_threshold": 0.5})
    with pytest.raises(ValueError, match="Threshold band ordering"):
        Linker(
            config=bad,
            encoder=_ControlledEncoder(),
            index=_StubIndex(),
            concepts_by_uri={},
        )


# ---------------------------------------------------------------------------
# Pipeline-version stamping
# ---------------------------------------------------------------------------


def test_pipeline_version_carries_encoder_name(default_config: SkillMatcherConfig) -> None:
    """The result's pipeline_version includes encoder identity."""
    linker = Linker(
        config=default_config,
        encoder=_ControlledEncoder(),
        index=_StubIndex(),
        concepts_by_uri={},
    )
    result, _ = linker.link(cv_id="cv1", cv_text="x", lexical=_make_extraction([]))
    assert "skill_matcher@" in result.pipeline_version
    assert "controlled-test-encoder" in result.pipeline_version


# ---------------------------------------------------------------------------
# Slow / real-encoder end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_linker_e2e_on_real_cv1() -> None:
    """End-to-end run on real_cv1 with the production encoder + index.

    Asserts only that the result is structurally well-formed -- not
    that F1 beats lexical, per the Step 6 brief (correctness gate, not
    metrics gate).
    """
    from cv_extractor.pipeline import ExtractionPipeline
    from skill_extractor.pipeline import SkillExtractor
    from skill_matcher.pipeline import SkillMatcher

    pdf_path = Path("tests/fixtures/real_cv1.pdf")
    if not pdf_path.exists():
        pytest.skip(f"fixture {pdf_path} missing")

    extraction = ExtractionPipeline().process(pdf_path)
    lexical = SkillExtractor().extract(extraction)

    matcher = SkillMatcher()
    result = matcher.link(
        cv_id="real_cv1",
        cv_text=extraction.text,
        lexical=lexical,
    )

    # Structural assertions only.
    assert result.cv_id == "real_cv1"
    assert isinstance(result.candidates, list)
    # At least lexical buckets should be observed; expansion is allowed
    # to be empty (encoder is placeholder).
    sources = {c.source for c in result.candidates}
    assert sources.issubset({"lexical_kept", "lexical_dropped", "expansion"})


# ---------------------------------------------------------------------------
# _section_evidence_text — section tag is appended only when informative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("matched_text", "section", "expected"),
    [
        # Informative sections are appended verbatim.
        ("microservices", "skills", "microservices (skills)"),
        ("English", "experience", "English (experience)"),
        ("SQL", "education", "SQL (education)"),
        # Non-informative sentinels are omitted entirely.
        ("microservices", "other", "microservices"),
        ("microservices", "unknown", "microservices"),
        ("microservices", "Other", "microservices"),  # case-insensitive
        ("microservices", "UNKNOWN", "microservices"),
        ("microservices", "", "microservices"),  # blank section
    ],
)
def test_section_evidence_text_omits_sentinel_sections(
    matched_text: str, section: str, expected: str
) -> None:
    assert _section_evidence_text(matched_text, section) == expected
