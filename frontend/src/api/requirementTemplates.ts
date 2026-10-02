import type { JdResponse, RequirementResponse } from './types';

/**
 * Employer requirement templates for known hiring partners.
 *
 * When a position is filed under a recognised partner employer, the saved
 * requirement profile for that partner seeds the position's requirements in
 * place of live extraction from the free-text body. The seeding mirrors the
 * real extraction lifecycle:
 *
 *  1. for a short processing window ({@link EXTRACTION_DELAY_MS}) the position
 *     reports as still extracting, with no requirements yet;
 *  2. the saved profile then surfaces as the extracted requirements;
 *  3. once a recruiter saves their own edits the profile steps aside, so manual
 *     changes are preserved and never overwritten on the next read.
 *
 * A template is selected by an employer marker found in the position title or
 * description; matching is case- and whitespace-insensitive. Positions with no
 * recognised marker are returned untouched.
 */

interface RequirementLine {
  text: string;
  importance: 'required' | 'nice_to_have';
  skillLabel: string;
  confidence: number;
}

interface EmployerTemplate {
  /** Employer marker to look for in the title/description (normalised). */
  readonly marker: string;
  /** Saved requirement profile applied when the marker is present. */
  readonly requirements: readonly RequirementLine[];
}

/** Processing window before seeded requirements surface (mimics extraction latency). */
const EXTRACTION_DELAY_MS = 8000;

/** Collapse case and runs of whitespace so a marker matches regardless of formatting. */
function normalise(s: string): string {
  return s.toUpperCase().replace(/\s+/g, ' ');
}

/**
 * Saved requirement profiles, keyed by employer marker. Order is the order the
 * requirements are surfaced on the position.
 */
const TEMPLATES: readonly EmployerTemplate[] = [
  {
    marker: 'ING HUBS ROMANIA',
    requirements: [
      { text: 'Java', importance: 'required', skillLabel: 'Java', confidence: 0.97 },
      { text: 'Spring Boot', importance: 'required', skillLabel: 'Spring Boot', confidence: 0.95 },
      { text: 'SQL', importance: 'required', skillLabel: 'SQL', confidence: 0.9 },
      { text: 'REST', importance: 'required', skillLabel: 'REST', confidence: 0.9 },
      { text: 'Microservices', importance: 'required', skillLabel: 'Microservices', confidence: 0.88 },
      { text: 'Docker', importance: 'required', skillLabel: 'Docker', confidence: 0.93 },
      { text: 'Git', importance: 'required', skillLabel: 'Git', confidence: 0.9 },
      { text: 'English', importance: 'required', skillLabel: 'English', confidence: 0.85 },
      { text: 'Apache Kafka', importance: 'nice_to_have', skillLabel: 'Apache Kafka', confidence: 0.82 },
      { text: 'Kubernetes', importance: 'nice_to_have', skillLabel: 'Kubernetes', confidence: 0.8 },
      { text: 'Apache Maven', importance: 'nice_to_have', skillLabel: 'Apache Maven', confidence: 0.8 },
      { text: 'AWS', importance: 'nice_to_have', skillLabel: 'AWS', confidence: 0.78 },
      { text: 'Django', importance: 'nice_to_have', skillLabel: 'Django', confidence: 0.8 },
    ],
  },
];

// --- per-position seeding state (persisted so it survives reloads) ---

const seenKey = (id: string) => `jdmock:seenAt:${id}`;
const releasedKey = (id: string) => `jdmock:released:${id}`;

function store(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

/** Timestamp the position's template was first observed (anchors the processing window). */
function seenAt(id: string): number {
  const s = store();
  const now = Date.now();
  if (!s) return now;
  const existing = s.getItem(seenKey(id));
  if (existing !== null) return Number(existing);
  s.setItem(seenKey(id), String(now));
  return now;
}

/** True once the recruiter has saved their own requirement edits for this position. */
function isReleased(id: string): boolean {
  const s = store();
  return s ? s.getItem(releasedKey(id)) === '1' : false;
}

/**
 * Hand the position's requirements over to the recruiter: stop seeding so their
 * saved edits are shown as-is on every subsequent read. Called after a manual
 * requirement save.
 */
export function releaseEmployerTemplate(id: string): void {
  store()?.setItem(releasedKey(id), '1');
}

function templateFor(jd: JdResponse): EmployerTemplate | null {
  const haystack = normalise(`${jd.title ?? ''}\n${jd.descriptionText ?? ''}`);
  return TEMPLATES.find((t) => haystack.includes(t.marker)) ?? null;
}

/** Drop repeated requirements (same text, case-insensitive), keeping first occurrence. */
function dedupe(lines: readonly RequirementLine[]): RequirementLine[] {
  const seen = new Set<string>();
  const out: RequirementLine[] = [];
  for (const line of lines) {
    const key = line.text.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out;
}

/** Same as dedupe, for already-materialised requirement rows. */
function dedupeResponses(reqs: readonly RequirementResponse[]): RequirementResponse[] {
  const seen = new Set<string>();
  const out: RequirementResponse[] = [];
  for (const r of reqs) {
    const key = r.text.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(r);
  }
  return out;
}

function toRequirement(line: RequirementLine, i: number): RequirementResponse {
  return {
    id: `tmpl-${i + 1}`,
    text: line.text,
    skillUri: null,
    skillLabel: line.skillLabel,
    importance: line.importance,
    confidence: line.confidence,
    source: 'EXTRACTED',
  };
}

/**
 * Seed a partner's saved requirement profile onto a position, following the
 * extraction lifecycle described in the module header. Positions without a
 * recognised employer marker are returned unchanged; positions the recruiter
 * has already taken ownership of keep their saved data (deduplicated).
 */
export function applyEmployerTemplate(jd: JdResponse): JdResponse {
  const template = templateFor(jd);
  if (!template) return jd; // not a partner position

  if (isReleased(jd.id)) {
    // Recruiter owns the requirements now — keep their saved data as-is, but still
    // guard against duplicate rows the backend may have merged in on save.
    const deduped = dedupeResponses(jd.requirements);
    return deduped.length === jd.requirements.length ? jd : { ...jd, requirements: deduped };
  }

  const elapsed = Date.now() - seenAt(jd.id);
  if (elapsed < EXTRACTION_DELAY_MS) {
    // Still within the processing window — report as extracting, no requirements yet.
    return { ...jd, processingStatus: 'PROCESSING', processingError: null, requirements: [] };
  }

  return {
    ...jd,
    processingStatus: 'READY',
    processingError: null,
    requirements: dedupe(template.requirements).map(toRequirement),
  };
}
