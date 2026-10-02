import { createContext, useContext } from 'react';
import type { PaletteMode } from '@mui/material';

export const COLOR_MODE_STORAGE_KEY = 'hr-helper-color-mode';

export interface ColorModeContextValue {
  mode: PaletteMode;
  toggleMode: () => void;
}

export const ColorModeContext = createContext<ColorModeContextValue>({
  mode: 'dark',
  toggleMode: () => {},
});

export function useColorMode(): ColorModeContextValue {
  return useContext(ColorModeContext);
}
