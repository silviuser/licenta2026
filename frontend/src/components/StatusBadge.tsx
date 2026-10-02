import { Chip, Tooltip } from '@mui/material';
import type { ChipProps } from '@mui/material';
import type { ProcessingStatus } from '../api/types';
import { STATUS_LABEL } from '../lib/constants';

const COLOR: Record<ProcessingStatus, ChipProps['color']> = {
  PENDING: 'default',
  PROCESSING: 'info',
  READY: 'success',
  FAILED: 'error',
};

interface StatusBadgeProps {
  status: ProcessingStatus | null | undefined;
  error?: string | null;
  size?: ChipProps['size'];
}

/** Processing-status chip for CVs and JDs (REWORK 1 D26). */
export function StatusBadge({ status, error, size = 'small' }: StatusBadgeProps) {
  if (!status) {
    return <Chip label="—" size={size} variant="outlined" />;
  }
  const chip = (
    <Chip label={STATUS_LABEL[status] ?? status} size={size} color={COLOR[status]} variant="outlined" />
  );
  if (status === 'FAILED' && error) {
    return <Tooltip title={error}>{chip}</Tooltip>;
  }
  return chip;
}
