import type { ReactNode } from 'react';
import { Box } from '@mui/material';
import { alpha, keyframes, useTheme } from '@mui/material/styles';

const drift = keyframes`
  from { transform: translate3d(-6%, -4%, 0) scale(1); }
  to   { transform: translate3d(6%, 5%, 0) scale(1.15); }
`;

const driftAlt = keyframes`
  from { transform: translate3d(5%, 6%, 0) scale(1.1); }
  to   { transform: translate3d(-6%, -5%, 0) scale(0.95); }
`;

/**
 * Full-viewport centered shell with slow-drifting indigo/violet aurora glows
 * (login / register / public apply). Pure CSS; honours prefers-reduced-motion.
 */
export function AuroraBackground({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const dark = theme.palette.mode === 'dark';

  const glowSx = {
    position: 'absolute',
    borderRadius: '50%',
    pointerEvents: 'none',
    '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
  } as const;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
        position: 'relative',
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
    >
      <Box
        aria-hidden
        sx={{
          ...glowSx,
          width: 720,
          height: 720,
          top: '-18%',
          left: '-12%',
          filter: 'blur(90px)',
          background: `radial-gradient(circle, ${alpha('#5e6ad2', dark ? 0.28 : 0.16)} 0%, transparent 65%)`,
          animation: `${drift} 22s ease-in-out infinite alternate`,
        }}
      />
      <Box
        aria-hidden
        sx={{
          ...glowSx,
          width: 640,
          height: 640,
          bottom: '-22%',
          right: '-10%',
          filter: 'blur(100px)',
          background: `radial-gradient(circle, ${alpha('#8b5cf6', dark ? 0.22 : 0.12)} 0%, transparent 65%)`,
          animation: `${driftAlt} 28s ease-in-out infinite alternate`,
        }}
      />
      <Box sx={{ position: 'relative', width: '100%', display: 'flex', justifyContent: 'center' }}>
        {children}
      </Box>
    </Box>
  );
}
