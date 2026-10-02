"""Unit tests for :mod:`skill_extractor.esco.cache`.

These tests do not import spaCy; they exercise the hashing and on-disk
pickle round-trip in isolation. The matcher tests cover the spaCy-side
integration separately.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from skill_extractor.esco.cache import (
    MatcherCachePayload,
    MatcherDiskCache,
    MatchMeta,
    compute_esco_hash,
)
from skill_extractor.exceptions import MatcherCacheError

# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


class TestComputeEscoHash:
    def test_deterministic_same_inputs(self, tmp_path: Path) -> None:
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text("hello", encoding="utf-8")
        b.write_text("world", encoding="utf-8")
        h1 = compute_esco_hash(a, b)
        h2 = compute_esco_hash(a, b)
        assert h1 == h2
        assert len(h1) == 12

    def test_changes_when_content_changes(self, tmp_path: Path) -> None:
        a = tmp_path / "a.csv"
        a.write_text("hello", encoding="utf-8")
        h1 = compute_esco_hash(a)
        a.write_text("hello!", encoding="utf-8")
        h2 = compute_esco_hash(a)
        assert h1 != h2

    def test_order_independent(self, tmp_path: Path) -> None:
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text("alpha", encoding="utf-8")
        b.write_text("beta", encoding="utf-8")
        assert compute_esco_hash(a, b) == compute_esco_hash(b, a)

    def test_missing_file_silently_skipped(self, tmp_path: Path) -> None:
        a = tmp_path / "exists.csv"
        a.write_text("data", encoding="utf-8")
        missing = tmp_path / "absent.csv"
        # Hash with both should equal hash with just the existing one.
        assert compute_esco_hash(a, missing) == compute_esco_hash(a)


# ---------------------------------------------------------------------------
# MatcherDiskCache fixtures
# ---------------------------------------------------------------------------


def _sample_payload(
    esco_hash: str = "abcdef123456",
    language: str = "en",
) -> MatcherCachePayload:
    """A minimal-but-complete payload for round-trip tests."""
    return MatcherCachePayload(
        esco_hash=esco_hash,
        language=language,
        spacy_model="en_core_web_sm",
        phrase_attr="LOWER",
        docbin_bytes=b"\x00\x01\x02",
        pattern_names=["uri:python|preferred", "uri:python|alt"],
        label_map={
            "uri:python|preferred": MatchMeta(
                concept_uri="uri:python",
                preferred_label="Python",
                label_kind="preferred",
                skill_type="knowledge",
                surfaces={"python"},
            ),
            "uri:python|alt": MatchMeta(
                concept_uri="uri:python",
                preferred_label="Python",
                label_kind="alt",
                skill_type="knowledge",
                surfaces={"py", "python3"},
            ),
        },
    )


@pytest.fixture
def disk_cache(tmp_path: Path) -> MatcherDiskCache:
    return MatcherDiskCache(
        cache_dir=tmp_path / "cache",
        filename_template="phrasematcher_{lang}_{esco_hash}.pkl",
    )


# ---------------------------------------------------------------------------
# MatcherDiskCache behaviour
# ---------------------------------------------------------------------------


class TestMatcherDiskCache:
    def test_path_for_uses_template(self, disk_cache: MatcherDiskCache) -> None:
        path = disk_cache.path_for(lang="en", esco_hash="abc12345")
        assert path.name == "phrasematcher_en_abc12345.pkl"

    def test_save_creates_dir_and_file(
        self, disk_cache: MatcherDiskCache
    ) -> None:
        payload = _sample_payload()
        disk_cache.save(payload)
        # Lang derived from spacy_model 'en_core_web_sm' → 'en'.
        path = disk_cache.path_for(lang="en", esco_hash=payload.esco_hash)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_round_trip(self, disk_cache: MatcherDiskCache) -> None:
        original = _sample_payload()
        disk_cache.save(original)
        restored = disk_cache.load(lang="en", esco_hash=original.esco_hash)
        assert restored is not None
        assert restored.esco_hash == original.esco_hash
        assert restored.spacy_model == original.spacy_model
        assert restored.phrase_attr == original.phrase_attr
        assert restored.pattern_names == original.pattern_names
        assert restored.label_map == original.label_map

    def test_load_missing_returns_none(
        self, disk_cache: MatcherDiskCache
    ) -> None:
        assert (
            disk_cache.load(lang="en", esco_hash="nonexistent000")
            is None
        )

    def test_load_corrupted_returns_none(
        self, disk_cache: MatcherDiskCache, tmp_path: Path
    ) -> None:
        path = disk_cache.path_for(lang="en", esco_hash="badfile12345")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"this is not a pickle")
        assert (
            disk_cache.load(lang="en", esco_hash="badfile12345") is None
        )

    def test_load_unexpected_type_returns_none(
        self, disk_cache: MatcherDiskCache
    ) -> None:
        path = disk_cache.path_for(lang="en", esco_hash="wrongtype000")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fp:
            pickle.dump({"not": "a payload"}, fp)
        assert (
            disk_cache.load(lang="en", esco_hash="wrongtype000") is None
        )

    def test_load_hash_mismatch_returns_none(
        self, disk_cache: MatcherDiskCache
    ) -> None:
        """A payload whose internal ``esco_hash`` disagrees with the
        filename hash is rejected (defensive against tampering)."""
        # Save under one hash but with a payload claiming a different one.
        bad = _sample_payload(esco_hash="claimed00000")
        # Manually pickle to the path corresponding to *another* hash.
        target = disk_cache.path_for(lang="en", esco_hash="filename00000")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fp:
            pickle.dump(bad, fp)
        assert (
            disk_cache.load(lang="en", esco_hash="filename00000") is None
        )

    def test_save_failure_raises_matchercacheerror(
        self, tmp_path: Path
    ) -> None:
        """If the cache_dir path is unwritable (a file blocking the
        directory creation), save raises ``MatcherCacheError``."""
        # Create a *file* where the cache dir should go.
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file", encoding="utf-8")
        cache = MatcherDiskCache(
            cache_dir=blocker,  # path is a file, mkdir will fail
            filename_template="m_{lang}_{esco_hash}.pkl",
        )
        with pytest.raises(MatcherCacheError):
            cache.save(_sample_payload())
