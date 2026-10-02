import { useState } from 'react';
import { Play, Plus, Trash2, Upload } from 'lucide-react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
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
import { useNavigate } from 'react-router-dom';
import type { DashboardKpis, PositionSummary } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EmptyState } from '../components/EmptyState';
import { Reveal } from '../components/motion/Reveal';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { Loading } from '../components/states/Loading';
import { useToast } from '../components/toastContext';
import { useDashboard } from '../hooks/useDashboard';
import { useDeleteJd } from '../hooks/useJds';
import { CTA, EMPTY, KPI_LABEL, ROUTES } from '../lib/constants';
import { errorMessage } from '../lib/errorMessages';
import { formatDateTime, toPercent } from '../lib/formatters';

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useDashboard();

  const newPositionButton = (
    <Button variant="contained" startIcon={<Plus size={16} />} onClick={() => navigate(ROUTES.jdNew)}>
      {CTA.newPosition}
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Your open positions, candidates and latest matches at a glance."
        action={newPositionButton}
      />

      {isLoading && <Loading />}
      {isError && <ErrorAlert error={error} onRetry={() => refetch()} />}

      {data && (
        <>
          <KpiRow kpis={data.kpis} />

          <Reveal delay={0.22}>
            <Typography variant="h6" sx={{ mb: 2 }}>
              Positions
            </Typography>

            {data.positions.length === 0 ? (
              <EmptyState title={EMPTY.dashboard.title} body={EMPTY.dashboard.body} action={newPositionButton} />
            ) : (
              <PositionsTable positions={data.positions} />
            )}
          </Reveal>
        </>
      )}
    </>
  );
}

function KpiCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card sx={{ flex: 1, minWidth: 200 }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        {children}
      </CardContent>
    </Card>
  );
}

const KPI_REVEAL_STYLE = { flex: 1, minWidth: 200, display: 'flex' } as const;

function KpiRow({ kpis }: { kpis: DashboardKpis }) {
  const last = kpis.lastMatch;
  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 4 }}>
      <Reveal style={KPI_REVEAL_STYLE}>
        <KpiCard label={KPI_LABEL.openPositions}>
          <Typography variant="h4">{kpis.openPositions}</Typography>
        </KpiCard>
      </Reveal>
      <Reveal delay={0.06} style={KPI_REVEAL_STYLE}>
        <KpiCard label={KPI_LABEL.uniqueCandidates}>
          <Typography variant="h4">{kpis.uniqueCandidates}</Typography>
        </KpiCard>
      </Reveal>
      <Reveal delay={0.12} style={KPI_REVEAL_STYLE}>
        <KpiCard label={KPI_LABEL.cvsProcessing}>
          <Typography variant="h4">{kpis.cvsProcessing}</Typography>
        </KpiCard>
      </Reveal>
      <Reveal delay={0.18} style={KPI_REVEAL_STYLE}>
      <KpiCard label={KPI_LABEL.lastMatch}>
        {last ? (
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }} noWrap>
              {last.jdTitle}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {toPercent(last.topScore)} · {formatDateTime(last.finishedAt)}
            </Typography>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No matches yet
          </Typography>
        )}
      </KpiCard>
      </Reveal>
    </Stack>
  );
}

function PositionsTable({ positions }: { positions: PositionSummary[] }) {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const deleteJd = useDeleteJd();
  const [pendingDelete, setPendingDelete] = useState<PositionSummary | null>(null);

  function handleConfirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete;
    deleteJd.mutate(target.jdId, {
      onSuccess: () => {
        setPendingDelete(null);
        showToast(`Deleted "${target.title}"`, 'success');
      },
      onError: (err) => {
        setPendingDelete(null);
        showToast(errorMessage(err), 'error');
      },
    });
  }

  return (
    <>
      <TableContainer component={Card}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Title</TableCell>
              <TableCell align="right">Applications</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Last match</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {positions.map((p) => (
              <TableRow
                key={p.jdId}
                hover
                sx={{ cursor: 'pointer' }}
                onClick={() => navigate(ROUTES.jd(p.jdId))}
              >
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {p.title}
                  </Typography>
                </TableCell>
                <TableCell align="right">{p.applicationCount}</TableCell>
                <TableCell>
                  <StatusBadge status={p.processingStatus} />
                </TableCell>
                <TableCell>
                  <LastMatchCell position={p} />
                </TableCell>
                <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                  <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
                    <Tooltip title="Open position">
                      <Button size="small" onClick={() => navigate(ROUTES.jd(p.jdId))}>
                        {CTA.openJd}
                      </Button>
                    </Tooltip>
                    <Tooltip title="Run a match">
                      <Button
                        size="small"
                        startIcon={<Play size={14} />}
                        onClick={() => navigate(`${ROUTES.jd(p.jdId)}?match=1`)}
                      >
                        Match
                      </Button>
                    </Tooltip>
                    <Tooltip title="Upload CVs">
                      <Button
                        size="small"
                        startIcon={<Upload size={14} />}
                        onClick={() => navigate(ROUTES.jdUpload(p.jdId))}
                      >
                        Upload
                      </Button>
                    </Tooltip>
                    <Tooltip title="Delete position">
                      <IconButton
                        size="small"
                        color="error"
                        aria-label={`Delete ${p.title}`}
                        onClick={() => setPendingDelete(p)}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <ConfirmDialog
        open={pendingDelete !== null}
        title={pendingDelete ? `Delete "${pendingDelete.title}"?` : 'Delete position?'}
        body="This removes the position, its match history, and every CV that was only attached to this position. Shared CVs (also used by another position) are kept. This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        destructive
        loading={deleteJd.isPending}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}

function LastMatchCell({ position }: { position: PositionSummary }) {
  const last = position.lastMatch;
  if (!last) {
    return (
      <Typography variant="body2" color="text.secondary">
        —
      </Typography>
    );
  }
  if (last.status === 'SUCCEEDED') {
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        <Chip label={toPercent(last.topScore)} size="small" color="primary" variant="outlined" />
        <Typography variant="body2" color="text.secondary">
          {formatDateTime(last.finishedAt)}
        </Typography>
      </Stack>
    );
  }
  if (last.status === 'PENDING' || last.status === 'RUNNING') {
    return <Chip label="Running…" size="small" color="info" variant="outlined" />;
  }
  return <Chip label="Failed" size="small" color="error" variant="outlined" />;
}
