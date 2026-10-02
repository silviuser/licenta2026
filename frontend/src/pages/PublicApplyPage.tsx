import { useState } from 'react';
import type { FormEvent } from 'react';
import { CheckCircle2, FileText } from 'lucide-react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useParams } from 'react-router-dom';
import { getPublicJob, submitApplication } from '../api/public';
import type { PublicApplyResponse } from '../api/types';
import { AuroraBackground } from '../components/AuroraBackground';
import { FileUpload } from '../components/FileUpload';
import { Reveal } from '../components/motion/Reveal';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { Loading } from '../components/states/Loading';
import { PUBLIC_APPLY } from '../lib/constants';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^[+]?[0-9 ()./-]{6,32}$/;

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <AuroraBackground>
      <Reveal style={{ width: '100%', maxWidth: 560 }}>
        <Card sx={{ width: '100%' }}>
          <CardContent sx={{ p: 4 }}>{children}</CardContent>
        </Card>
      </Reveal>
    </AuroraBackground>
  );
}

export function PublicApplyPage() {
  const { token = '' } = useParams<{ token: string }>();

  const job = useQuery({
    queryKey: ['public-apply', token],
    queryFn: () => getPublicJob(token),
    enabled: Boolean(token),
    retry: false,
  });

  const submit = useMutation({
    mutationFn: (file: File) =>
      submitApplication(token, { name: name.trim(), email: email.trim(), phone: phone.trim(), file }),
  });

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [touched, setTouched] = useState(false);
  const [result, setResult] = useState<PublicApplyResponse | null>(null);

  if (job.isLoading) {
    return (
      <Shell>
        <Loading />
      </Shell>
    );
  }

  // A generic 404 means the link is disabled or was regenerated (D38).
  if (job.isError) {
    const status = job.error instanceof AxiosError ? job.error.response?.status : undefined;
    if (status === 404) {
      return (
        <Shell>
          <Typography variant="h5" gutterBottom>
            {PUBLIC_APPLY.unavailableTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {PUBLIC_APPLY.unavailableBody}
          </Typography>
        </Shell>
      );
    }
    return (
      <Shell>
        <ErrorAlert error={job.error} onRetry={() => job.refetch()} />
      </Shell>
    );
  }

  if (result) {
    const received = result.status === 'RECEIVED';
    return (
      <Shell>
        <Stack spacing={2} alignItems="center" textAlign="center">
          <Box sx={{ color: 'success.main', display: 'flex' }}>
            <CheckCircle2 size={56} strokeWidth={1.5} />
          </Box>
          <Typography variant="h5">
            {received ? PUBLIC_APPLY.receivedTitle : PUBLIC_APPLY.updatedTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {received ? PUBLIC_APPLY.receivedBody : PUBLIC_APPLY.updatedBody}
          </Typography>
        </Stack>
      </Shell>
    );
  }

  const data = job.data!;
  const nameError = touched && name.trim().length === 0;
  const emailError = touched && !EMAIL_RE.test(email.trim());
  const phoneError = touched && !PHONE_RE.test(phone.trim());
  const fileError = touched && !file;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    const valid =
      name.trim().length > 0 &&
      EMAIL_RE.test(email.trim()) &&
      PHONE_RE.test(phone.trim()) &&
      file != null;
    if (!valid) return;
    submit.mutate(file as File, { onSuccess: (res) => setResult(res) });
  }

  return (
    <Shell>
      <Typography variant="overline" color="text.secondary">
        {PUBLIC_APPLY.appName}
      </Typography>
      <Typography variant="h4" sx={{ mb: 0.5 }}>
        {data.jobTitle}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {PUBLIC_APPLY.intro}
      </Typography>

      {data.jobDescription && (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ whiteSpace: 'pre-wrap', mb: 3, pb: 2, borderBottom: 1, borderColor: 'divider' }}
        >
          {data.jobDescription}
        </Typography>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <Stack spacing={2}>
          {submit.isError && <ErrorAlert error={submit.error} title="Could not submit" />}

          <TextField
            label={PUBLIC_APPLY.name}
            value={name}
            onChange={(e) => setName(e.target.value)}
            error={nameError}
            helperText={nameError ? PUBLIC_APPLY.invalidName : ' '}
            required
            fullWidth
          />
          <TextField
            label={PUBLIC_APPLY.email}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={emailError}
            helperText={emailError ? PUBLIC_APPLY.invalidEmail : ' '}
            required
            fullWidth
          />
          <TextField
            label={PUBLIC_APPLY.phone}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            error={phoneError}
            helperText={phoneError ? PUBLIC_APPLY.invalidPhone : ' '}
            required
            fullWidth
          />

          <FileUpload uploading={submit.isPending} onFile={setFile} />
          {file && (
            <Chip
              icon={<FileText size={14} />}
              label={file.name}
              variant="outlined"
              onDelete={() => setFile(null)}
              sx={{ alignSelf: 'flex-start' }}
            />
          )}
          {fileError && (
            <Typography variant="body2" color="error.main">
              {PUBLIC_APPLY.invalidFile}
            </Typography>
          )}

          <Button type="submit" variant="contained" size="large" disabled={submit.isPending}>
            {submit.isPending ? PUBLIC_APPLY.submitting : PUBLIC_APPLY.submit}
          </Button>
        </Stack>
      </form>
    </Shell>
  );
}
