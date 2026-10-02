"""Unit tests for multi-column layout detection in utils/layout.py."""

import pytest

from cv_extractor.utils.layout import ColumnBoundary, detect_columns, split_page_at_boundary


class TestDetectColumns:
    """Tests for detect_columns()."""

    def test_single_column_returns_none(self) -> None:
        # All words on the left half — no gap
        x_coords = [float(i * 5) for i in range(20)]  # 0, 5, 10, ..., 95
        result = detect_columns(x_coords, page_width=595.0)
        assert result is None

    def test_two_column_layout_detected(self) -> None:
        # Words cluster around x=50 and x=350, clear gap between 150–300
        left = [50.0 + i for i in range(15)]
        right = [350.0 + i for i in range(15)]
        result = detect_columns(left + right, page_width=595.0, column_gap_ratio=0.1)
        assert result is not None
        assert isinstance(result, ColumnBoundary)

    def test_gap_falls_within_central_zone(self) -> None:
        left = [50.0] * 15
        right = [350.0] * 15
        result = detect_columns(left + right, page_width=595.0, column_gap_ratio=0.1)
        assert result is not None
        # Gap must be in the 20–80% zone
        assert result.gap_start_x > 595.0 * 0.1
        assert result.gap_end_x < 595.0 * 0.9

    def test_too_few_words_returns_none(self) -> None:
        x_coords = [50.0, 350.0]  # Only 2 words
        result = detect_columns(x_coords, page_width=595.0, min_words=10)
        assert result is None

    def test_empty_coords_returns_none(self) -> None:
        assert detect_columns([], page_width=595.0) is None

    def test_zero_page_width_returns_none(self) -> None:
        x_coords = [50.0] * 20
        assert detect_columns(x_coords, page_width=0.0) is None

    def test_gap_too_narrow_returns_none(self) -> None:
        # Words spread uniformly — no significant gap
        x_coords = [float(i * 30) for i in range(20)]  # evenly distributed
        result = detect_columns(x_coords, page_width=595.0, column_gap_ratio=0.3)
        assert result is None

    def test_three_column_layout_returns_none(self) -> None:
        # Three clusters — ambiguous, should not guess
        left = [40.0] * 10
        mid = [240.0] * 10
        right = [440.0] * 10
        result = detect_columns(left + mid + right, page_width=595.0, column_gap_ratio=0.05)
        # The function refuses to handle 3+ columns
        assert result is None

    def test_gap_width_is_positive(self) -> None:
        left = [30.0] * 15
        right = [380.0] * 15
        result = detect_columns(left + right, page_width=595.0)
        if result is not None:
            assert result.gap_width > 0

    # ---------------------------------------------------------------
    # Regression tests for fixes applied 2026-05-02
    # ---------------------------------------------------------------

    def test_regression_left_clustered_single_column_not_misdetected(self) -> None:
        """Words clustered only on the left half of the page must NOT be reported
        as a 2-column layout simply because the right margin is empty.

        Previously the gap-detection walked only the central 60 % of the page
        and treated any empty central bins as a column gap.  For a real-world
        single-column CV with all text on the left, this misfired and caused
        every page to be cropped in half.
        """
        # Mimic the real fixture: 40 words all between x=50 and x=200.
        x_coords = [50.0 + (i % 30) * 5 for i in range(40)]
        result = detect_columns(x_coords, page_width=595.0, column_gap_ratio=0.1)
        assert result is None

    def test_regression_two_column_with_trailing_margin(self) -> None:
        """A real two-column page has *both* a column gap (real) AND a right
        margin (not a real gap).  The fixed algorithm must report exactly one
        column boundary, not two.
        """
        left = [50.0 + i for i in range(15)]   # bin 1-2
        right = [350.0 + i for i in range(15)]  # bin 11-12, leaving bins 13-19 empty (margin)
        result = detect_columns(left + right, page_width=595.0, column_gap_ratio=0.1)
        assert result is not None
        # The reported gap must lie inside the central zone, not extend into
        # the right-margin "fake gap".
        assert result.gap_start_x >= 0.2 * 595.0
        assert result.gap_end_x <= 0.8 * 595.0


class TestSplitPageAtBoundary:
    """Tests for split_page_at_boundary()."""

    def test_left_range_starts_at_zero(self) -> None:
        boundary = ColumnBoundary(gap_start_x=200.0, gap_end_x=300.0)
        (left_x0, _), _ = split_page_at_boundary(595.0, boundary)
        assert left_x0 == 0.0

    def test_left_range_ends_at_gap_start(self) -> None:
        boundary = ColumnBoundary(gap_start_x=200.0, gap_end_x=300.0)
        (_, left_x1), _ = split_page_at_boundary(595.0, boundary)
        assert left_x1 == 200.0

    def test_right_range_starts_at_gap_end(self) -> None:
        boundary = ColumnBoundary(gap_start_x=200.0, gap_end_x=300.0)
        _, (right_x0, _) = split_page_at_boundary(595.0, boundary)
        assert right_x0 == 300.0

    def test_right_range_ends_at_page_width(self) -> None:
        boundary = ColumnBoundary(gap_start_x=200.0, gap_end_x=300.0)
        _, (_, right_x1) = split_page_at_boundary(595.0, boundary)
        assert right_x1 == 595.0

    def test_ranges_do_not_overlap(self) -> None:
        boundary = ColumnBoundary(gap_start_x=250.0, gap_end_x=350.0)
        (_, left_x1), (right_x0, _) = split_page_at_boundary(595.0, boundary)
        assert left_x1 <= right_x0


class TestColumnBoundary:
    def test_gap_width_property(self) -> None:
        b = ColumnBoundary(gap_start_x=100.0, gap_end_x=250.0)
        assert b.gap_width == pytest.approx(150.0)

    def test_frozen_dataclass_cannot_be_mutated(self) -> None:
        b = ColumnBoundary(gap_start_x=100.0, gap_end_x=250.0)
        with pytest.raises((AttributeError, TypeError)):
            b.gap_start_x = 999.0  # type: ignore[misc]
