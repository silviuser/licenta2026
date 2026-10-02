import { createContext, useContext } from 'react';
import type { UserResponse } from '../api/types';

export interface AuthContextValue {
  user: UserResponse | null;
  role: string | null;
  isAuthenticated: boolean;
  /** True while the initial /me bootstrap is in flight. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Register then auto sign-in (decision: auto sign-in). */
  registerAndLogin: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
