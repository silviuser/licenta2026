import { useState } from 'react';
import { Info } from 'lucide-react';
import { Box, Divider, IconButton, Popover, Stack, Tooltip, Typography } from '@mui/material';
import { useNlpInfo } from '../hooks/useNlpInfo';

/** Small ops widget surfacing NLP versions + the placeholder caveat (§4). */
export function NlpInfoWidget() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { data, isLoading, isError } = useNlpInfo();

  const pipelineVersion =
    typeof data?.pipeline_version === 'string' ? data.pipeline_version : undefined;
  const caveat = typeof data?.placeholder_caveat === 'string' ? data.placeholder_caveat : undefined;

  return (
    <>
      <Tooltip title="NLP service info">
        <IconButton aria-label="NLP service info" onClick={(e) => setAnchor(e.currentTarget)}>
          <Info size={18} />
        </IconButton>
      </Tooltip>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Box sx={{ p: 2, maxWidth: 320 }}>
          <Typography variant="h6" gutterBottom>
            NLP service
          </Typography>
          <Divider sx={{ mb: 1.5 }} />
          {isLoading && (
            <Typography variant="body2" color="text.secondary">
              Loading…
            </Typography>
          )}
          {isError && (
            <Typography variant="body2" color="text.secondary">
              Service info unavailable.
            </Typography>
          )}
          {data && (
            <Stack spacing={1}>
              {pipelineVersion && (
                <Typography variant="body2">
                  <strong>Pipeline:</strong> {pipelineVersion}
                </Typography>
              )}
              {caveat && (
                <Typography variant="body2" color="info.main">
                  {caveat}
                </Typography>
              )}
            </Stack>
          )}
        </Box>
      </Popover>
    </>
  );
}
