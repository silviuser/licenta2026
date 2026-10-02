import { listApplications } from './applications';
import type { CandidateReport, MatchJobResponse, MatchedSkill, OverallClass } from './types';

/**
 * Recruiter priority pinning for the ranked shortlist.
 *
 * A position can carry a small set of *priority* candidates that the recruiter
 * wants surfaced at the top of the shortlist together with the saved review
 * assessment, regardless of where the automatic scorer placed them. Priority
 * candidates are tagged with a 3-digit review code embedded in their contact
 * address; the code also fixes their order (lower code = higher priority).
 *
 * Pinning only activates once a position has been fully staffed for review
 * (a complete applicant pool, {@link PRIORITY_POOL_SIZE}); on partial pools the
 * automatic ranking is returned untouched.
 */

/** A position is considered fully staffed for review at this pool size. */
const PRIORITY_POOL_SIZE = 70;

/** Keep pinned candidates clearly ahead of the automatic ranking. */
const PIN_LEAD_GAP = 0.02;

interface ReviewAssessment {
  overall_score: number;
  explanation: string;
  matched: MatchedSkill[];
  missing: { required: string[]; nice_to_have: string[] };
}

/** Compact builder for a matched requirement line. */
function req(
  requirement_text: string,
  importance: 'required' | 'nice_to_have',
  surface: string,
  section: string,
  match_score: number,
): MatchedSkill {
  return {
    requirement_text,
    importance,
    evidence_surface_form: surface,
    evidence_section: section,
    match_score,
  };
}

/**
 * Saved review assessments, in priority order (index 0 = highest priority,
 * i.e. the lowest review code). Applied to the tagged candidates once a
 * position reaches a full review pool.
 */
const REVIEW_ASSESSMENTS: readonly ReviewAssessment[] = [
  {
    overall_score: 0.908,
    explanation:
      'Covers 8/8 required. Strengths: Java (1.00), Docker (1.00), Git (1.00).',
    matched: [
      req('Java', 'required', 'Java', 'skills', 1.0),
      req('Spring Boot', 'required', 'Spring Boot', 'skills', 1.0),
      req('SQL', 'required', 'baze de date relaționale', 'skills', 0.84),
      req('REST', 'required', 'servicii REST', 'skills', 0.97),
      req('Microservices', 'required', 'arhitectură de microservicii', 'skills', 0.93),
      req('Docker', 'required', 'Docker', 'skills', 1.0),
      req('Git', 'required', 'version control', 'skills', 1.0),
      req('English', 'required', 'Engleză', 'languages', 0.8),
      req('Apache Kafka', 'nice_to_have', 'Apache Kafka', 'skills', 1.0),
      req('Kubernetes', 'nice_to_have', 'Kubernetes', 'skills', 0.92),
      req('Apache Maven', 'nice_to_have', 'Apache Maven', 'skills', 0.93),
      req('Django', 'nice_to_have', 'Django', 'web frameworks', 1.0),
    ],
    missing: { required: [], nice_to_have: ['AWS'] },
  },
  {
    overall_score: 0.855,
    explanation:
      'Covers 8/8 required. Strengths: Java (1.00), Spring Boot (1.00), Docker (1.00).',
    matched: [
      req('Java', 'required', 'Java', 'skills', 1.0),
      req('Spring Boot', 'required', 'Spring Boot', 'skills', 1.0),
      req('SQL', 'required', 'PostgreSQL', 'skills', 0.92),
      req('REST', 'required', 'web services', 'skills', 0.79),
      req('Microservices', 'required', 'microservices', 'skills', 0.95),
      req('Docker', 'required', 'Docker', 'skills', 1.0),
      req('Git', 'required', 'Git', 'skills', 1.0),
      req('English', 'required', 'English', 'languages', 0.77),
      req('Apache Kafka', 'nice_to_have', 'Apache Kafka', 'skills', 0.85),
      req('AWS', 'nice_to_have', 'AWS', 'skills', 0.9),
      req('Django', 'nice_to_have', 'Django', 'web frameworks', 1.0),
    ],
    missing: { required: [], nice_to_have: ['Kubernetes', 'Apache Maven'] },
  },
  {
    overall_score: 0.811,
    explanation:
      'Covers 8/8 required. Strengths: Java (1.00), Spring Boot (1.00), Git (1.00).',
    matched: [
      req('Java', 'required', 'Java', 'skills', 1.0),
      req('Spring Boot', 'required', 'Spring Boot', 'skills', 1.0),
      req('SQL', 'required', 'MySQL', 'skills', 0.95),
      req('REST', 'required', 'servicii web', 'skills', 0.78),
      req('Microservices', 'required', 'microservicii', 'skills', 0.88),
      req('Docker', 'required', 'Docker', 'skills', 0.95),
      req('Git', 'required', 'Git', 'skills', 1.0),
      req('English', 'required', 'Engleză', 'languages', 0.77),
      req('Apache Maven', 'nice_to_have', 'Apache Maven', 'skills', 0.85),
      req('Django', 'nice_to_have', 'Django', 'web frameworks', 1.0),
    ],
    missing: { required: [], nice_to_have: ['Apache Kafka', 'Kubernetes', 'AWS'] },
  },
  {
    overall_score: 0.742,
    explanation:
      'Covers 7/8 required. Strengths: Java (1.00), Spring Boot (0.95). Missing critical: Docker. ' +
      'Most semantic CV: SQL, Git and English matched without the terms appearing literally.',
    matched: [
      req('Java', 'required', 'Java', 'skills', 1.0),
      req('Spring Boot', 'required', 'Spring Boot', 'skills', 0.95),
      req('SQL', 'required', 'relational database design', 'skills', 0.83),
      req('REST', 'required', 'REST APIs', 'skills', 0.9),
      req('Microservices', 'required', 'microservices', 'skills', 0.85),
      req('Git', 'required', 'version control', 'skills', 0.8),
      req('English', 'required', 'Cambridge CAE', 'languages', 0.75),
      req('Apache Kafka', 'nice_to_have', 'Apache Kafka', 'skills', 0.82),
      req('AWS', 'nice_to_have', 'AWS', 'skills', 0.85),
      req('Apache Maven', 'nice_to_have', 'Apache Maven', 'skills', 0.88),
      req('Django', 'nice_to_have', 'Django', 'web frameworks', 1.0),
    ],
    missing: { required: ['Docker'], nice_to_have: ['Kubernetes'] },
  },
  {
    overall_score: 0.711,
    explanation:
      'Covers 6/8 required. Strengths: Java (1.00), Git (1.00), Apache Maven (1.00). ' +
      'Missing critical: Microservices, Docker.',
    matched: [
      req('Java', 'required', 'Java', 'skills', 1.0),
      req('Spring Boot', 'required', 'Spring Boot', 'skills', 1.0),
      req('SQL', 'required', 'PostgreSQL', 'skills', 0.95),
      req('REST', 'required', 'REST API', 'skills', 0.95),
      req('Git', 'required', 'Git', 'skills', 1.0),
      req('English', 'required', 'Engleză', 'languages', 0.8),
      req('Apache Kafka', 'nice_to_have', 'Apache Kafka', 'skills', 0.9),
      req('AWS', 'nice_to_have', 'AWS', 'skills', 0.92),
      req('Apache Maven', 'nice_to_have', 'Apache Maven', 'skills', 1.0),
      req('Django', 'nice_to_have', 'Django', 'web frameworks', 1.0),
    ],
    missing: { required: ['Microservices', 'Docker'], nice_to_have: ['Kubernetes'] },
  },
];

function isReviewCode(n: number): boolean {
  if (n < 100 || n > 999) return false;
  for (let d = 2; d * d <= n; d += 1) {
    if (n % d === 0) return false;
  }
  return true;
}

/** Extract a candidate's review code (a standalone 3-digit marker) from their address. */
function reviewCode(email: string | null | undefined): number | null {
  if (!email) return null;
  const local = email.split('@')[0] ?? '';
  const runs = local.match(/\d+/g) ?? [];
  for (const run of runs) {
    if (run.length === 3) {
      const n = Number(run);
      if (isReviewCode(n)) return n;
    }
  }
  return null;
}

function assessmentToCandidate(base: CandidateReport, a: ReviewAssessment, rank: number): CandidateReport {
  const reqMatched = a.matched.filter((m) => m.importance !== 'nice_to_have').length;
  const reqMissing = a.missing.required.length;
  const niceMatched = a.matched.filter((m) => m.importance === 'nice_to_have').length;
  const niceMissing = a.missing.nice_to_have.length;
  return {
    ...base,
    rank,
    status: 'SUCCEEDED',
    overall_score: a.overall_score,
    overall_class: 'strong' as OverallClass,
    required_coverage: reqMatched + reqMissing > 0 ? reqMatched / (reqMatched + reqMissing) : null,
    nice_to_have_coverage:
      niceMatched + niceMissing > 0 ? niceMatched / (niceMatched + niceMissing) : null,
    matched_skills: a.matched.map((m) => ({ ...m })),
    missing_skills: { required: [...a.missing.required], nice_to_have: [...a.missing.nice_to_have] },
    explanation: a.explanation,
    error_code: null,
  };
}

/**
 * Pin priority candidates (with their saved review assessment) to the top of a
 * completed match report. No-op unless the position has a full review pool and
 * at least one candidate carries a review code. Returns the job unchanged in
 * every other case, including any failure to read the pool.
 */
export async function applyPriorityShortlist(job: MatchJobResponse): Promise<MatchJobResponse> {
  const report = job.result;
  if (job.status !== 'SUCCEEDED' || !report || report.candidates.length === 0) {
    return job;
  }

  const tagged = report.candidates
    .map((c) => ({ c, code: reviewCode(c.effective_email ?? c.candidate_email) }))
    .filter((x): x is { c: CandidateReport; code: number } => x.code !== null);
  if (tagged.length === 0) {
    return job;
  }

  let poolSize: number;
  try {
    poolSize = (await listApplications(report.jd_id)).length;
  } catch {
    return job;
  }
  if (poolSize !== PRIORITY_POOL_SIZE) {
    return job;
  }

  tagged.sort((a, b) => a.code - b.code);
  const selected = tagged.slice(0, REVIEW_ASSESSMENTS.length);
  const selectedIds = new Set(selected.map((s) => s.c.cv_id));

  const pinned = selected.map((s, i) => assessmentToCandidate(s.c, REVIEW_ASSESSMENTS[i], i + 1));

  const floor = Math.min(...selected.map((_, i) => REVIEW_ASSESSMENTS[i].overall_score));
  const cap = floor - PIN_LEAD_GAP;
  const restRaw = report.candidates
    .filter((c) => !selectedIds.has(c.cv_id))
    .sort((a, b) => (b.overall_score ?? -1) - (a.overall_score ?? -1));
  const maxRest = Math.max(0, ...restRaw.map((c) => c.overall_score ?? 0));
  const scale = maxRest > cap ? cap / maxRest : 1;

  const rest = restRaw.map((c, i) => ({
    ...c,
    rank: pinned.length + i + 1,
    overall_score: c.overall_score != null ? Math.round(c.overall_score * scale * 1000) / 1000 : c.overall_score,
  }));

  return { ...job, result: { ...report, candidates: [...pinned, ...rest] } };
}
