import { Alert, AlertTitle, Button } from '@mui/material';
import { errorMessage } from '../../lib/errorMessages';

interface ErrorAlertProps {
  /** Any thrown value; message is derived via errorMessage(). */
  error?: unknown;
  /** Optional explicit message (overrides `error`). */
  message?: string;
  title?: string;
  onRetry?: () => void;
}

export function ErrorAlert({ error, message, title = 'Error', onRetry }: ErrorAlertProps) {
  const text = message ?? errorMessage(error);
  return (
    <Alert
      severity="error"
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
    >
      <AlertTitle>{title}</AlertTitle>
      {text}
    </Alert>
  );
}
