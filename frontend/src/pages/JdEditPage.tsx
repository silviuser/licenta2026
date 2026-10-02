import { useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowLeft } from 'lucide-react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import type { JdRequest, RequirementInput } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { RequirementEditor } from '../components/RequirementEditor';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { useToast } from '../components/toastContext';
import { useCreateJd } from '../hooks/useJds';
import { CTA, ROUTES, SUCCESS } from '../lib/constants';

/**
 * Create a position. Requirements are optional (REWORK 1 D18): leave them empty
 * and the backend extracts them from the description in the background.
 */
export function JdEditPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const createJd = useCreateJd();

  const [title, setTitle] = useState('');
  const [descriptionText, setDescriptionText] = useState('');
  const [requirements, setRequirements] = useState<RequirementInput[]>([]);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [attempted, setAttempted] = useState(false);

  const titleInvalid = attempted && title.trim().length === 0;
  const requirementsInvalid = requirements.some((r) => r.text.trim().length === 0);
  const willAutoExtract = requirements.length === 0 && descriptionText.trim().length > 0;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setAttempted(true);
    setSubmitError(null);
    if (title.trim().length === 0 || requirementsInvalid) return;

    const body: JdRequest = {
      title: title.trim(),
      descriptionText: descriptionText.trim() || null,
      requirements: requirements.map((r) => ({
        text: r.text.trim(),
        importance: r.importance,
        skillUri: r.skillUri || null,
        skillLabel: r.skillLabel?.trim() || null,
        confidence: r.confidence ?? 0.5,
      })),
    };

    createJd.mutate(body, {
      onSuccess: (jd) => {
        showToast(SUCCESS.jdSaved, 'success');
        navigate(ROUTES.jd(jd.id));
      },
      onError: (err) => setSubmitError(err),
    });
  }

  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      <Button startIcon={<ArrowLeft size={16} />} onClick={() => navigate(ROUTES.dashboard)} sx={{ mb: 2 }}>
        {CTA.backToDashboard}
      </Button>

      <PageHeader title="New position" />

      <Stack spacing={3}>
        {submitError != null && <ErrorAlert error={submitError} title="Could not save" />}

        <Card>
          <CardContent>
            <Stack spacing={2}>
              <TextField
                label="Title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                fullWidth
                error={titleInvalid}
                helperText={titleInvalid ? 'A title is required.' : undefined}
              />
              <TextField
                label="Description"
                value={descriptionText}
                onChange={(e) => setDescriptionText(e.target.value)}
                fullWidth
                multiline
                minRows={4}
                placeholder="Paste the full job description here."
              />
            </Stack>
          </CardContent>
        </Card>

        <Box>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Requirements
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Leave this empty to auto-extract the requirements from the description — you can edit
            them afterwards. Or add them manually below.
          </Typography>
          {willAutoExtract && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Requirements will be extracted from the description in the background.
            </Alert>
          )}
          <RequirementEditor value={requirements} onChange={setRequirements} allowEmpty />
        </Box>

        <Divider />

        <Stack direction="row" spacing={2} justifyContent="flex-end">
          <Button color="inherit" onClick={() => navigate(ROUTES.dashboard)} disabled={createJd.isPending}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={createJd.isPending}>
            {createJd.isPending ? 'Saving…' : CTA.createJd}
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
