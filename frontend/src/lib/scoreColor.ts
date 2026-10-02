/**
 * Single mapping `overallClass` → MUI semantic palette key (§14.1).
 * Reused by ScoreBadge, CoverageBar and History rows so colour is consistent.
 */
export type SemanticColor = 'success' | 'warning' | 'error' | 'info';

export function scoreColor(klass: string | null | undefined): SemanticColor {
  switch (klass) {
    case 'strong':
      return 'success';
    case 'possible':
      return 'warning';
    case 'no':
      return 'error';
    default:
      return 'info';
  }
}
