import { Box, CircularProgress, Typography } from '@mui/material';
import { LOADING } from '../../lib/constants';

export function Loading({ label = LOADING.short }: { label?: string }) {
  return (
    <Box
      role="status"
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        py: 6,
      }}
    >
      <CircularProgress />
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}
