import { useMemo } from 'react';
import { Copy, Mail, Minus, Plus } from 'lucide-react';
import { Box, Button, Chip, Paper, Stack, Tooltip, Typography } from '@mui/material';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { CONTACT } from '../lib/constants';
import { buildMailto, formatAddressList, isMailtoWithinLimit } from '../lib/mailto';
import { useToast } from './toastContext';

export interface ContactCandidate {
  cvId: string;
  name: string;
  email: string | null;
}

interface ContactTopBarProps {
  /** Selected candidates, in rank order. */
  selected: ContactCandidate[];
  topN: number;
  maxN: number;
  isCustom: boolean;
  onTopNChange: (n: number) => void;
  onRemove: (cvId: string) => void;
  subject: string;
}

/**
 * Sticky "Contact top N" action bar (REWORK 4 D44/D47). Slides up when there are
 * candidates; respects prefers-reduced-motion. Copies addresses or opens a BCC
 * mailto (so candidates are not exposed to each other), excluding any selected
 * candidate without an email.
 */
export function ContactTopBar({
  selected,
  topN,
  maxN,
  isCustom,
  onTopNChange,
  onRemove,
  subject,
}: ContactTopBarProps) {
  const { showToast } = useToast();
  const reduceMotion = useReducedMotion();

  const withEmail = useMemo(() => selected.filter((c) => c.email), [selected]);
  const emails = useMemo(() => withEmail.map((c) => c.email as string), [withEmail]);
  const withoutEmailCount = selected.length - withEmail.length;

  const mailtoUrl = buildMailto({ bcc: emails, subject });
  const mailtoTooLong = !isMailtoWithinLimit(mailtoUrl);
  const canEmail = emails.length > 0 && !mailtoTooLong;

  async function copyAddresses() {
    try {
      await navigator.clipboard.writeText(formatAddressList(emails));
      showToast(CONTACT.copied, 'success');
    } catch {
      showToast(CONTACT.copyFailed, 'error');
    }
  }

  return (
    <Box
      component={motion.div}
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      sx={{ position: 'sticky', bottom: 16, zIndex: 5, mt: 2 }}
    >
      <Paper elevation={6} sx={{ p: 2, borderRadius: 2 }}>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="subtitle2">{CONTACT.topN}</Typography>
            <Stack direction="row" alignItems="center">
              <Button
                size="small"
                aria-label="Decrease selection"
                disabled={topN <= 0}
                onClick={() => onTopNChange(Math.max(0, topN - 1))}
                sx={{ minWidth: 32 }}
              >
                <Minus size={16} />
              </Button>
              <Typography variant="body1" sx={{ minWidth: 24, textAlign: 'center', fontWeight: 600 }}>
                {topN}
              </Typography>
              <Button
                size="small"
                aria-label="Increase selection"
                disabled={topN >= maxN}
                onClick={() => onTopNChange(Math.min(maxN, topN + 1))}
                sx={{ minWidth: 32 }}
              >
                <Plus size={16} />
              </Button>
            </Stack>
            {isCustom && <Chip label="custom" size="small" color="info" variant="outlined" />}
            <Box sx={{ flexGrow: 1 }} />
            <Typography variant="body2" color="text.secondary">
              {CONTACT.selectedSummary(selected.length, withEmail.length)}
            </Typography>
            {withoutEmailCount > 0 && (
              <Chip
                label={CONTACT.withoutEmail(withoutEmailCount)}
                size="small"
                color="warning"
                variant="outlined"
              />
            )}
          </Stack>

          {selected.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <AnimatePresence initial={false}>
                {selected.map((c, i) => (
                  <Box
                    key={c.cvId}
                    component={motion.div}
                    layout={!reduceMotion}
                    initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ duration: 0.18, delay: reduceMotion ? 0 : Math.min(i * 0.03, 0.3) }}
                  >
                    <Chip
                      label={c.email ? `${c.name} · ${c.email}` : `${c.name} · no email`}
                      size="small"
                      color={c.email ? 'default' : 'warning'}
                      variant={c.email ? 'filled' : 'outlined'}
                      onDelete={() => onRemove(c.cvId)}
                    />
                  </Box>
                ))}
              </AnimatePresence>
            </Stack>
          )}

          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              size="small"
              startIcon={<Copy size={16} />}
              disabled={emails.length === 0}
              onClick={copyAddresses}
            >
              {CONTACT.copyAddresses}
            </Button>
            <Tooltip title={mailtoTooLong ? CONTACT.tooLong : ''} disableHoverListener={!mailtoTooLong}>
              <span>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<Mail size={16} />}
                  component={canEmail ? 'a' : 'button'}
                  href={canEmail ? mailtoUrl : undefined}
                  disabled={!canEmail}
                >
                  {CONTACT.openInEmail}
                </Button>
              </span>
            </Tooltip>
            {mailtoTooLong && (
              <Typography variant="caption" color="warning.main">
                {CONTACT.tooLong}
              </Typography>
            )}
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
}
