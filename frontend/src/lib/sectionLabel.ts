/**
 * Display helpers for CV/JD section tags.
 *
 * Two non-informative section sentinels must never reach the recruiter:
 *   - `other`   — catch-all bucket for free-text / JD prose
 *   - `unknown` — fallback for expansion (semantic) candidates
 *
 * These are hidden at the display layer so they disappear immediately, even on
 * match reports that were stored before the backend started stripping them.
 * Real sections (`skills`, `experience`, `languages`, `education`, …) and
 * meaningful ESCO parentheticals (e.g. "Java (computer programming)") are kept.
 */

const SENTINEL_SECTIONS = new Set(['other', 'unknown']);

/** Trailing " (other)" / " (unknown)" tag, case-insensitive. */
const SENTINEL_SUFFIX = /\s*\((?:other|unknown)\)\s*$/i;

/** Strip a trailing sentinel section tag from a label; keep everything else. */
export function cleanLabel(label: string | null | undefined): string {
  if (!label) return '';
  return label.replace(SENTINEL_SUFFIX, '').trim();
}

/**
 * Render a " (section)" suffix only for informative sections.
 * Returns '' for `other`, `unknown`, blank, or nullish values.
 */
export function sectionSuffix(section: string | null | undefined): string {
  if (!section) return '';
  const s = section.trim();
  if (s === '' || SENTINEL_SECTIONS.has(s.toLowerCase())) return '';
  return ` (${s})`;
}
