import { Box, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  body?: string;
  /** Optional CTA (e.g. an Upload button). */
  action?: ReactNode;
  icon?: ReactNode;
}

/** Friendly empty state (§8, §14.3): what it is + why it's empty + how to start. */
export function EmptyState({ title, body, action, icon }: EmptyStateProps) {
  return (
    <Box
      sx={{
        textAlign: 'center',
        py: 8,
        px: 3,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        borderStyle: 'dashed',
        bgcolor: 'background.paper',
      }}
    >
      <Stack spacing={2} alignItems="center">
        {icon}
        <Typography variant="h6">{title}</Typography>
        {body && (
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420 }}>
            {body}
          </Typography>
        )}
        {action}
      </Stack>
    </Box>
  );
}
