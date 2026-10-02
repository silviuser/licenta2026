import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button, Card, CardContent, Link, Stack, TextField, Typography } from '@mui/material';
import { Link as RouterLink, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { AuroraBackground } from '../components/AuroraBackground';
import { BrandLogo } from '../components/BrandLogo';
import { Reveal } from '../components/motion/Reveal';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { CTA, ROUTES } from '../lib/constants';

const MIN_PASSWORD = 8;

export function RegisterPage() {
  const { registerAndLogin, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (isAuthenticated) {
    return <Navigate to={ROUTES.dashboard} replace />;
  }

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const canSubmit = email && fullName && password.length >= MIN_PASSWORD;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      // Auto sign-in after registration → land on the dashboard.
      await registerAndLogin(email, password, fullName);
      navigate(ROUTES.dashboard, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuroraBackground>
      <Reveal style={{ width: '100%', maxWidth: 420 }}>
      <Card sx={{ width: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 0.5 }}>
            <BrandLogo withWordmark={false} size={30} />
            <Typography variant="h4">Create account</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Set up your recruiter account.
          </Typography>

          <form onSubmit={handleSubmit} noValidate>
            <Stack spacing={2}>
              {error != null && <ErrorAlert error={error} title="Registration failed" />}
              <TextField
                label="Full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                required
                fullWidth
                autoFocus
              />
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                fullWidth
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                fullWidth
                error={passwordTooShort}
                helperText={
                  passwordTooShort
                    ? `Use at least ${MIN_PASSWORD} characters.`
                    : `At least ${MIN_PASSWORD} characters.`
                }
              />
              <Button type="submit" variant="contained" size="large" disabled={submitting || !canSubmit}>
                {submitting ? 'Creating account…' : CTA.createAccount}
              </Button>
            </Stack>
          </form>

          <Typography variant="body2" sx={{ mt: 3, textAlign: 'center' }}>
            Already have an account?{' '}
            <Link component={RouterLink} to={ROUTES.login}>
              {CTA.signIn}
            </Link>
          </Typography>
        </CardContent>
      </Card>
      </Reveal>
    </AuroraBackground>
  );
}
