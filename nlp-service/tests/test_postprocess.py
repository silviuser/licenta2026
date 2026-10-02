"""Unit tests for postprocess.py — all pure-function tests, no I/O."""

import pytest

from cv_extractor.config import ExtractorConfig
from cv_extractor.postprocess import QualityChecker, postprocess_text


class TestPostprocessText:
    """Tests for the postprocess_text() pure function."""

    def test_empty_string_returns_empty(self) -> None:
        assert postprocess_text("") == ""

    def test_expands_fi_ligature(self) -> None:
        assert postprocess_text("proﬁle") == "profile"

    def test_expands_fl_ligature(self) -> None:
        assert postprocess_text("reﬂect") == "reflect"

    def test_expands_ff_ligature(self) -> None:
        assert postprocess_text("oﬀice") == "office"

    def test_expands_ffi_ligature(self) -> None:
        assert postprocess_text("eﬃcient") == "efficient"

    def test_collapses_multiple_spaces(self) -> None:
        result = postprocess_text("hello   world")
        assert result == "hello world"

    def test_collapses_tabs(self) -> None:
        result = postprocess_text("hello\t\tworld")
        assert result == "hello world"

    def test_normalises_windows_line_endings(self) -> None:
        result = postprocess_text("line one\r\nline two")
        assert "\r" not in result
        assert "line one\nline two" == result

    def test_collapses_excess_blank_lines(self) -> None:
        result = postprocess_text("para one\n\n\n\n\npara two")
        assert result == "para one\n\npara two"

    def test_preserves_double_newline_paragraph_breaks(self) -> None:
        text = "Section A\n\nSection B"
        result = postprocess_text(text)
        assert "\n\n" in result

    def test_removes_non_printable_characters(self) -> None:
        # ASCII control characters (except \t \n \r) should be stripped
        result = postprocess_text("hello\x01\x02world")
        assert result == "helloworld"

    def test_preserves_romanian_diacritics(self) -> None:
        text = "experiență educație abilități"
        result = postprocess_text(text)
        assert result == text

    def test_preserves_unicode_letters(self) -> None:
        text = "Ș ș Ț ț Ă ă Â â Î î"
        result = postprocess_text(text)
        assert "ș" in result
        assert "ț" in result

    def test_strips_leading_trailing_whitespace(self) -> None:
        result = postprocess_text("  hello world  ")
        assert result == "hello world"

    def test_non_breaking_space_normalised_to_space(self) -> None:
        result = postprocess_text("hello\xa0world")
        assert result == "hello world"

    def test_ocr_rn_to_m_applied_when_flag_set(self) -> None:
        # "rnarket" should become "market" with OCR correction
        result = postprocess_text("rnarket analysis", was_ocr=True)
        assert "market" in result

    def test_ocr_rn_correction_not_applied_by_default(self) -> None:
        # Without was_ocr=True the substitution must NOT happen
        result = postprocess_text("environment")
        assert "environment" in result  # "rn" in "environment" should stay

    # ---------------------------------------------------------------
    # Regression tests for fixes applied 2026-05-02
    # ---------------------------------------------------------------

    def test_regression_rn_to_m_does_not_corrupt_midword_rn(self) -> None:
        """The fix must NOT replace mid-word "rn" — those are usually genuine
        ("environment", "earn", "warn", "cornputer" is ambiguous but unlikely
        to be a real OCR error on a real CV).
        """
        for word in ("environment", "earn", "warn", "burn", "modern"):
            result = postprocess_text(word, was_ocr=True)
            assert word in result, f"{word!r} should be preserved, got {result!r}"

    def test_regression_rn_to_m_handles_word_initial_rn(self) -> None:
        """The fix MUST replace word-initial "rn" — that is what the rule was
        designed for and what a non-fixed regex was failing to match.
        """
        result = postprocess_text("rnarket and rnoney", was_ocr=True)
        assert "market" in result
        assert "money" in result


class TestQualityChecker:
    """Tests for QualityChecker."""

    @pytest.fixture
    def checker(self) -> QualityChecker:
        config = ExtractorConfig(
            min_chars_per_page=50,
            min_quality_score=0.5,
            cv_keyword_min_matches=2,
        )
        return QualityChecker(config)

    def test_empty_text_scores_zero(self, checker: QualityChecker) -> None:
        assert checker.score("") == 0.0

    def test_high_quality_cv_text_scores_above_threshold(self, checker: QualityChecker) -> None:
        text = (
            "John Doe\n\nExperience\n5 years as Software Engineer at ACME\n\n"
            "Education\nB.Sc. Computer Science\n\nSkills\nPython, Java, SQL\n\n"
            "Languages\nEnglish, Romanian\n\nContact\njohn@example.com"
        )
        score = checker.score(text, total_pages=1)
        assert score >= 0.5

    def test_garbage_text_scores_low(self, checker: QualityChecker) -> None:
        # High ratio of non-alphabetic characters
        text = "123 456 789 !!! ### $$$ %%% ^^^ &&&"
        score = checker.score(text, total_pages=1)
        assert score < 0.5

    def test_is_sufficient_returns_true_for_good_text(self, checker: QualityChecker) -> None:
        text = "Experience Education Skills Python Java contact languages projects"
        assert checker.is_sufficient(text, total_pages=1)

    def test_is_sufficient_returns_false_for_short_text(self, checker: QualityChecker) -> None:
        assert not checker.is_sufficient("hi", total_pages=1)

    def test_is_likely_cv_returns_true_for_cv_keywords(self, checker: QualityChecker) -> None:
        text = "Experience at ACME Corp. Education at University. Skills: Python."
        assert checker.is_likely_cv(text)

    def test_is_likely_cv_returns_false_for_non_cv(self, checker: QualityChecker) -> None:
        text = "Recipe for chocolate cake: mix flour, sugar, cocoa powder."
        assert not checker.is_likely_cv(text)

    def test_is_likely_cv_works_with_romanian_keywords(self, checker: QualityChecker) -> None:
        text = "Experiență de muncă la firma Acme. Educație la universitate. Competențe Python."
        assert checker.is_likely_cv(text)

    def test_score_respects_page_count_in_length_signal(self, checker: QualityChecker) -> None:
        # Short text relative to 10 pages should score lower than relative to 1 page
        short_text = "a" * 60  # barely above single-page threshold
        score_1_page = checker.score(short_text, total_pages=1)
        score_10_pages = checker.score(short_text, total_pages=10)
        assert score_1_page > score_10_pages

    def test_alpha_ratio_signal(self, checker: QualityChecker) -> None:
        all_alpha = "abcdefghijklmnopqrstuvwxyz" * 5
        mostly_numbers = "1234567890" * 10 + "abc"
        assert checker.score(all_alpha) > checker.score(mostly_numbers)

    # ---------------------------------------------------------------
    # Regression tests for the multiplicative-length-gate fix
    # ---------------------------------------------------------------

    def test_regression_single_char_text_scores_below_fallback_threshold(self) -> None:
        """A 1-char extraction like "x" must score below any reasonable
        fallback threshold so the pipeline proceeds to the next extractor.

        Previously an additive formula floored the score at ~0.4 (alpha_ratio
        weight), letting garbage pass a 0.3 threshold.
        """
        config = ExtractorConfig(min_chars_per_page=100)
        checker = QualityChecker(config)
        score = checker.score("x", total_pages=1)
        assert score < 0.05, f"expected near-zero score for 'x', got {score}"

    def test_regression_short_high_alpha_text_does_not_pass(self) -> None:
        """High alpha-ratio short text should still fail the quality gate."""
        config = ExtractorConfig(min_chars_per_page=100, min_quality_score=0.3)
        checker = QualityChecker(config)
        # 5 chars of pure letters with no keywords — should NOT be sufficient
        # against a 100-chars-per-page expectation.
        assert not checker.is_sufficient("hello", total_pages=1)
