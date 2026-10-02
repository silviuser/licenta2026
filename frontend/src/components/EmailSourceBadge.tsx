import { Chip } from '@mui/material';
import type { EmailSource } from '../api/types';
import { EMAIL_SOURCE_LABEL } from '../lib/constants';

const COLOR: Record<EmailSource, 'info' | 'success' | 'default' | 'warning'> = {
  CANDIDATE_FORM: 'info',
  MANUAL: 'success',
  EXTRACTED: 'default',
  NONE: 'warning',
};

/** Discreet badge for where a candidate's email came from (REWORK 4 D42). */
export function EmailSourceBadge({ source }: { source: EmailSource }) {
  return (
    <Chip
      label={EMAIL_SOURCE_LABEL[source]}
      size="small"
      variant="outlined"
      color={COLOR[source]}
    />
  );
}
