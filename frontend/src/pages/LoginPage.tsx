import { useState } from 'react';
import type { FormEvent } from 'react';
import { Button, Card, CardContent, Link, Stack, TextField, Typography } from '@mui/material';
import { Link as RouterLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { AuroraBackground } from '../components/AuroraBackground';
import { BrandLogo } from '../components/BrandLogo';
import { Reveal } from '../components/motion/Reveal';
import { ErrorAlert } from '../components/states/ErrorAlert';
import { CTA, ROUTES } from '../lib/constants';

interface LocationState {
  from?: { pathname: string };
}

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const from = (location.state as LocationState | null)?.from?.pathname ?? ROUTES.dashboard;

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
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
            <Typography variant="h4">HR Helper</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Sign in to match CVs against job descriptions.
          </Typography>

          <form onSubmit={handleSubmit} noValidate>
            <Stack spacing={2}>
              {error != null && <ErrorAlert error={error} title="Sign in failed" />}
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                fullWidth
                autoFocus
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={submitting || !email || !password}
              >
                {submitting ? 'Signing in…' : CTA.signIn}
              </Button>
            </Stack>
          </form>

          <Typography variant="body2" sx={{ mt: 3, textAlign: 'center' }}>
            No account?{' '}
            <Link component={RouterLink} to={ROUTES.register}>
              {CTA.createAccount}
            </Link>
          </Typography>
        </CardContent>
      </Card>
      </Reveal>
    </AuroraBackground>
  );
}
