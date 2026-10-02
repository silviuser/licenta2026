import type {
  ApplicationResponse,
  CvResponse,
  DashboardResponse,
  JdResponse,
  MatchJobResponse,
  MatchReport,
} from '../../api/types';

export const cv1: CvResponse = {
  id: 'cv-1',
  originalFilename: 'alice.pdf',
  contentType: 'application/pdf',
  sizeBytes: 1024,
  detectedLanguage: 'en',
  extractionCached: true,
  processingStatus: 'READY',
  processingError: null,
  contentHash: 'hash-1',
  extractedEmail: 'alice@example.com',
  manualEmail: null,
  effectiveEmail: 'alice@example.com',
  emailSource: 'EXTRACTED',
  createdAt: '2026-06-06T12:00:00Z',
};

export const jd1: JdResponse = {
  id: 'jd-1',
  title: 'Backend Engineer',
  descriptionText: 'Build and maintain backend services.',
  requirements: [
    {
      id: 'r-1',
      text: 'Java',
      skillUri: null,
      skillLabel: 'Java',
      importance: 'required',
      confidence: 0.9,
      source: 'EXTRACTED',
    },
    {
      id: 'r-2',
      text: 'Docker',
      skillUri: null,
      skillLabel: 'Docker',
      importance: 'nice_to_have',
      confidence: 0.7,
      source: 'MANUAL',
    },
  ],
  processingStatus: 'READY',
  processingError: null,
  createdAt: '2026-06-06T12:00:00Z',
  updatedAt: '2026-06-06T12:00:00Z',
};

export const application1: ApplicationResponse = {
  applicationId: 'a-1',
  cvId: 'cv-1',
  filename: 'alice.pdf',
  cvProcessingStatus: 'READY',
  origin: 'RECRUITER',
  candidateName: null,
  candidateEmail: null,
  candidatePhone: null,
  effectiveEmail: 'alice@example.com',
  emailSource: 'EXTRACTED',
  appliedAt: null,
  createdAt: '2026-06-06T12:00:00Z',
};

/** A candidate-link application (REWORK 3 D37). */
export const applicationViaLink: ApplicationResponse = {
  applicationId: 'a-2',
  cvId: 'cv-2',
  filename: 'bob.pdf',
  cvProcessingStatus: 'READY',
  origin: 'CANDIDATE_LINK',
  candidateName: 'Bob Candidate',
  candidateEmail: 'bob@candidate.com',
  candidatePhone: '+40 712 000 111',
  effectiveEmail: 'bob@candidate.com',
  emailSource: 'CANDIDATE_FORM',
  appliedAt: '2026-06-06T13:00:00Z',
  createdAt: '2026-06-06T13:00:00Z',
};

export const applyLinkActive = {
  exists: true,
  enabled: true,
  url: 'http://localhost:5173/apply/test-token-123',
};

export const matchReport: MatchReport = {
  jd_id: 'jd-1',
  source_jd_ids: [],
  generated_at: '2026-06-06T12:00:05Z',
  required_total: 1,
  nice_to_have_total: 1,
  candidates: [
    {
      rank: 1,
      cv_id: 'cv-1',
      filename: 'alice.pdf',
      source: 'DIRECT',
      source_jd_id: null,
      source_jd_title: null,
      origin: 'RECRUITER',
      candidate_name: null,
      candidate_email: null,
      candidate_phone: null,
      effective_email: 'alice@example.com',
      email_source: 'EXTRACTED',
      status: 'SUCCEEDED',
      overall_score: 0.78,
      overall_class: 'strong',
      required_coverage: 1,
      nice_to_have_coverage: 0,
      matched_skills: [
        {
          requirement_text: 'Java',
          importance: 'required',
          evidence_surface_form: 'Java 17',
          evidence_section: 'experience',
          match_score: 0.91,
        },
      ],
      missing_skills: { required: [], nice_to_have: ['Docker'] },
      explanation: 'Covers 1/1 required. Strengths: Java (0.91).',
      error_code: null,
    },
  ],
};

export function runningJob(jobId: string): MatchJobResponse {
  return {
    jobId,
    cvId: null,
    jdId: 'jd-1',
    status: 'RUNNING',
    pipelineVersion: null,
    errorCode: null,
    errorDetail: null,
    result: null,
    createdAt: '2026-06-06T12:00:00Z',
    startedAt: '2026-06-06T12:00:01Z',
    finishedAt: null,
  };
}

export function succeededJob(jobId: string): MatchJobResponse {
  return {
    jobId,
    cvId: null,
    jdId: 'jd-1',
    status: 'SUCCEEDED',
    pipelineVersion: 'skill_matcher@test',
    errorCode: null,
    errorDetail: null,
    result: matchReport,
    createdAt: '2026-06-06T12:00:00Z',
    startedAt: '2026-06-06T12:00:01Z',
    finishedAt: '2026-06-06T12:00:05Z',
  };
}

export const dashboard: DashboardResponse = {
  kpis: {
    openPositions: 2,
    uniqueCandidates: 3,
    cvsProcessing: 1,
    lastMatch: {
      jobId: 'job-1',
      jdId: 'jd-1',
      jdTitle: 'Backend Engineer',
      finishedAt: '2026-06-06T12:00:05Z',
      topScore: 0.78,
    },
  },
  positions: [
    {
      jdId: 'jd-1',
      title: 'Backend Engineer',
      processingStatus: 'READY',
      applicationCount: 2,
      createdAt: '2026-06-06T12:00:00Z',
      lastMatch: {
        jobId: 'job-1',
        status: 'SUCCEEDED',
        topScore: 0.78,
        finishedAt: '2026-06-06T12:00:05Z',
      },
    },
    {
      jdId: 'jd-2',
      title: 'Data Engineer',
      processingStatus: 'READY',
      applicationCount: 1,
      createdAt: '2026-06-05T12:00:00Z',
      lastMatch: null,
    },
  ],
};

export const emptyDashboard: DashboardResponse = {
  kpis: { openPositions: 0, uniqueCandidates: 0, cvsProcessing: 0, lastMatch: null },
  positions: [],
};
