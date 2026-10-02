import { createContext, useContext } from 'react';
import type { AlertColor } from '@mui/material';

export interface ToastApi {
  showToast: (message: string, severity?: AlertColor) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}
