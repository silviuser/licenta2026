/**
 * Graded score banding for the match badge.
 *
 * The 3-class backend projection (strong / possible / no) collapses very
 * different scores into one chip — anything above the (very low) strong cut
 * shows "Strong match", so 30% and 70% look identical. This util derives a
 * finer, percentage-based band purely for display.
 *
 * Cutoffs mirror the evaluation report (Match_eval_REZULTATE/00_RAPORT):
 *   Excellent  >= 70%
 *   Strong     60–69%
 *   Partial    50–59%
 *   Weak       30–49%
 *   Unsuitable < 30%
 *
 * Banding is computed from the displayed *integer* percentage so the chip
 * label always agrees with the number shown next to it.
 */
export type ScoreBandKey =
  | 'excellent'
  | 'strong'
  | 'partial'
  | 'weak'
  | 'unsuitable';

export interface ScoreBand {
  key: ScoreBandKey;
  label: string;
  /** Chip background (hex). White text stays legible on all five. */
  color: string;
}

/** Ordered high → low; first band whose `min` is met wins. */
const BANDS: readonly { readonly min: number; readonly band: ScoreBand }[] = [
  { min: 70, band: { key: 'excellent', label: 'Excellent', color: '#15803d' } },
  { min: 60, band: { key: 'strong', label: 'Strong', color: '#4d7c0f' } },
  { min: 50, band: { key: 'partial', label: 'Partial', color: '#b45309' } },
  { min: 30, band: { key: 'weak', label: 'Weak', color: '#c2410c' } },
  { min: 0, band: { key: 'unsuitable', label: 'Unsuitable', color: '#b91c1c' } },
] as const;

/** Map an integer percentage (0..100) to its display band. */
export function scoreBand(percent: number): ScoreBand {
  const p = Number.isFinite(percent) ? percent : 0;
  for (const { min, band } of BANDS) {
    if (p >= min) {
      return band;
    }
  }
  return BANDS[BANDS.length - 1].band;
}
