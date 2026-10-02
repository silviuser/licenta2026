import { Mail } from 'lucide-react';
import { Button, Tooltip } from '@mui/material';
import { CONTACT } from '../lib/constants';
import { buildMailto } from '../lib/mailto';

interface MailtoButtonProps {
  email: string | null;
  subject: string;
  /** Called when the (disabled) button is clicked with no address — e.g. open the editor. */
  onNoEmail?: () => void;
  label?: string;
}

/**
 * Per-candidate Email action (REWORK 4 D44). Opens a pre-filled `mailto:`; when
 * there is no address it is disabled with a tooltip that points to manual editing.
 */
export function MailtoButton({ email, subject, onNoEmail, label = CONTACT.email }: MailtoButtonProps) {
  if (!email) {
    return (
      <Tooltip title={CONTACT.noEmailTooltip}>
        <span>
          <Button
            size="small"
            startIcon={<Mail size={16} />}
            disabled
            aria-disabled
            // The disabled button swallows clicks, so expose the editor affordance
            // via the wrapping span instead.
            onClick={onNoEmail}
          >
            {label}
          </Button>
        </span>
      </Tooltip>
    );
  }
  return (
    <Button
      size="small"
      startIcon={<Mail size={16} />}
      component="a"
      href={buildMailto({ to: email, subject })}
      aria-label={`Email ${email}`}
    >
      {label}
    </Button>
  );
}
