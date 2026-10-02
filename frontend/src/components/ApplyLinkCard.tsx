import { useState } from 'react';
import { Copy, Link2, RefreshCw } from 'lucide-react';
import {
  Box,
  Button,
  Card,
  CardContent,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  useApplyLink,
  useGenerateApplyLink,
  useSetApplyLinkEnabled,
} from '../hooks/useApplyLink';
import { APPLY_LINK } from '../lib/constants';
import { errorMessage } from '../lib/errorMessages';
import { ConfirmDialog } from './ConfirmDialog';
import { Loading } from './states/Loading';
import { useToast } from './toastContext';

/** Recruiter-facing apply-link section on the JD page (REWORK 3 §3.2). */
export function ApplyLinkCard({ jdId }: { jdId: string }) {
  const { showToast } = useToast();
  const link = useApplyLink(jdId);
  const generate = useGenerateApplyLink(jdId);
  const setEnabled = useSetApplyLinkEnabled(jdId);

  const [regenerateOpen, setRegenerateOpen] = useState(false);

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      showToast(APPLY_LINK.copied, 'success');
    } catch {
      showToast('Could not copy the link', 'error');
    }
  }

  function handleGenerate() {
    generate.mutate(undefined, {
      onError: (err) => showToast(errorMessage(err), 'error'),
    });
  }

  function handleToggle(enabled: boolean) {
    setEnabled.mutate(enabled, {
      onError: (err) => showToast(errorMessage(err), 'error'),
    });
  }

  function handleRegenerate() {
    generate.mutate(undefined, {
      onSuccess: () => {
        setRegenerateOpen(false);
        showToast('Application link regenerated', 'success');
      },
      onError: (err) => {
        setRegenerateOpen(false);
        showToast(errorMessage(err), 'error');
      },
    });
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {APPLY_LINK.title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {APPLY_LINK.description}
        </Typography>

        {link.isLoading ? (
          <Loading />
        ) : !link.data?.exists || !link.data.url ? (
          <Button
            variant="contained"
            startIcon={<Link2 size={16} />}
            onClick={handleGenerate}
            disabled={generate.isPending}
          >
            {generate.isPending ? 'Generating…' : APPLY_LINK.generate}
          </Button>
        ) : (
          <Stack spacing={2}>
            <TextField
              value={link.data.url}
              label="Public apply link"
              fullWidth
              InputProps={{
                readOnly: true,
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title={APPLY_LINK.copy}>
                      <IconButton
                        aria-label={APPLY_LINK.copy}
                        edge="end"
                        onClick={() => copy(link.data!.url as string)}
                      >
                        <Copy size={16} />
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ),
              }}
            />

            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 1,
              }}
            >
              <FormControlLabel
                control={
                  <Switch
                    checked={link.data.enabled}
                    onChange={(e) => handleToggle(e.target.checked)}
                    disabled={setEnabled.isPending}
                  />
                }
                label={link.data.enabled ? APPLY_LINK.active : APPLY_LINK.inactive}
              />
              <Button
                color="inherit"
                startIcon={<RefreshCw size={16} />}
                onClick={() => setRegenerateOpen(true)}
                disabled={generate.isPending}
              >
                {APPLY_LINK.regenerate}
              </Button>
            </Box>

            <Typography variant="caption" color={link.data.enabled ? 'text.secondary' : 'warning.main'}>
              {link.data.enabled ? APPLY_LINK.enabledHint : APPLY_LINK.disabledHint}
            </Typography>
          </Stack>
        )}
      </CardContent>

      <ConfirmDialog
        open={regenerateOpen}
        title={APPLY_LINK.regenerateTitle}
        body={APPLY_LINK.regenerateBody}
        confirmLabel={APPLY_LINK.regenerate}
        destructive
        loading={generate.isPending}
        onConfirm={handleRegenerate}
        onCancel={() => setRegenerateOpen(false)}
      />
    </Card>
  );
}
