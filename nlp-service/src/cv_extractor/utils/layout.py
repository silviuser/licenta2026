"""Multi-column layout detection for PDF pages.

Strategy
--------
We collect the x-coordinate (left edge) of every word on the page.
Words naturally cluster around the left margin of each column.  A clear
gap in the x-distribution — wider than ``column_gap_ratio * page_width``
— signals a second column.

We use a simple histogram approach rather than a full clustering algorithm
so the logic stays easy to test and reason about:

1. Bucket the page width into N_BINS bins.
2. Compute the normalised word count per bin.
3. Walk through bins from left to right; whenever a contiguous run of
   *empty* bins is wider than the gap threshold, we call it a column
   boundary.
4. A page is multi-column if exactly one such gap is found in the central
   60 % of the page (avoids misidentifying left/right page margins as gaps).
"""

from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

# Number of histogram bins across the page width.
_N_BINS = 20

# The gap must fall within the central portion of the page (not at edges).
_CENTRAL_ZONE_START = 0.2  # 20% from left
_CENTRAL_ZONE_END = 0.8    # 80% from left


@dataclass(frozen=True)
class ColumnBoundary:
    """Describes a detected gap between columns.

    Attributes:
        gap_start_x: Left x-coordinate of the gap (in page units).
        gap_end_x:   Right x-coordinate of the gap (in page units).
    """

    gap_start_x: float
    gap_end_x: float

    @property
    def gap_width(self) -> float:
        """Width of the detected gap."""
        return self.gap_end_x - self.gap_start_x


def detect_columns(
    word_x_coords: list[float],
    page_width: float,
    column_gap_ratio: float = 0.1,
    min_words: int = 10,
) -> ColumnBoundary | None:
    """Detect whether a page has a two-column layout.

    Args:
        word_x_coords:    List of x-coordinate (left edge) for every word
                          bounding box on the page.
        page_width:       Total page width in the same units as ``word_x_coords``.
        column_gap_ratio: Minimum gap width as a fraction of ``page_width``
                          required to consider it a column separator.
        min_words:        If fewer words than this are present, skip detection
                          (too little evidence).

    Returns:
        A ``ColumnBoundary`` describing the gap if two columns are detected,
        or ``None`` for single-column pages.
    """
    if len(word_x_coords) < min_words or page_width <= 0:
        return None

    bin_width = page_width / _N_BINS
    gap_threshold_bins = max(1, round(column_gap_ratio * _N_BINS))

    # Build histogram: count words whose left edge falls in each bin.
    bins: list[int] = [0] * _N_BINS
    for x in word_x_coords:
        bin_idx = min(int(x / bin_width), _N_BINS - 1)
        bins[bin_idx] += 1

    # A real column gap must have content on both sides — i.e., it lies
    # strictly between the leftmost and rightmost populated bins.  Empty
    # runs at page margins are not column boundaries.
    populated = [i for i, count in enumerate(bins) if count > 0]
    if len(populated) < 2:
        # All words clustered in a single bin (or none at all) → single column.
        log.debug("column_detection_skipped", reason="content_in_single_bin")
        return None

    first_populated = populated[0]
    last_populated = populated[-1]

    central_start_bin = int(_CENTRAL_ZONE_START * _N_BINS)
    central_end_bin = int(_CENTRAL_ZONE_END * _N_BINS)

    # Find contiguous empty runs strictly inside the populated span.  The
    # loop iterates *through* last_populated (inclusive) — that bin is
    # populated by construction, so its else-branch closes any open gap.
    gaps: list[tuple[int, int]] = []
    in_gap = False
    gap_start = 0

    for i in range(first_populated + 1, last_populated + 1):
        if bins[i] == 0:
            if not in_gap:
                in_gap = True
                gap_start = i
        else:
            if in_gap:
                in_gap = False
                gaps.append((gap_start, i - 1))

    # Wide-enough gaps that overlap the central zone.
    def _overlaps_central(g: tuple[int, int]) -> bool:
        return g[0] < central_end_bin and g[1] >= central_start_bin

    significant_gaps = [
        g for g in gaps
        if (g[1] - g[0] + 1) >= gap_threshold_bins and _overlaps_central(g)
    ]

    if len(significant_gaps) != 1:
        # Zero gaps → single column; 2+ gaps → unusual layout, don't guess.
        log.debug(
            "column_detection_skipped",
            reason="unexpected gap count",
            gap_count=len(significant_gaps),
        )
        return None

    gap_start_bin, gap_end_bin = significant_gaps[0]
    raw_start_x = gap_start_bin * bin_width
    raw_end_x = (gap_end_bin + 1) * bin_width
    # Clip to the central zone so downstream cropping never strays into
    # legitimate column content at the page edges.
    central_start_x = _CENTRAL_ZONE_START * page_width
    central_end_x = _CENTRAL_ZONE_END * page_width
    boundary = ColumnBoundary(
        gap_start_x=max(raw_start_x, central_start_x),
        gap_end_x=min(raw_end_x, central_end_x),
    )
    log.debug(
        "two_column_detected",
        gap_start_x=boundary.gap_start_x,
        gap_end_x=boundary.gap_end_x,
        page_width=page_width,
    )
    return boundary


def split_page_at_boundary(
    page_width: float,
    boundary: ColumnBoundary,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Convert a ColumnBoundary into two crop x-ranges.

    Args:
        page_width: Total width of the page.
        boundary:   The detected column gap.

    Returns:
        A tuple ``(left_range, right_range)`` where each range is
        ``(x_min, x_max)`` suitable for passing to ``pdfplumber``'s
        ``page.crop((x0, top, x1, bottom))``.
    """
    left_x_max = boundary.gap_start_x
    right_x_min = boundary.gap_end_x
    return (0.0, left_x_max), (right_x_min, page_width)
