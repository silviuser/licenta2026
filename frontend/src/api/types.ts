/**
 * TypeScript mirror of the backend API contract (REWORK 1).
 *
 * IMPORTANT convention split:
 *  - Backend DTOs are camelCase.
 *  - The match `result` subtree (MatchReport) is serialised snake_case by the
 *    backend's NLP ObjectMapper — use it as-is, do NOT normalise.
 */

// ----- Auth -----
export type Role = 'RECRUITER' | 'ADMIN';

export interface UserResponse {
  id: string;
  email: string;
  fullName: string;
  role: string;
  enabled: boolean;
}

/** NB: no id/email here → fetch the profile from /api/auth/me after login. */
export interface LoginResponse {
  accessToken: string;
  expiresIn: number; // seconds
  role: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  fullName: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

// ----- Processing status (REWORK 1 D26) -----
export type ProcessingStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED';

// ----- Email (REWORK 4 D42) -----
/** Where a candidate's resolved (effective) email came from. */
export type EmailSource = 'CANDIDATE_FORM' | 'MANUAL' | 'EXTRACTED' | 'NONE';

// ----- CVs -----
export interface CvResponse {
  id: string;
  originalFilename: string;
  contentType: string;
  sizeBytes: number;
  detectedLanguage: string | null;
  extractionCached: boolean;
  processingStatus: ProcessingStatus;
  processingError: string | null;
  contentHash: string | null;
  extractedEmail: string | null; // mined from the CV text (REWORK 4 D40)
  manualEmail: string | null; // recruiter override (D45)
  effectiveEmail: string | null; // resolved (no application context here)
  emailSource: EmailSource;
  createdAt: string; // ISO
}

export interface CvEmailUpdateRequest {
  manualEmail: string | null; // null/blank clears the override → reverts to extracted
}

export type UploadItemStatus = 'CREATED' | 'DUPLICATE' | 'REJECTED';

export interface CvUploadItemResult {
  filename: string;
  status: UploadItemStatus;
  cvId: string | null;
  applicationId: string | null;
  reason: string | null;
}

export interface CvBulkUploadResponse {
  results: CvUploadItemResult[];
}

// ----- Job Descriptions -----
export type Importance = 'required' | 'nice_to_have';
export type RequirementSource = 'EXTRACTED' | 'MANUAL';

export interface RequirementInput {
  text: string;
  skillUri?: string | null;
  skillLabel?: string | null;
  importance: Importance;
  confidence?: number | null;
  source?: RequirementSource;
}

export interface RequirementResponse {
  id: string;
  text: string;
  skillUri: string | null;
  skillLabel: string | null;
  importance: string;
  confidence: number;
  source: RequirementSource;
}

export interface JdRequest {
  title: string;
  descriptionText?: string | null;
  requirements?: RequirementInput[]; // optional (D18): empty + text → background extraction
}

export interface JdResponse {
  id: string;
  title: string;
  descriptionText: string | null;
  requirements: RequirementResponse[];
  processingStatus: ProcessingStatus;
  processingError: string | null;
  createdAt: string;
  updatedAt: string;
}

// ----- Applications (CV ↔ JD) -----
export type ApplicationOrigin = 'RECRUITER' | 'CANDIDATE_LINK';

export interface ApplicationResponse {
  applicationId: string;
  cvId: string;
  filename: string | null;
  cvProcessingStatus: ProcessingStatus | null;
  origin: ApplicationOrigin;
  candidateName: string | null;
  candidateEmail: string | null;
  candidatePhone: string | null;
  effectiveEmail: string | null; // resolved contact email (REWORK 4 D42)
  emailSource: EmailSource;
  appliedAt: string | null;
  createdAt: string;
}

export interface AttachApplicationsRequest {
  cvIds: string[];
}

export interface AttachApplicationsResponse {
  created: ApplicationResponse[];
  alreadyExisted: string[];
  notFound: string[];
}

// ----- Matching (per-JD) -----
export type JobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
export type OverallClass = 'strong' | 'possible' | 'no';
export type CandidateSource = 'DIRECT' | 'OTHER_JD';

export interface CreateJdMatchRequest {
  sourceJdIds: string[]; // other JDs to pool applications from (REWORK 2 D27); [] = direct only
}

export interface MatchJobResponse {
  jobId: string;
  cvId: string | null; // null for per-JD jobs
  jdId: string;
  status: JobStatus;
  pipelineVersion: string | null;
  errorCode: string | null;
  errorDetail: string | null;
  result: MatchReport | null; // present at SUCCEEDED
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

// ----- Match report subtree (snake_case — REWORK 1 §G) -----
export interface MatchedSkill {
  requirement_text: string;
  importance: string;
  evidence_surface_form: string | null;
  evidence_section: string | null;
  match_score: number;
}

export interface MissingSkills {
  required: string[];
  nice_to_have: string[];
}

export interface CandidateReport {
  rank: number | null;
  cv_id: string;
  filename: string;
  source: CandidateSource;
  source_jd_id: string | null; // provenance for OTHER_JD candidates (REWORK 2 D29)
  source_jd_title: string | null;
  origin: ApplicationOrigin; // how the application was created (REWORK 3 D37)
  candidate_name: string | null;
  candidate_email: string | null;
  candidate_phone: string | null;
  effective_email: string | null; // resolved contact email (REWORK 4 D42)
  email_source: EmailSource;
  status: 'SUCCEEDED' | 'FAILED';
  overall_score: number | null;
  overall_class: OverallClass | null;
  required_coverage: number | null;
  nice_to_have_coverage: number | null;
  matched_skills: MatchedSkill[];
  missing_skills: MissingSkills | null;
  explanation: string | null;
  error_code: string | null;
}

export interface MatchReport {
  jd_id: string;
  source_jd_ids: string[]; // positions this match pulled applications from (REWORK 2 D27)
  generated_at: string;
  required_total: number;
  nice_to_have_total: number;
  candidates: CandidateReport[];
}

// ----- Dashboard (REWORK 2 D30) -----
export interface LastMatchKpi {
  jobId: string;
  jdId: string;
  jdTitle: string;
  finishedAt: string | null;
  topScore: number | null;
}

export interface DashboardKpis {
  openPositions: number;
  uniqueCandidates: number;
  cvsProcessing: number;
  lastMatch: LastMatchKpi | null;
}

export interface PositionLastMatch {
  jobId: string;
  status: JobStatus;
  topScore: number | null;
  finishedAt: string | null;
}

export interface PositionSummary {
  jdId: string;
  title: string;
  processingStatus: ProcessingStatus;
  applicationCount: number;
  createdAt: string;
  lastMatch: PositionLastMatch | null;
}

export interface DashboardResponse {
  kpis: DashboardKpis;
  positions: PositionSummary[];
}

// ----- Public apply link (REWORK 3 D32–D35) -----
export interface ApplyLinkResponse {
  exists: boolean;
  enabled: boolean;
  url: string | null;
}

/** Public job view shown on /apply/{token} — title + description only (D35). */
export interface PublicJobView {
  jobTitle: string;
  jobDescription: string | null;
}

export interface PublicApplyRequest {
  name: string;
  email: string;
  phone: string;
  file: File;
}

export interface PublicApplyResponse {
  status: 'RECEIVED' | 'UPDATED';
  message: string;
}

// ----- NLP info (ops widget) -----
export interface NlpInfo {
  [key: string]: unknown;
  pipeline_version?: string;
  placeholder_caveat?: string;
}

// ----- Pagination (Spring Page<T>) -----
export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  number: number; // current page (0-based)
  size: number;
  first?: boolean;
  last?: boolean;
  numberOfElements?: number;
}

export interface PageParams {
  page?: number;
  size?: number;
  sort?: string; // e.g. "createdAt,desc"
}

// ----- Uniform error body -----
export interface ApiError {
  error: string; // stable code, e.g. "invalid_content_type"
  detail: string; // human-readable, show to user
  requestId: string | null;
  timestamp: string;
}
