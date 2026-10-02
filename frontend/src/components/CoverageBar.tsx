import { Box, LinearProgress, Stack, Typography } from '@mui/material';
import { toPercent, toPercentNumber } from '../lib/formatters';

interface CoverageBarProps {
  label: string;
  value: number | null; // 0..1
  /** 'required' uses error when below threshold, else success; 'nice' uses info. */
  variant: 'required' | 'nice';
  /** Threshold below which required coverage is flagged (error). */
  threshold?: number;
}

/** Coverage as a LinearProgress with the percentage alongside (§14.2). */
export function CoverageBar({ label, value, variant, threshold = 0.5 }: CoverageBarProps) {
  const pct = toPercentNumber(value);
  const color =
    variant === 'nice' ? 'info' : (value ?? 0) >= threshold ? 'success' : 'error';

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {toPercent(value)}
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={pct}
        color={color}
        aria-label={`${label}: ${pct} percent`}
        sx={{ height: 8, borderRadius: 1 }}
      />
    </Box>
  );
}
