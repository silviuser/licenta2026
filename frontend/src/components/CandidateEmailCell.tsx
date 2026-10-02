import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { Box, CircularProgress, IconButton, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import type { CvResponse, EmailSource } from '../api/types';
import { useUpdateCvEmail } from '../hooks/useCvs';
import { CONTACT } from '../lib/constants';
import { errorMessage } from '../lib/errorMessages';
import { useToast } from './toastContext';
import { EmailSourceBadge } from './EmailSourceBadge';
import { MailtoButton } from './MailtoButton';

const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

interface CandidateEmailCellProps {
  cvId: string;
  email: string | null; // effective email
  source: EmailSource;
  subject: string; // mailto subject
  /** Reflect the manual edit in the parent view (match snapshot vs live list). */
  onUpdated?: (cv: CvResponse) => void;
}

/**
 * One candidate's email surface (REWORK 4 D44/D45): resolved address + source
 * badge + inline edit + mailto. Editing sets/clears the CV's manual email;
 * clearing reverts to the extracted address. A subtle checkmark confirms a save.
 */
export function CandidateEmailCell({ cvId, email, source, subject, onUpdated }: CandidateEmailCellProps) {
  const { showToast } = useToast();
  const update = useUpdateCvEmail();
  const reduceMotion = useReducedMotion();

  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const [justSaved, setJustSaved] = useState(false);

  const trimmed = value.trim();
  const invalid = trimmed.length > 0 && !EMAIL_RE.test(trimmed);

  function startEdit() {
    setValue(source === 'MANUAL' ? (email ?? '') : '');
    setEditing(true);
  }

  function save() {
    if (invalid) return;
    update.mutate(
      { cvId, manualEmail: trimmed.length > 0 ? trimmed : null },
      {
        onSuccess: (cv) => {
          setEditing(false);
          setJustSaved(true);
          showToast(CONTACT.saved, 'success');
          onUpdated?.(cv);
          window.setTimeout(() => setJustSaved(false), 1500);
        },
        onError: (err) => showToast(errorMessage(err), 'error'),
      },
    );
  }

  if (editing) {
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField
          size="small"
          autoFocus
          value={value}
          label={CONTACT.emailLabel}
          placeholder="name@example.com"
          error={invalid}
          helperText={invalid ? CONTACT.invalidEmail : ' '}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save();
            if (e.key === 'Escape') setEditing(false);
          }}
          sx={{ minWidth: 240 }}
        />
        <Tooltip title={CONTACT.save}>
          <span>
            <IconButton
              size="small"
              color="primary"
              aria-label={CONTACT.save}
              disabled={invalid || update.isPending}
              onClick={save}
            >
              {update.isPending ? <CircularProgress size={16} /> : <Check size={18} />}
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title={CONTACT.cancel}>
          <IconButton
            size="small"
            aria-label={CONTACT.cancel}
            disabled={update.isPending}
            onClick={() => setEditing(false)}
          >
            <X size={18} />
          </IconButton>
        </Tooltip>
      </Stack>
    );
  }

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      {email ? (
        <Typography variant="body2">{email}</Typography>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No email
        </Typography>
      )}
      <EmailSourceBadge source={source} />
      <Tooltip title={CONTACT.editTooltip}>
        <IconButton size="small" aria-label={CONTACT.editTooltip} onClick={startEdit}>
          <Pencil size={15} />
        </IconButton>
      </Tooltip>
      <MailtoButton email={email} subject={subject} onNoEmail={startEdit} />
      <AnimatePresence>
        {justSaved && (
          <motion.span
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{ display: 'inline-flex' }}
          >
            <Box component="span" sx={{ color: 'success.main', display: 'inline-flex' }} aria-hidden>
              <Check size={16} />
            </Box>
          </motion.span>
        )}
      </AnimatePresence>
    </Stack>
  );
}
