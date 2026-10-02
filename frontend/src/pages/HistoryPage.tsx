import { useState } from 'react';
import {
  Card,
  Chip,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import type { JobStatus, MatchJobResponse } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { PageHeader } from '../components/PageHeader';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { Loading } from '../components/states/Loading';
import { useJds } from '../hooks/useJds';
import { useMatchHistory } from '../hooks/useMatches';
import { DEFAULT_PAGE_SIZE, EMPTY, ROUTES } from '../lib/constants';
import { formatDateTime } from '../lib/formatters';

const STATUSES: JobStatus[] = ['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'];

const STATUS_COLOR: Record<JobStatus, 'default' | 'info' | 'success' | 'error'> = {
  PENDING: 'default',
  RUNNING: 'info',
  SUCCEEDED: 'success',
  FAILED: 'error',
};

export function HistoryPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(DEFAULT_PAGE_SIZE);
  const [jdId, setJdId] = useState('');
  const [status, setStatus] = useState<JobStatus | ''>('');

  const jds = useJds({ size: 100 });
  const { data, isLoading, isError, error, refetch } = useMatchHistory({
    page,
    size,
    jdId: jdId || undefined,
    status: status || undefined,
  });

  const jdName = (id: string) => jds.data?.content.find((j) => j.id === id)?.title ?? id.slice(0, 8);

  const rows = data?.content ?? [];
  const noFilters = !jdId && !status;

  function resetToFirstPage<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(0);
    };
  }

  return (
    <>
      <PageHeader title="Match history" subtitle="Past matches — filter and open any result." />

      <Card sx={{ p: 2, mb: 3 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            select
            label="Position"
            value={jdId}
            onChange={(e) => resetToFirstPage(setJdId)(e.target.value)}
            sx={{ minWidth: 220 }}
            size="small"
          >
            <MenuItem value="">All positions</MenuItem>
            {(jds.data?.content ?? []).map((jd) => (
              <MenuItem key={jd.id} value={jd.id}>
                {jd.title}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Status"
            value={status}
            onChange={(e) => resetToFirstPage(setStatus)(e.target.value as JobStatus | '')}
            sx={{ minWidth: 160 }}
            size="small"
          >
            <MenuItem value="">All statuses</MenuItem>
            {STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </Card>

      {isLoading && <Loading />}
      {isError && <ErrorAlert error={error} onRetry={() => refetch()} />}

      {!isLoading && !isError && rows.length === 0 && noFilters && (
        <EmptyState title={EMPTY.history.title} body={EMPTY.history.body} />
      )}
      {!isLoading && !isError && rows.length === 0 && !noFilters && (
        <EmptyState title="No matches for these filters." body="Try clearing or changing the filters." />
      )}

      {!isLoading && !isError && rows.length > 0 && (
        <TableContainer component={Card}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Position</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((job: MatchJobResponse) => (
                <TableRow
                  key={job.jobId}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => navigate(ROUTES.match(job.jobId))}
                >
                  <TableCell>{jdName(job.jdId)}</TableCell>
                  <TableCell>
                    <Chip label={job.status} size="small" color={STATUS_COLOR[job.status]} variant="outlined" />
                  </TableCell>
                  <TableCell>{formatDateTime(job.createdAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={data?.totalElements ?? 0}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={size}
            onRowsPerPageChange={(e) => {
              setSize(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 20, 50]}
          />
        </TableContainer>
      )}
    </>
  );
}
