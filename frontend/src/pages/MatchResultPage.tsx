import { useState } from 'react';
import { ArrowLeft, ChevronDown, ChevronsDownUp, ChevronsUpDown, Eye } from 'lucide-react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useNavigate, useParams } from 'react-router-dom';
import type { CandidateReport, CvResponse, EmailSource, MatchJobResponse } from '../api/types';
import { CandidateEmailCell } from '../components/CandidateEmailCell';
import { ContactTopBar, type ContactCandidate } from '../components/ContactTopBar';
import { EmptyState } from '../components/EmptyState';
import { PageHeader } from '../components/PageHeader';
import { ScoreBadge } from '../components/ScoreBadge';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { Loading } from '../components/states/Loading';
import { useViewCv } from '../hooks/useCvs';
import { useJd } from '../hooks/useJds';
import { useMatchJob } from '../hooks/useMatches';
import { CONTACT, CTA, LOADING, MATCH_TOP_N, ORIGIN_LABEL, ROUTES, SOURCE_LABEL } from '../lib/constants';
import { matchFailureMessage } from '../lib/errorMessages';
import { cleanLabel, sectionSuffix } from '../lib/sectionLabel';

export function MatchResultPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useMatchJob(jobId);

  return (
    <>
      <Button startIcon={<ArrowLeft size={16} />} onClick={() => navigate(ROUTES.dashboard)} sx={{ mb: 2 }}>
        {CTA.backToDashboard}
      </Button>

      <PageHeader title="Match result" subtitle="Candidates ranked against this position." />

      {isLoading && <Loading label={LOADING.short} />}
      {isError && <ErrorAlert error={error} onRetry={() => refetch()} />}
      {data && <MatchBody job={data} />}
    </>
  );
}

function MatchBody({ job }: { job: MatchJobResponse }) {
  if (job.status === 'PENDING' || job.status === 'RUNNING') {
    return (
      <Card>
        <CardContent>
          <Stack spacing={2} alignItems="center" sx={{ py: 6 }}>
            <CircularProgress />
            <Typography variant="h6">{LOADING.matchJob}</Typography>
            <Typography variant="body2" color="text.secondary">
              {LOADING.matchJobHint}
            </Typography>
            <Chip label={job.status} size="small" color="info" variant="outlined" />
          </Stack>
        </CardContent>
      </Card>
    );
  }

  if (job.status === 'FAILED') {
    return (
      <ErrorAlert title="Matching failed" message={matchFailureMessage(job.errorCode, job.errorDetail)} />
    );
  }

  const report = job.result;
  if (!report || report.candidates.length === 0) {
    return <EmptyState title="No candidates were scored." body="Attach CVs to this position and run a match." />;
  }

  return <RankedCandidates report={report} />;
}

function RankedCandidates({ report }: { report: NonNullable<MatchJobResponse['result']> }) {
  const jd = useJd(report.jd_id);
  const subject = CONTACT.subject(jd.data?.title ?? 'this position');

  const total = report.candidates.length;
  const scored = report.candidates.filter((c) => c.status === 'SUCCEEDED');

  const [showAll, setShowAll] = useState(false);
  // Manual email edits patch the snapshot locally (the stored report is immutable;
  // the edit shows in the next match, D45). Keyed by cv_id.
  const [overrides, setOverrides] = useState<Map<string, { email: string | null; source: EmailSource }>>(
    () => new Map(),
  );
  const [topN, setTopN] = useState(() => Math.min(MATCH_TOP_N, scored.length));
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(scored.slice(0, Math.min(MATCH_TOP_N, scored.length)).map((c) => c.cv_id)),
  );

  const resolved = (c: CandidateReport) =>
    overrides.get(c.cv_id) ?? { email: c.effective_email, source: c.email_source };

  function handleEmailUpdated(c: CandidateReport, cv: CvResponse) {
    // Form email (candidate-link) always wins over a manual CV edit (D42), so only
    // fall back to the CV's resolved address when there is no form email.
    const next = c.candidate_email
      ? { email: c.candidate_email, source: 'CANDIDATE_FORM' as EmailSource }
      : { email: cv.effectiveEmail, source: cv.emailSource };
    setOverrides((prev) => new Map(prev).set(c.cv_id, next));
  }

  function changeTopN(n: number) {
    setTopN(n);
    setSelected(new Set(scored.slice(0, n).map((c) => c.cv_id)));
  }
  function toggleSelected(cvId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cvId)) next.delete(cvId);
      else next.add(cvId);
      return next;
    });
  }

  const firstN = scored.slice(0, topN).map((c) => c.cv_id);
  const isCustom = selected.size !== firstN.length || firstN.some((id) => !selected.has(id));

  const selectedContacts: ContactCandidate[] = scored
    .filter((c) => selected.has(c.cv_id))
    .map((c) => ({ cvId: c.cv_id, name: c.candidate_name ?? c.filename, email: resolved(c).email }));

  // Default view = the top N scored candidates. Failed CVs never take a top slot;
  // they only show with "Show all". If nothing scored, fall back to the full list.
  const top = scored.slice(0, MATCH_TOP_N);
  const visible = showAll || top.length === 0 ? report.candidates : top;
  const hiddenCount = total - visible.length;
  const canToggle = hiddenCount > 0 || showAll;

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip label={`${total} candidate${total === 1 ? '' : 's'}`} size="small" />
        <Chip label={`${report.required_total} required`} size="small" variant="outlined" color="primary" />
        <Chip label={`${report.nice_to_have_total} nice-to-have`} size="small" variant="outlined" />
        {report.source_jd_ids.length > 0 && (
          <Chip
            label={`Includes ${report.source_jd_ids.length} other position${
              report.source_jd_ids.length === 1 ? '' : 's'
            }`}
            size="small"
            color="info"
            variant="outlined"
          />
        )}
      </Stack>

      {!showAll && hiddenCount > 0 && (
        <Typography variant="body2" color="text.secondary">
          Showing the top {visible.length} of {total} candidates.
        </Typography>
      )}

      {visible.map((c) => {
        const r = resolved(c);
        return (
          <CandidateRow
            key={c.cv_id}
            candidate={c}
            selectable={c.status === 'SUCCEEDED'}
            selected={selected.has(c.cv_id)}
            onToggle={() => toggleSelected(c.cv_id)}
            email={r.email}
            source={r.source}
            subject={subject}
            onEmailUpdated={(cv) => handleEmailUpdated(c, cv)}
          />
        );
      })}

      {canToggle && (
        <Box>
          <Button
            startIcon={showAll ? <ChevronsDownUp size={16} /> : <ChevronsUpDown size={16} />}
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll ? `Show top ${MATCH_TOP_N}` : `Show all ${total} candidates`}
          </Button>
        </Box>
      )}

      {scored.length > 0 && (
        <ContactTopBar
          selected={selectedContacts}
          topN={topN}
          maxN={scored.length}
          isCustom={isCustom}
          onTopNChange={changeTopN}
          onRemove={toggleSelected}
          subject={subject}
        />
      )}
    </Stack>
  );
}

function CandidateRow({
  candidate: c,
  selectable,
  selected,
  onToggle,
  email,
  source,
  subject,
  onEmailUpdated,
}: {
  candidate: CandidateReport;
  selectable: boolean;
  selected: boolean;
  onToggle: () => void;
  email: string | null;
  source: EmailSource;
  subject: string;
  onEmailUpdated: (cv: CvResponse) => void;
}) {
  const failed = c.status === 'FAILED';
  const { viewCv, viewingCvId } = useViewCv();
  const viewing = viewingCvId === c.cv_id;
  return (
    <Accordion disableGutters>
      <AccordionSummary expandIcon={<ChevronDown size={18} />}>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ width: '100%', pr: 2 }}>
          {selectable && (
            <Checkbox
              size="small"
              checked={selected}
              onClick={(e) => e.stopPropagation()}
              onChange={onToggle}
              inputProps={{ 'aria-label': `Select ${c.candidate_name ?? c.filename}` }}
              sx={{ p: 0.5 }}
            />
          )}
          <Typography variant="body2" color="text.secondary" sx={{ minWidth: 32 }}>
            {c.rank != null ? `#${c.rank}` : '—'}
          </Typography>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="body1" sx={{ fontWeight: 500 }} noWrap>
              {c.candidate_name ?? c.filename}
            </Typography>
            {c.candidate_name && (
              <Typography variant="caption" color="text.secondary" display="block" noWrap>
                {c.filename}
              </Typography>
            )}
          </Box>
          {c.origin === 'CANDIDATE_LINK' && (
            <Chip
              label={ORIGIN_LABEL.CANDIDATE_LINK}
              size="small"
              color="info"
              variant="outlined"
            />
          )}
          {c.source === 'OTHER_JD' && (
            <Tooltip title={c.source_jd_title ? `Pulled in from: ${c.source_jd_title}` : SOURCE_LABEL.OTHER_JD}>
              <Chip
                label={c.source_jd_title ? `From: ${c.source_jd_title}` : SOURCE_LABEL.OTHER_JD}
                size="small"
                color="info"
                variant="outlined"
              />
            </Tooltip>
          )}
          <Tooltip title="View CV">
            <span>
              <IconButton
                size="small"
                aria-label={`View CV for ${c.candidate_name ?? c.filename}`}
                disabled={viewing}
                onClick={(e) => {
                  e.stopPropagation();
                  viewCv(c.cv_id, c.filename);
                }}
              >
                {viewing ? <CircularProgress size={16} /> : <Eye size={16} />}
              </IconButton>
            </span>
          </Tooltip>
          {failed ? (
            <Chip label={`Failed${c.error_code ? `: ${c.error_code}` : ''}`} size="small" color="error" />
          ) : (
            <ScoreBadge score={c.overall_score ?? 0} klass={c.overall_class ?? 'no'} size="sm" />
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        {failed ? (
          <Typography variant="body2" color="error.main">
            This CV could not be scored ({c.error_code ?? 'error'}).
          </Typography>
        ) : (
          <Stack spacing={2}>
            <CandidateEmailCell
              cvId={c.cv_id}
              email={email}
              source={source}
              subject={subject}
              onUpdated={onEmailUpdated}
            />
            {c.candidate_phone && (
              <Typography variant="body2" color="text.secondary">
                {c.candidate_phone}
              </Typography>
            )}

            {c.explanation && (
              <Typography variant="body2" color="text.secondary">
                {c.explanation}
              </Typography>
            )}

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Identified skills ({c.matched_skills.length})
              </Typography>
              {c.matched_skills.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  None matched.
                </Typography>
              ) : (
                <Stack spacing={0.5}>
                  {c.matched_skills.map((s, i) => (
                    <Stack key={i} direction="row" spacing={1} alignItems="center">
                      <Chip
                        label={s.importance === 'nice_to_have' ? 'nice-to-have' : 'required'}
                        size="small"
                        variant="outlined"
                        color={s.importance === 'nice_to_have' ? 'default' : 'primary'}
                      />
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {cleanLabel(s.requirement_text)}
                      </Typography>
                      {s.evidence_surface_form && (
                        <Typography variant="body2" color="text.secondary">
                          — “{cleanLabel(s.evidence_surface_form)}”
                          {sectionSuffix(s.evidence_section)}
                        </Typography>
                      )}
                      <Box sx={{ flexGrow: 1 }} />
                      <Chip label={s.match_score.toFixed(2)} size="small" />
                    </Stack>
                  ))}
                </Stack>
              )}
            </Box>

            <Divider />

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Missing skills
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {(c.missing_skills?.required ?? []).map((t) => (
                  <Chip key={`r-${t}`} label={cleanLabel(t)} size="small" color="error" />
                ))}
                {(c.missing_skills?.nice_to_have ?? []).map((t) => (
                  <Chip key={`n-${t}`} label={cleanLabel(t)} size="small" variant="outlined" />
                ))}
                {(c.missing_skills?.required.length ?? 0) === 0 &&
                  (c.missing_skills?.nice_to_have.length ?? 0) === 0 && (
                    <Typography variant="body2" color="text.secondary">
                      Nothing missing.
                    </Typography>
                  )}
              </Stack>
            </Box>
          </Stack>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
