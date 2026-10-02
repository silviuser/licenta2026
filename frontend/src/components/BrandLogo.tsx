import { Box, Stack, Typography } from '@mui/material';

interface BrandLogoProps {
  /** Mark height in px. */
  size?: number;
  withWordmark?: boolean;
}

/**
 * HR Helper mark (logo V2): two bars — candidate and position — joined by a
 * bridge. Bars are fixed brand colours (indigo #5e6ad2, violet #8b5cf6); the
 * bridge uses currentColor so it adapts to dark/light mode.
 */
export function BrandLogo({ size = 26, withWordmark = true }: BrandLogoProps) {
  const mark = (
    <Box
      component="svg"
      viewBox="0 0 44 44"
      aria-hidden
      sx={{ width: size, height: size, display: 'block', color: 'text.primary', flexShrink: 0 }}
    >
      <path d="M12 9v26" stroke="#5e6ad2" strokeWidth="6" strokeLinecap="round" />
      <path d="M32 9v26" stroke="#8b5cf6" strokeWidth="6" strokeLinecap="round" />
      <path d="M12 22h20" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
    </Box>
  );

  if (!withWordmark) return mark;

  return (
    <Stack direction="row" spacing={1.25} alignItems="center">
      {mark}
      <Typography
        variant="h6"
        component="span"
        sx={{ fontWeight: 600, letterSpacing: '-0.02em', color: 'text.primary', lineHeight: 1 }}
      >
        HR Helper
      </Typography>
    </Stack>
  );
}
