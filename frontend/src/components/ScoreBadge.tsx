import { Chip, Stack, Typography } from '@mui/material';
import { toPercentNumber } from '../lib/formatters';
import { scoreBand } from '../lib/scoreBand';

interface ScoreBadgeProps {
  score: number; // 0..1
  /**
   * Backend 3-class projection ('strong' | 'possible' | 'no'). Accepted for
   * backward compatibility but no longer drives the badge — the displayed
   * band is derived from the percentage (see scoreBand).
   */
  klass?: string;
  size?: 'sm' | 'lg';
}

/**
 * Big percentage + graded band chip (§14.2).
 *
 * The band (Excellent / Strong / Partial / Weak / Unsuitable) is computed from
 * the rounded percentage, so a 30% candidate no longer shares the "Strong"
 * label with a 70% one.
 * A11y: never colour-only — the band label text is always present, plus an aria-label.
 */
export function ScoreBadge({ score, size = 'lg' }: ScoreBadgeProps) {
  const percent = toPercentNumber(score);
  const band = scoreBand(percent);
  const ariaLabel = `Match score ${percent} percent, ${band.label}`;

  return (
    <Stack
      direction={size === 'lg' ? 'column' : 'row'}
      spacing={size === 'lg' ? 1 : 1.5}
      alignItems={size === 'lg' ? 'flex-start' : 'center'}
      aria-label={ariaLabel}
    >
      <Typography
        component="span"
        sx={{
          fontWeight: 700,
          lineHeight: 1,
          fontSize: size === 'lg' ? '3.5rem' : '1.5rem',
          color: band.color,
        }}
      >
        {percent}%
      </Typography>
      <Chip
        label={band.label}
        size={size === 'lg' ? 'medium' : 'small'}
        sx={{ bgcolor: band.color, color: '#fff', fontWeight: 600 }}
      />
    </Stack>
  );
}
