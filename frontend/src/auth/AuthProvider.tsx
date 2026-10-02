import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getMe, login as loginRequest, register as registerRequest } from '../api/auth';
import { UNAUTHORIZED_EVENT } from '../api/client';
import type { UserResponse } from '../api/types';
import { clearToken, getToken, setToken } from './tokenStorage';
import { AuthContext } from './authContext';
import type { AuthContextValue } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(getToken()));

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  // Bootstrap: if a token is present on load, hydrate the profile from /me.
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setLoading(false);
      return;
    }
    setLoading(true);
    getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // 401 handled by the interceptor; just drop local state here.
        if (!cancelled) {
          clearToken();
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // React to a 401 surfaced by the axios interceptor.
  useEffect(() => {
    const handler = () => {
      setUser(null);
      queryClient.clear();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [queryClient]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest({ email, password });
    setToken(res.accessToken);
    const me = await getMe();
    setUser(me);
  }, []);

  const registerAndLogin = useCallback(
    async (email: string, password: string, fullName: string) => {
      await registerRequest({ email, password, fullName });
      const res = await loginRequest({ email, password });
      setToken(res.accessToken);
      const me = await getMe();
      setUser(me);
    },
    [],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role: user?.role ?? null,
      isAuthenticated: Boolean(user),
      loading,
      login,
      registerAndLogin,
      logout,
    }),
    [user, loading, login, registerAndLogin, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
