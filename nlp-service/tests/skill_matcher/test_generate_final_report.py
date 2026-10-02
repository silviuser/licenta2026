# ruff: noqa: RUF001, RUF003, ANN401
# RUF001 / RUF003: literal markdown snippets used as parser inputs and
# explanatory comments use the same en-dashes / em-dashes the rendered
# report uses. ANN401: synthetic-fixture builders accept ``Any`` because
# they wrap values into ``Metric`` regardless of type.
"""Tests for ``scripts/generate_final_validation_report.py`` (Step 9).

Covers:
- The ``Metric`` dataclass and its ``__post_init__`` invariants.
- Markdown helpers (``_normalise``, ``find_section``, ``parse_pipe_table``,
  ``parse_bullet_kv``, ``parse_dash_kv``).
- The provenance walker.
- Section/appendix renderers on synthetic dicts.
- Byte-identical body across two consecutive runs (no embedded
  timestamps inside the report body).
- A ``@pytest.mark.slow`` end-to-end run that invokes ``main()`` against
  the real repo state and asserts the Step 8 macro F1 row resolves to
  0.504.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "generate_final_validation_report.py"

_spec = importlib.util.spec_from_file_location(
    "generate_final_validation_report", _SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
gfvr = importlib.util.module_from_spec(_spec)
sys.modules["generate_final_validation_report"] = gfvr
_spec.loader.exec_module(gfvr)


# ---------------------------------------------------------------------------
# Metric dataclass
# ---------------------------------------------------------------------------

class TestMetric:
    """``Metric.__post_init__`` invariants."""

    def test_construct_with_required_fields(self) -> None:
        m = gfvr.Metric(value=0.504, source_file="reports/x.json", source_section="best.macro_f1")
        assert m.value == pytest.approx(0.504)
        assert m.source_file == "reports/x.json"
        assert m.source_section == "best.macro_f1"

    def test_self_sentinel_is_accepted(self) -> None:
        m = gfvr.Metric(value="curated text", source_file="self", source_section="curated prose")
        assert m.source_file == "self"

    def test_empty_source_file_rejected(self) -> None:
        with pytest.raises(ValueError, match="source_file"):
            gfvr.Metric(value=1.0, source_file="", source_section="x")

    def test_empty_source_section_rejected(self) -> None:
        with pytest.raises(ValueError, match="source_section"):
            gfvr.Metric(value=1.0, source_file="reports/x.json", source_section="")

    def test_frozen(self) -> None:
        m = gfvr.Metric(value=1.0, source_file="self", source_section="x")
        with pytest.raises((AttributeError, Exception)):
            m.value = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_unifies_em_dashes(self) -> None:
        assert gfvr._normalise("a—b") == "a-b"
        assert gfvr._normalise("a–b") == "a-b"

    def test_strips_zero_width_chars(self) -> None:
        s = "a​b"
        assert gfvr._normalise(s) == "ab"


class TestFindSection:
    SAMPLE = """# Title

## 1. First section

body of first.

## 2. Second section

body of second.
"""

    def test_returns_body_of_matched_section(self) -> None:
        body = gfvr.find_section(self.SAMPLE, "1. First section")
        assert body is not None
        assert "body of first" in body
        assert "Second section" not in body

    def test_missing_section_returns_none(self) -> None:
        assert gfvr.find_section(self.SAMPLE, "999. Nope") is None


class TestParsePipeTable:
    def test_parses_simple_table(self) -> None:
        text = """\
| name | value |
|------|------:|
| a | 1 |
| b | 2 |
"""
        rows = gfvr.parse_pipe_table(text)
        assert rows == [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}]

    def test_skips_separator_row(self) -> None:
        text = """| col |
|-----|
| only |
"""
        rows = gfvr.parse_pipe_table(text)
        assert rows == [{"col": "only"}]

    def test_empty_section_returns_empty(self) -> None:
        assert gfvr.parse_pipe_table("no table here") == []


class TestParseDashKv:
    def test_bold_key_form(self) -> None:
        text = "- **alpha**: 123\n- **beta**: hello\n"
        out = gfvr.parse_dash_kv(text)
        assert out == {"alpha": "123", "beta": "hello"}

    def test_code_key_form(self) -> None:
        text = "- `module2_fp_catalogue`: 7\n- `random_in_corpus`: 199\n"
        out = gfvr.parse_dash_kv(text)
        assert out == {"module2_fp_catalogue": "7", "random_in_corpus": "199"}


class TestParseBulletKv:
    def test_star_form(self) -> None:
        text = "* **Mode:** full\n* **Encoder:** placeholder\n"
        out = gfvr.parse_bullet_kv(text)
        assert out == {"Mode": "full", "Encoder": "placeholder"}


class TestCoercion:
    def test_coerce_float_handles_comma(self) -> None:
        assert gfvr._coerce_float("1,234") == pytest.approx(1234.0)

    def test_coerce_float_handles_percent(self) -> None:
        assert gfvr._coerce_float("92.14%") == pytest.approx(92.14)

    def test_coerce_int_handles_thousands(self) -> None:
        assert gfvr._coerce_int("11 739") == 11739

    def test_coerce_int_returns_none_on_garbage(self) -> None:
        assert gfvr._coerce_int("not a number") is None


# ---------------------------------------------------------------------------
# Provenance walker
# ---------------------------------------------------------------------------

class TestVerifyProvenance:
    def test_valid_tree_returns_no_violations(self) -> None:
        tree = {
            "section_a": {
                "metric_1": {
                    "value": 0.5,
                    "source_file": "reports/x.json",
                    "source_section": "headline.macro_f1",
                },
                "nested": {
                    "metric_2": {
                        "value": "ok",
                        "source_file": "self",
                        "source_section": "curated",
                    },
                },
            },
        }
        assert gfvr.verify_provenance(tree) == []

    def test_missing_source_file_caught(self) -> None:
        tree = {
            "section_a": {
                "metric_1": {
                    "value": 0.5,
                    "source_file": "",
                    "source_section": "headline.macro_f1",
                },
            },
        }
        violations = gfvr.verify_provenance(tree)
        assert violations == ["section_a.metric_1"]

    def test_walks_into_lists(self) -> None:
        tree: dict[str, Any] = {
            "table": [
                {
                    "row_id": {
                        "value": 1,
                        "source_file": "reports/x.json",
                        "source_section": "rows[0]",
                    },
                    "row_name": {
                        "value": "bad",
                        "source_file": "",
                        "source_section": "rows[0].name",
                    },
                }
            ]
        }
        violations = gfvr.verify_provenance(tree)
        assert violations == ["table.0.row_name"]


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

class TestTryMetric:
    def test_renders_existing_metric(self) -> None:
        m = gfvr.Metric(value=0.123, source_file="self", source_section="x")
        assert gfvr.try_metric(m, "{:.3f}") == "0.123"

    def test_missing_metric_returns_placeholder(self) -> None:
        assert gfvr.try_metric(None) == "_not measured_"

    def test_fmt_pct_renders(self) -> None:
        m = gfvr.Metric(value=0.504, source_file="self", source_section="x")
        assert gfvr.fmt_pct(m, decimals=1) == "50.4%"

    def test_fmt_int_renders_thousands(self) -> None:
        m = gfvr.Metric(value=11739, source_file="self", source_section="x")
        assert gfvr.fmt_int(m) == "11,739"


# ---------------------------------------------------------------------------
# Confusion-matrix table renderer
# ---------------------------------------------------------------------------

class TestConfusionTable:
    def test_list_of_lists_form(self) -> None:
        matrix = [[8, 16, 11], [5, 45, 52], [4, 23, 116]]
        out = gfvr._confusion_table(matrix)
        assert "pred:strong" in out
        assert "gold:strong" in out
        assert "| 8 |" in out
        assert "| 116 |" in out

    def test_dict_form_with_gold_pred_keys(self) -> None:
        matrix = {
            "strong__strong": 8,
            "strong__possible": 16,
            "strong__no": 11,
            "possible__strong": 5,
            "possible__possible": 45,
            "possible__no": 52,
            "no__strong": 4,
            "no__possible": 23,
            "no__no": 116,
        }
        out = gfvr._confusion_table(matrix)
        assert "| 8 |" in out
        assert "| 116 |" in out

    def test_missing_data_is_handled(self) -> None:
        out = gfvr._confusion_table(None)
        assert "not available" in out


# ---------------------------------------------------------------------------
# Byte-identical body across two assemble_report calls
# ---------------------------------------------------------------------------

def _synthetic_sections() -> dict[str, Any]:
    """Build a minimal synthetic ``sections`` tree (every renderer gets data)."""

    def m(value: Any, sec: str = "synthetic") -> gfvr.Metric:
        return gfvr.Metric(value=value, source_file="self", source_section=sec)

    return {
        "section_01": {
            "macro_f1_locked": m(0.504),
            "plain_accuracy_locked": m(0.604),
            "weighted_accuracy_locked": m(0.494),
            "macro_f1_provisional_step7": m(0.225),
            "macro_f1_zero_shot_step4": m(0.151),
        },
        "section_03": {
            "training": {
                "n_input_pdfs": m(120),
                "n_surviving_cvs": m(120),
                "n_cvs_contributing_positives": m(119),
                "n_positives": m(3458),
                "n_hard_negatives": m(10374),
                "neg_to_pos_ratio": m(3.0),
                "n_train_cvs": m(95),
                "n_val_cvs": m(24),
                "n_train_pairs": m(11352),
                "n_val_pairs": m(2480),
                "language_en_count": m(3458),
            },
            "eval": {
                "n_cells": m(280),
                "n_cvs_total": m(15),
                "n_jds_total": m(20),
                "n_cvs_skipped": m(1),
                "skipped_cv_id": m("real_cv2"),
                "n_pairs_skipped": m(20),
            },
            "esco": {
                "concepts_total": m(14013),
                "concepts_knowledge": m(3219),
                "concepts_skill_competence": m(10435),
                "concepts_language": m(359),
                "concepts_custom": m(74),
                "esco_sha": m("bce83eb3ad4f"),
            },
        },
        "section_04": {
            "tests_pass": m(86),
            "tests_total": m(86),
            "coverage_pct": m(92.14),
            "real_cv_pass": m(5),
            "real_cv_total": m(6),
        },
        "section_05": {
            "tests_total": m(348),
            "coverage_pct": m(95.17),
            "macro_precision_labelled_8cv": m(0.968),
            "macro_recall_labelled_8cv": m(0.648),
            "macro_f1_labelled_8cv": m(0.766),
            "lexical_macro_f1_eval15": m(0.4603),
        },
        "section_06": {
            "encoder_model": m("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            "embedding_dim": m(384),
            "device": m("cpu"),
            "concept_text_format": m("bounded-a"),
            "window_size_tokens": m(30),
            "window_stride_tokens": m(15),
            "semantic_threshold_step4": m(0.55),
            "semantic_macro_f1": m(0.151),
            "semantic_macro_precision": m(0.157),
            "semantic_macro_recall": m(0.156),
            "lexical_macro_f1": m(0.460),
            "lexical_macro_precision": m(0.645),
            "lexical_macro_recall": m(0.371),
            "ensemble_macro_f1": m(0.346),
            "ensemble_macro_precision": m(0.303),
            "ensemble_macro_recall": m(0.437),
        },
        "section_07": {
            "round1_anchor": {
                "run_name": m("mnrl_v1_20260516_1610"),
                "zero_shot_f1": m(0.151),
                "fine_tuned_f1": m(0.144),
                "zero_shot_precision": m(0.157),
                "fine_tuned_precision": m(0.147),
                "zero_shot_recall": m(0.156),
                "fine_tuned_recall": m(0.156),
                "zero_shot_ensemble_f1": m(0.346),
                "fine_tuned_ensemble_f1": m(0.339),
            },
            "round1_t050": {
                "zero_shot_f1": m(0.146),
                "fine_tuned_f1": m(0.153),
            },
            "round2_sliding": {
                "run_name": m("mnrl_sw_v1_20260516_1953"),
                "zero_shot_f1": m(0.151),
                "fine_tuned_f1": m(0.121),
                "zero_shot_precision": m(0.157),
                "fine_tuned_precision": m(0.161),
                "zero_shot_recall": m(0.156),
                "fine_tuned_recall": m(0.100),
                "zero_shot_ensemble_f1": m(0.346),
                "fine_tuned_ensemble_f1": m(0.399),
            },
            "round2_t050": {},
            "diagnostic": {
                "alignment_verdict": m("aligned"),
                "coverage_ratio": m(0.2429),
                "overlap_uris": m(34),
            },
        },
        "section_08": {
            "lexical_macro_f1": m(0.460),
            "lexical_macro_precision": m(0.645),
            "lexical_macro_recall": m(0.371),
            "kept_macro_f1": m(0.297),
            "kept_macro_precision": m(0.704),
            "kept_macro_recall": m(0.202),
            "expansion_macro_f1": m(0.0),
            "expansion_macro_precision": m(0.929),
            "expansion_macro_recall": m(0.0),
            "kept_plus_expansion_macro_f1": m(0.296),
            "kept_plus_expansion_macro_precision": m(0.700),
            "kept_plus_expansion_macro_recall": m(0.202),
            "n_lexical_kept_total": m(110),
            "n_lexical_ambiguous_total": m(40),
            "n_lexical_dropped_total": m(120),
            "n_expansion_total": m(0),
            "lexical_dropped_fraction": m(0.44),
        },
        "section_09": {
            "macro_f1": m(0.225),
            "accuracy": m(0.511),
            "weighted_accuracy": m(0.333),
            "strong_precision": m(0.0),
            "strong_recall": m(0.0),
            "strong_f1": m(0.0),
            "possible_precision": m(0.0),
            "possible_recall": m(0.0),
            "possible_f1": m(0.0),
            "no_precision": m(0.511),
            "no_recall": m(1.0),
            "no_f1": m(0.676),
            "t1_provisional": m(0.55),
            "t2_provisional": m(0.25),
            "confusion": m([[0, 0, 35], [0, 0, 102], [0, 0, 143]]),
        },
        "section_10": {
            "locked_drop_threshold": m(0.4),
            "locked_keep_threshold": m(0.5),
            "locked_expansion_threshold": m(0.75),
            "locked_per_requirement_keep_threshold": m(0.085),
            "locked_required_weight": m(0.5),
            "locked_t1": m(0.06),
            "locked_t2": m(0.005),
            "macro_f1": m(0.504),
            "weighted_f1": m(0.583),
            "plain_accuracy": m(0.604),
            "weighted_accuracy": m(0.494),
            "f1_strong": m(0.308),
            "f1_possible": m(0.484),
            "f1_no": m(0.720),
            "precision_strong": m(0.471),
            "precision_possible": m(0.536),
            "precision_no": m(0.648),
            "recall_strong": m(0.229),
            "recall_possible": m(0.441),
            "recall_no": m(0.811),
            "confusion": m({
                "strong__strong": 8, "strong__possible": 16, "strong__no": 11,
                "possible__strong": 5, "possible__possible": 45, "possible__no": 52,
                "no__strong": 4, "no__possible": 23, "no__no": 116,
            }),
            "n_predicted_strong": m(17),
            "n_predicted_possible": m(84),
            "n_predicted_no": m(179),
            "n_combos_evaluated": m(928800),
            "n_gold_cells": m(300),
            "tier10_elapsed_seconds": m(2928.9),
            "tier2_elapsed_seconds": m(2918.7),
            "total_wall_clock_seconds": m(5847.6),
            "n_strict_passing": m(11739),
            "n_strict_total": m(928800),
        },
        "section_11": {},
        "section_12": {
            "top_disagreements": [],
            "walkthrough_examples": [],
        },
    }


def _synthetic_appendices() -> dict[str, Any]:
    def m(value: Any) -> gfvr.Metric:
        return gfvr.Metric(value=value, source_file="self", source_section="synthetic")
    return {
        "A": [{"date": m("2026-05-17"), "step": m("9"), "change": m("Step 9 closed.")}],
        "B": [],
        "C": [],
        "D_top10": [],
        "D_distribution": [],
    }


def test_assemble_report_byte_identical_across_runs() -> None:
    """Two consecutive assemble_report calls with same inputs produce equal bodies."""
    sections = _synthetic_sections()
    sections["section_11"] = sections["section_10"]
    appendices = _synthetic_appendices()
    fixed_ts = "2026-05-17T20:00:00Z"
    first = gfvr.assemble_report(
        sections=sections, appendices=appendices,
        integrity_notes=[], from_rerun=False,
        generated_at=fixed_ts, version_str="skill_matcher 0.7.0",
    )
    second = gfvr.assemble_report(
        sections=sections, appendices=appendices,
        integrity_notes=[], from_rerun=False,
        generated_at=fixed_ts, version_str="skill_matcher 0.7.0",
    )
    assert first == second


def test_assemble_report_contains_step8_macro_f1_and_caveat() -> None:
    sections = _synthetic_sections()
    sections["section_11"] = sections["section_10"]
    body = gfvr.assemble_report(
        sections=sections, appendices=_synthetic_appendices(),
        integrity_notes=[], from_rerun=False,
        generated_at="2026-05-17T20:00:00Z", version_str="skill_matcher 0.7.0",
    )
    # Section 1 headline.
    assert "0.504" in body
    # Placeholder caveat appears.
    assert "placeholder" in body.lower()
    # 16 sections + appendices A-F (F is data-integrity).
    assert "## 1. Executive summary" in body
    assert "## 16. Conclusion" in body
    assert "## Appendix A" in body
    assert "## Appendix E" in body
    assert "## Appendix F" in body


def test_assemble_report_long_enough_for_thesis_chapter() -> None:
    sections = _synthetic_sections()
    sections["section_11"] = sections["section_10"]
    body = gfvr.assemble_report(
        sections=sections, appendices=_synthetic_appendices(),
        integrity_notes=[], from_rerun=False,
        generated_at="2026-05-17T20:00:00Z", version_str="skill_matcher 0.7.0",
    )
    lines = body.count("\n") + 1
    assert lines >= 400, f"report only {lines} lines; expected >= 400"
    assert lines <= 5000, f"report {lines} lines exceeds upper bound 5000"


# ---------------------------------------------------------------------------
# Slow end-to-end against the real repo state
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_full_report_generation_end_to_end(tmp_path: Path) -> None:
    """Invoke ``main()`` and assert the rendered file contains 0.504."""
    out_md = tmp_path / "module3_final_validation_test.md"
    exit_code = gfvr.main(
        [
            "--out-report", str(out_md),
            "--no-figures",
        ]
    )
    assert exit_code == 0, f"main() returned {exit_code}"
    assert out_md.exists()
    body = out_md.read_text(encoding="utf-8")
    assert "0.504" in body, "Step 8 macro F1 lift not rendered"
    assert "Placeholder" in body or "placeholder" in body
    # JSON companion exists with same stem.
    out_json = out_md.with_suffix(".json")
    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "sections" in payload
    assert 
