/** Static config + UX copy (FRONTEND_KICKOFF_PROMPT §14.3 — English, single source of truth). */

// Client-side PDF guard. Backend default HRHELPER_BACKEND_MAX_PDF_MB=20.
export const MAX_PDF_BYTES = 20 * 1024 * 1024;
export const PDF_MIME = 'application/pdf';

// Default page size for paginated lists.
export const DEFAULT_PAGE_SIZE = 20;

// Match polling interval (§7).
export const MATCH_POLL_INTERVAL_MS = 2000;

// Default size of the ranked "top candidates" shown on the match result page;
// the rest are revealed with a "Show all" toggle.
export const MATCH_TOP_N = 5;

export const ROUTES = {
  login: '/login',
  register: '/register',
  dashboard: '/',
  cvs: '/cvs',
  jds: '/jds',
  jdNew: '/jds/new',
  jd: (id: string) => `/jds/${id}`,
  jdUpload: (id: string) => `/jds/${id}?upload=1`,
  match: (jobId: string) => `/match/${jobId}`,
  history: '/history',
  apply: (token: string) => `/apply/${token}`,
} as const;

/** CTA labels — verb + outcome (§14.3). */
export const CTA = {
  signIn: 'Sign in',
  createAccount: 'Create account',
  signOut: 'Sign out',
  uploadCv: 'Upload CV',
  download: 'Download',
  deleteCv: 'Delete CV',
  createJd: 'Create job description',
  saveChanges: 'Save changes',
  addRequirement: 'Add requirement',
  delete: 'Delete',
  runMatch: 'Run match',
  backToHistory: 'Back to history',
  uploadCvs: 'Upload CVs',
  attachFromLibrary: 'Attach from library',
  attach: 'Attach',
  saveRequirements: 'Save requirements',
  includeOtherApplications: 'Also pull in candidates from other positions',
  openJd: 'Open',
  backToJd: 'Back to position',
  newPosition: 'New position',
  backToDashboard: 'Back to dashboard',
  selectAll: 'Select all',
  selectNone: 'Select none',
} as const;

/** Dashboard KPI card labels (D30). */
export const KPI_LABEL = {
  openPositions: 'Open positions',
  uniqueCandidates: 'Candidates (unique)',
  cvsProcessing: 'CVs processing',
  lastMatch: 'Last match',
} as const;

/** Human labels for the processing-status badge (D26). */
export const STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  PROCESSING: 'Processing',
  READY: 'Ready',
  FAILED: 'Failed',
};

/** Provenance badge for pooled candidates (D23). */
export const SOURCE_LABEL: Record<string, string> = {
  DIRECT: 'Applied here',
  OTHER_JD: 'From another position',
};

/** Application-origin badge (REWORK 3 D37). */
export const ORIGIN_LABEL: Record<string, string> = {
  RECRUITER: 'Added by you',
  CANDIDATE_LINK: 'Applied via link',
};

/** Email-source badge (REWORK 4 D42). Wording kept distinct from the
 *  requirement-source badge ('extracted'/'manual') to avoid ambiguity. */
export const EMAIL_SOURCE_LABEL: Record<string, string> = {
  CANDIDATE_FORM: 'from form',
  MANUAL: 'edited',
  EXTRACTED: 'from CV',
  NONE: 'no email',
};

/** Contact-action copy (REWORK 4 D44/D45/D47 — English). */
export const CONTACT = {
  email: 'Email',
  noEmailTooltip: 'No address — add one manually',
  editTooltip: 'Edit email',
  emailLabel: 'Email address',
  save: 'Save',
  cancel: 'Cancel',
  invalidEmail: 'Enter a valid email address',
  saved: 'Email updated',
  topN: 'Contact top',
  copyAddresses: 'Copy addresses',
  copied: 'Copied ✓',
  copyFailed: 'Could not copy the addresses',
  openInEmail: 'Open in email',
  tooLong:
    'Too many addresses for a mailto link — copy them instead and paste into your email client.',
  /** mailto subject (D16-consistent, EN). */
  subject: (positionTitle: string) => `${positionTitle} — next steps`,
  selectedSummary: (selected: number, withEmail: number) =>
    `${selected} selected · ${withEmail} with email`,
  withoutEmail: (n: number) => `${n} without email`,
} as const;

/** mailto URLs longer than this are impractical across clients (D47). */
export const MAILTO_MAX_URL = 1800;

/** Recruiter-facing apply-link section copy (REWORK 3 §3.2). */
export const APPLY_LINK = {
  title: 'Application link',
  description:
    'Share this link so candidates can apply to this position directly — no account needed.',
  generate: 'Generate application link',
  copy: 'Copy link',
  copied: 'Link copied',
  regenerate: 'Regenerate',
  active: 'Active',
  inactive: 'Inactive',
  regenerateTitle: 'Regenerate the application link?',
  regenerateBody:
    'The current link will stop working immediately. Anyone who still has it will no longer be able to apply.',
  enabledHint: 'Candidates can apply through this link.',
  disabledHint: 'The link is turned off — candidates cannot apply right now.',
} as const;

/** Public candidate apply page copy (REWORK 3 §3.1 — English, candidate-facing). */
export const PUBLIC_APPLY = {
  appName: 'HR Helper',
  intro: 'Apply for this position by sharing your details and résumé.',
  unavailableTitle: 'This application link is no longer available.',
  unavailableBody:
    'The link may have been turned off or replaced. Please ask the recruiter for an up-to-date link.',
  name: 'Full name',
  email: 'Email',
  phone: 'Phone',
  submit: 'Submit application',
  submitting: 'Submitting…',
  receivedTitle: 'Your application has been received.',
  receivedBody: 'Thank you for applying. The recruiter will review your résumé.',
  updatedTitle: 'Your application has been updated.',
  updatedBody: 'We replaced your previous submission with the latest details and résumé.',
  invalidName: 'Please enter your name.',
  invalidEmail: 'Please enter a valid email address.',
  invalidPhone: 'Please enter a valid phone number.',
  invalidFile: 'Please attach your résumé as a PDF.',
} as const;

/** Empty-state copy (§14.3). */
export const EMPTY = {
  cvs: {
    title: 'No CVs yet.',
    body: "Upload a candidate's PDF résumé to start matching.",
  },
  jds: {
    title: 'No job descriptions yet.',
    body: 'Create one with its required and nice-to-have skills.',
  },
  dashboard: {
    title: 'No positions yet.',
    body: 'Create your first position to upload CVs and run matches.',
  },
  history: {
    title: 'No matches yet.',
    body: 'Run your first match from a CV and a job description.',
  },
} as const;

/** Loading / async copy (§14.3). */
export const LOADING = {
  matchJob: 'Analyzing the CV and scoring it against the job…',
  matchJobHint: 'This can take a few seconds on the first run.',
  short: 'Loading…',
} as const;

/** Success toasts (sober) (§14.3). */
export const SUCCESS = {
  cvUploaded: 'CV uploaded',
  jdSaved: 'Job description saved',
  matchComplete: 'Match complete',
} as const;

/** Human labels for the overall class chip. */
export const CLASS_LABEL: Record<string, string> = {
  strong: 'Strong match',
  possible: 'Possible match',
  no: 'No match',
};
