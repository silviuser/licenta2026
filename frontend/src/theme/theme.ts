import { alpha, createTheme, darken, lighten } from '@mui/material/styles';
import type { PaletteMode, Theme } from '@mui/material';

/**
 * Single source of truth for the design tokens.
 *
 * Design language mirrored from linear.app (captured live on 2026-06-06):
 * near-black page, hairline alpha borders instead of shadows, pill buttons,
 * tight letter-spacing on headings, glass-blur sticky nav, indigo accent.
 * Components read tokens via the theme / palette keys and `sx` — no
 * hardcoded colours, radii or spacing in components.
 */

const ACCENT = {
  main: '#5e6ad2', // Linear brand indigo
  light: '#6c77dd', // hover (dark mode lifts up)
  dark: '#4f5ac2', // active / hover on light bg
};

const DARK = {
  bg: '#08090a', // page background (linear.app body)
  paper: '#0f1011', // card / panel surface
  elevated: '#16171a', // menus, dialogs, tooltips
  divider: 'rgba(255, 255, 255, 0.08)', // hairline borders
  hover: 'rgba(255, 255, 255, 0.05)', // hover fills / chips
  textPrimary: '#f7f8f8',
  textSecondary: '#8a8f98', // nav / muted
};

const LIGHT = {
  bg: '#f9f8f9',
  paper: '#ffffff',
  elevated: '#ffffff',
  divider: '#e9e8ea',
  hover: 'rgba(0, 0, 0, 0.04)',
  textPrimary: '#0f1011',
  textSecondary: '#6f6e77',
};

export function buildTheme(mode: PaletteMode): Theme {
  const t = mode === 'dark' ? DARK : LIGHT;
  const sem =
    mode === 'dark'
      ? { success: '#27a644', warning: '#f2994a', error: '#f34e52', info: '#4ea7fc' }
      : { success: '#1f923e', warning: '#d97916', error: '#e5484d', info: '#2d7ff0' };
  // Linear badge: alpha-tinted pill with a bright label, never a solid fill.
  const tintChip = (color: string) => ({
    backgroundColor: alpha(color, mode === 'dark' ? 0.16 : 0.12),
    color: mode === 'dark' ? lighten(color, 0.4) : darken(color, 0.25),
  });
  const focusRing = `0 0 0 3px ${alpha(ACCENT.main, 0.25)}`;
  const popoverShadow =
    mode === 'dark' ? '0px 16px 40px rgba(0, 0, 0, 0.55)' : '0px 12px 32px rgba(0, 0, 0, 0.12)';

  return createTheme({
    palette: {
      mode,
      primary: {
        main: ACCENT.main,
        light: ACCENT.light,
        dark: ACCENT.dark,
        contrastText: '#ffffff',
      },
      secondary: { main: '#8b5cf6' },
      background: { default: t.bg, paper: t.paper },
      text: { primary: t.textPrimary, secondary: t.textSecondary },
      divider: t.divider,
      // Semantic — drives ScoreBadge / CoverageBar / History rows via lib/scoreColor.ts
      success: { main: sem.success },
      warning: { main: sem.warning },
      error: { main: sem.error },
      info: { main: sem.info },
      action: { hover: t.hover },
    },

    shape: {
      borderRadius: 8,
    },

    spacing: 8, // MUI default 8px grid (explicit for clarity)

    typography: {
      fontFamily: ['Inter', 'Roboto', 'system-ui', 'Arial', 'sans-serif'].join(','),
      // Linear headings: medium weight, tight letter-spacing
      h4: { fontSize: '1.625rem', fontWeight: 600, letterSpacing: '-0.02em' }, // 26px — page titles
      h5: { fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.015em' }, // 20px
      h6: { fontSize: '1.0625rem', fontWeight: 600, letterSpacing: '-0.01em' }, // 17px — card titles
      subtitle1: { fontWeight: 500 },
      subtitle2: { fontWeight: 500 },
      body1: { fontSize: '1rem' }, // 16px
      body2: { fontSize: '0.875rem' }, // 14px — secondary
      caption: { fontSize: '0.75rem' }, // 12px — metadata
      button: { textTransform: 'none', fontWeight: 500, fontSize: '0.8125rem', letterSpacing: 0 }, // 13px Linear UI
    },

    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            WebkitFontSmoothing: 'antialiased',
            MozOsxFontSmoothing: 'grayscale',
          },
          '::selection': { backgroundColor: alpha(ACCENT.main, 0.4) },
          ...(mode === 'dark' && {
            '*::-webkit-scrollbar': { width: 10, height: 10 },
            '*::-webkit-scrollbar-track': { background: 'transparent' },
            '*::-webkit-scrollbar-thumb': {
              backgroundColor: 'rgba(255, 255, 255, 0.14)',
              borderRadius: 8,
              border: '2px solid transparent',
              backgroundClip: 'content-box',
            },
          }),
        },
      },

      // Discrete elevation: flat surfaces with hairline borders, no heavy shadows.
      MuiPaper: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: ({ theme }) => ({
            backgroundImage: 'none',
            border: `1px solid ${theme.palette.divider}`,
          }),
        },
      },
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 12,
          }),
        },
      },

      // Popovers float on the elevated surface with one soft shadow.
      MuiDialog: {
        styleOverrides: {
          paper: {
            backgroundColor: t.elevated,
            border: `1px solid ${t.divider}`,
            borderRadius: 12,
            boxShadow: popoverShadow,
          },
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: {
            backgroundColor: t.elevated,
            border: `1px solid ${t.divider}`,
            borderRadius: 10,
            boxShadow: popoverShadow,
          },
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: {
            backgroundColor: t.elevated,
            border: `1px solid ${t.divider}`,
            borderRadius: 10,
            boxShadow: popoverShadow,
          },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: { backgroundImage: 'none', border: 'none', borderRight: `1px solid ${t.divider}` },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            backgroundColor: mode === 'dark' ? '#1d1e21' : '#0f1011',
            border: `1px solid ${mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'transparent'}`,
            color: '#f7f8f8',
            fontSize: '0.75rem',
            borderRadius: 6,
          },
        },
      },

      // Sticky glass nav: transparent + blur, hairline bottom border (linear.app header).
      MuiAppBar: {
        defaultProps: { elevation: 0, color: 'transparent' },
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            backgroundColor: alpha(t.bg, 0.75),
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            borderBottom: `1px solid ${t.divider}`,
            color: t.textPrimary,
          },
        },
      },

      // Pill buttons (Linear CTA), 13px, subtle inner highlight on contained.
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            borderRadius: 9999,
            paddingLeft: 16,
            paddingRight: 16,
            transition:
              'transform 120ms ease, background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease',
            '&:active': { transform: 'scale(0.97)' },
          },
          containedPrimary: {
            boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.14), 0 1px 2px rgba(0, 0, 0, 0.2)',
            '&:hover': {
              backgroundColor: mode === 'dark' ? ACCENT.light : ACCENT.dark,
              boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.14), 0 1px 2px rgba(0, 0, 0, 0.2)',
            },
          },
          outlined: {
            borderColor: t.divider,
            color: t.textPrimary,
            '&:hover': {
              borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.2)',
              backgroundColor: t.hover,
            },
          },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            transition: 'transform 120ms ease, background-color 150ms ease, color 150ms ease',
            '&:hover': { backgroundColor: t.hover },
            '&:active': { transform: 'scale(0.92)' },
          },
        },
      },

      MuiChip: {
        styleOverrides: {
          root: { fontWeight: 500 },
          outlined: { borderColor: t.divider },
        },
        variants: [
          { props: { variant: 'filled', color: 'success' }, style: tintChip(sem.success) },
          { props: { variant: 'filled', color: 'warning' }, style: tintChip(sem.warning) },
          { props: { variant: 'filled', color: 'error' }, style: tintChip(sem.error) },
          { props: { variant: 'filled', color: 'info' }, style: tintChip(sem.info) },
          { props: { variant: 'filled', color: 'primary' }, style: tintChip(ACCENT.main) },
        ],
      },

      // Inputs: hairline border, indigo focus ring (Linear forms).
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            backgroundColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.02)' : LIGHT.paper,
            '& .MuiOutlinedInput-notchedOutline': { borderColor: t.divider },
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: mode === 'dark' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.2)',
            },
            '&.Mui-focused': { boxShadow: focusRing },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
              borderColor: ACCENT.main,
              borderWidth: 1,
            },
          },
        },
      },

      MuiTableCell: {
        styleOverrides: {
          root: { borderColor: t.divider },
          head: { fontSize: '0.75rem', fontWeight: 500, color: t.textSecondary },
        },
      },
      MuiTableRow: {
        styleOverrides: {
          root: { '&.MuiTableRow-hover:hover': { backgroundColor: t.hover } },
        },
      },

      MuiLinearProgress: {
        styleOverrides: {
          root: { borderRadius: 9999, backgroundColor: t.hover },
          bar: { borderRadius: 9999 },
        },
      },

      MuiAlert: {
        styleOverrides: {
          root: { borderRadius: 8 },
        },
      },

      MuiListItemButton: {
        styleOverrides: {
          root: { borderRadius: 8 },
        },
      },
    },
  });
}

/** Default theme (dark, the Linear signature) — also used by tests. */
export const theme = buildTheme('dark');
