import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Play, Trash2 } from 'lucide-react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import type { RequirementInput } from '../api/types';
import { ApplyLinkCard } from '../components/ApplyLinkCard';
import { BulkFileUpload } from '../components/BulkFileUpload';
import { CandidateEmailCell } from '../components/CandidateEmailCell';
import { PageHeader } from '../components/PageHeader';
import { RequirementEditor } from '../components/RequirementEditor';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { Loading } from '../components/states/Loading';
import { useToast } from '../components/toastContext';
import {
  useApplications,
  useAttachApplications,
  useDeleteApplication,
} from '../hooks/useApplications';
import { useCvs, useUploadCvs } from '../hooks/useCvs';
import { useDashboard } from '../hooks/useDashboard';
import { useJd, useUpdateRequirements } from '../hooks/useJds';
import { useStartJdMatch } from '../hooks/useMatches';
import { CONTACT, CTA, ORIGIN_LABEL, ROUTES } from '../lib/constants';
import { errorMessage } from '../lib/errorMessages';
import { summariseUpload } from '../lib/uploads';

export function JdDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const jd = useJd(id);
  const applications = useApplications(id);
  const uploadCvs = useUploadCvs();
  const attach = useAttachApplications(id);
  const removeApp = useDeleteApplication(id);
  const updateRequirements = useUpdateRequirements(id);
  const startMatch = useStartJdMatch();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<RequirementInput[]>([]);
  const [attachOpen, setAttachOpen] = useState(false);
  const [matchOpen, setMatchOpen] = useState(() => searchParams.get('match') === '1');

  const uploadRef = useRef<HTMLDivElement>(null);

  // Deep-link from the dashboard "Upload" shortcut (D30): scroll to the upload zone.
  useEffect(() => {
    if (searchParams.get('upload') === '1') {
      uploadRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [searchParams]);

  if (jd.isLoading) return <Loading />;
  if (jd.isError || !jd.data) return <ErrorAlert error={jd.error} onRetry={() => jd.refetch()} />;

  const data = jd.data;
  const apps = applications.data ?? [];
  const appliedCvIds = new Set(apps.map((a) => a.cvId));

  function startEditing() {
    setDraft(
      data.requirements.map((r) => ({
        text: r.text,
        importance: r.importance === 'nice_to_have' ? 'nice_to_have' : 'required',
        skillUri: r.skillUri,
        skillLabel: r.skillLabel,
        confidence: r.confidence,
        source: r.source,
      })),
    );
    setEditing(true);
  }

  function saveRequirements() {
    updateRequirements.mutate(
      draft.map((r) => ({ ...r, text: r.text.trim() })),
      {
        onSuccess: () => {
          showToast('Requirements saved', 'success');
          setEditing(false);
        },
        onError: (err) => showToast(errorMessage(err), 'error'),
      },
    );
  }

  function handleUpload(files: File[]) {
    uploadCvs.mutate(
      { files, jdId: id },
      {
        onSuccess: (res) => {
          const { message, severity } = summariseUpload(res);
          showToast(message, severity);
          applications.refetch();
        },
        onError: (err) => showToast(errorMessage(err), 'error'),
      },
    );
  }

  function handleRunMatch(sourceJdIds: string[]) {
    startMatch.mutate(
      { jdId: id, sourceJdIds },
      {
        onSuccess: (res) => navigate(ROUTES.match(res.jobId)),
        onError: (err) => showToast(errorMessage(err), 'error'),
      },
    );
  }

  const requirementsInvalid = draft.some((r) => r.text.trim().length === 0);

  return (
    <>
      <Button startIcon={<ArrowLeft size={16} />} onClick={() => navigate(ROUTES.dashboard)} sx={{ mb: 2 }}>
        {CTA.backToDashboard}
      </Button>

      <PageHeader
        title={data.title}
        action={<StatusBadge status={data.processingStatus} error={data.processingError} size="medium" />}
      />

      <Stack spacing={3}>
        {data.descriptionText && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Description
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>
                {data.descriptionText}
              </Typography>
            </CardContent>
          </Card>
        )}

        {/* Requirements */}
        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">Requirements</Typography>
              {!editing ? (
                <Button onClick={startEditing}>Edit requirements</Button>
              ) : (
                <Stack direction="row" spacing={1}>
                  <Button color="inherit" onClick={() => setEditing(false)} disabled={updateRequirements.isPending}>
                    Cancel
                  </Button>
                  <Button
                    variant="contained"
                    onClick={saveRequirements}
                    disabled={updateRequirements.isPending || requirementsInvalid}
                  >
                    {updateRequirements.isPending ? 'Saving…' : CTA.saveRequirements}
                  </Button>
                </Stack>
              )}
            </Stack>
            <Divider sx={{ mb: 2 }} />

            {editing ? (
              <RequirementEditor value={draft} onChange={setDraft} allowEmpty />
            ) : data.requirements.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {data.processingStatus === 'PROCESSING' || data.processingStatus === 'PENDING'
                  ? 'Extracting requirements from the description…'
                  : 'No requirements yet. Edit to add them.'}
              </Typography>
            ) : (
              <Stack spacing={1}>
                {data.requirements.map((r) => (
                  <Stack key={r.id} direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" sx={{ flexGrow: 1 }}>
                      {r.text}
                    </Typography>
                    <Chip
                      label={r.importance === 'nice_to_have' ? 'nice-to-have' : 'required'}
                      size="small"
                      color={r.importance === 'nice_to_have' ? 'default' : 'primary'}
                      variant="outlined"
                    />
                    <Chip
                      label={r.source === 'EXTRACTED' ? 'extracted' : 'manual'}
                      size="small"
                      color={r.source === 'EXTRACTED' ? 'info' : 'default'}
                    />
                  </Stack>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>

        {/* Application link (REWORK 3) */}
        <ApplyLinkCard jdId={id} />

        {/* Applications */}
        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
              <Typography variant="h6">Applications ({apps.length})</Typography>
              <Button variant="outlined" onClick={() => setAttachOpen(true)}>
                {CTA.attachFromLibrary}
              </Button>
            </Stack>

            <Box sx={{ mb: 2 }} ref={uploadRef}>
              <BulkFileUpload
                uploading={uploadCvs.isPending}
                onFiles={handleUpload}
                label={CTA.uploadCvs}
              />
            </Box>

            {apps.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No candidates yet. Upload CVs or attach from your library.
              </Typography>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Candidate</TableCell>
                      <TableCell>Email</TableCell>
                      <TableCell>CV status</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {apps.map((a) => (
                      <TableRow key={a.applicationId} hover>
                        <TableCell>
                          <Stack spacing={0.5}>
                            <Stack direction="row" spacing={1} alignItems="center">
                              <Typography variant="body2">
                                {a.candidateName ?? a.filename ?? a.cvId.slice(0, 8)}
                              </Typography>
                              {a.origin === 'CANDIDATE_LINK' && (
                                <Chip
                                  label={ORIGIN_LABEL.CANDIDATE_LINK}
                                  size="small"
                                  color="info"
                                  variant="outlined"
                                />
                              )}
                            </Stack>
                            {a.origin === 'CANDIDATE_LINK' && a.candidatePhone && (
                              <Typography variant="caption" color="text.secondary">
                                {a.candidatePhone}
                              </Typography>
                            )}
                            {a.candidateName && a.filename && (
                              <Typography variant="caption" color="text.secondary">
                                {a.filename}
                              </Typography>
                            )}
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <CandidateEmailCell
                            cvId={a.cvId}
                            email={a.effectiveEmail}
                            source={a.emailSource}
                            subject={CONTACT.subject(data.title)}
                            onUpdated={() => applications.refetch()}
                          />
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={a.cvProcessingStatus} />
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="Remove from this position">
                            <IconButton
                              aria-label="Remove application"
                              color="error"
                              onClick={() =>
                                removeApp.mutate(a.applicationId, {
                                  onError: (err) => showToast(errorMessage(err), 'error'),
                                })
                              }
                            >
                              <Trash2 size={18} />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>

        {/* Match */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Run a match
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Rank the candidates against this position — optionally pulling in applicants from your
              other positions.
            </Typography>
            <Button
              variant="contained"
              startIcon={<Play size={16} />}
              onClick={() => setMatchOpen(true)}
            >
              {CTA.runMatch}
            </Button>
            {apps.length === 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
                Add at least one candidate, or pull them in from another position.
              </Typography>
            )}
          </CardContent>
        </Card>
      </Stack>

      <AttachDialog
        open={attachOpen}
        onClose={() => setAttachOpen(false)}
        appliedCvIds={appliedCvIds}
        attaching={attach.isPending}
        onAttach={(cvIds) =>
          attach.mutate(cvIds, {
            onSuccess: (res) => {
              showToast(`${res.created.length} attached`, 'success');
              setAttachOpen(false);
            },
            onError: (err) => showToast(errorMessage(err), 'error'),
          })
        }
      />

      <MatchDialog
        open={matchOpen}
        onClose={() => setMatchOpen(false)}
        jdId={id}
        directCount={apps.length}
        running={startMatch.isPending}
        onRun={handleRunMatch}
      />
    </>
  );
}

function MatchDialog({
  open,
  onClose,
  jdId,
  directCount,
  running,
  onRun,
}: {
  open: boolean;
  onClose: () => void;
  jdId: string;
  directCount: number;
  running: boolean;
  onRun: (sourceJdIds: string[]) => void;
}) {
  const dashboard = useDashboard();
  const [includeOther, setIncludeOther] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Other positions to pool from (D27): all unselected initially.
  const otherPositions = useMemo(
    () => (dashboard.data?.positions ?? []).filter((p) => p.jdId !== jdId),
    [dashboard.data, jdId],
  );
  const selectable = otherPositions.filter((p) => p.applicationCount > 0);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleRun() {
    onRun(includeOther ? [...selected] : []);
  }

  const sourceCount = includeOther ? selected.size : 0;
  const canRun = !running && (directCount > 0 || sourceCount > 0);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{CTA.runMatch}</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {directCount > 0
            ? `Scores the ${directCount} candidate${directCount === 1 ? '' : 's'} that applied to this position.`
            : 'No candidates have applied directly to this position yet.'}
        </Typography>

        <FormControlLabel
          control={
            <Checkbox
              checked={includeOther}
              onChange={(e) => setIncludeOther(e.target.checked)}
            />
          }
          label={CTA.includeOtherApplications}
        />

        {includeOther && (
          <Box sx={{ mt: 1 }}>
            <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
              <Button
                size="small"
                onClick={() => setSelected(new Set(selectable.map((p) => p.jdId)))}
                disabled={selectable.length === 0}
              >
                {CTA.selectAll}
              </Button>
              <Button size="small" onClick={() => setSelected(new Set())} disabled={selected.size === 0}>
                {CTA.selectNone}
              </Button>
            </Stack>

            {dashboard.isLoading ? (
              <Loading />
            ) : otherPositions.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                You have no other positions to pull candidates from.
              </Typography>
            ) : (
              <List dense>
                {otherPositions.map((p) => {
                  const disabled = p.applicationCount === 0;
                  return (
                    <ListItem key={p.jdId} disablePadding>
                      <ListItemButton
                        onClick={() => !disabled && toggle(p.jdId)}
                        disabled={disabled}
                      >
                        <Checkbox
                          edge="start"
                          checked={selected.has(p.jdId)}
                          tabIndex={-1}
                          disableRipple
                          disabled={disabled}
                        />
                        <ListItemText
                          primary={p.title}
                          secondary={
                            disabled
                              ? 'No applications'
                              : `${p.applicationCount} application${p.applicationCount === 1 ? '' : 's'}`
                          }
                        />
                      </ListItemButton>
                    </ListItem>
                  );
                })}
              </List>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button variant="contained" startIcon={<Play size={16} />} onClick={handleRun} disabled={!canRun}>
          {running ? 'Starting…' : CTA.runMatch}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function AttachDialog({
  open,
  onClose,
  appliedCvIds,
  attaching,
  onAttach,
}: {
  open: boolean;
  onClose: () => void;
  appliedCvIds: Set<string>;
  attaching: boolean;
  onAttach: (cvIds: string[]) => void;
}) {
  const cvs = useCvs({ size: 100 });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const available = useMemo(
    () => (cvs.data?.content ?? []).filter((cv) => !appliedCvIds.has(cv.id)),
    [cvs.data, appliedCvIds],
  );

  function toggle(cvId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cvId)) next.delete(cvId);
      else next.add(cvId);
      return next;
    });
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Attach CVs from your library</DialogTitle>
      <DialogContent dividers>
        {available.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No more library CVs to attach.
          </Typography>
        ) : (
          <List dense>
            {available.map((cv) => (
              <ListItem key={cv.id} disablePadding>
                <ListItemButton onClick={() => toggle(cv.id)}>
                  <Checkbox edge="start" checked={selected.has(cv.id)} tabIndex={-1} disableRipple />
                  <ListItemText primary={cv.originalFilename} secondary={cv.processingStatus} />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={() => onAttach([...selected])}
          disabled={attaching || selected.size === 0}
        >
          {attaching ? 'Attaching…' : `${CTA.attach} (${selected.size})`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
