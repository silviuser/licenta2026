import axios from 'axios';
import { clearToken, getToken } from '../auth/tokenStorage';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';

export const apiClient = axios.create({
  baseURL,
});

/** Request interceptor: attach the JWT when present (§5). */
apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

/**
 * Response interceptor: on 401, drop the token and notify the app so it can
 * redirect to /login (§5). We dispatch a window event rather than calling the
 * router directly to keep this module free of React/Router imports.
 */
export const UNAUTHORIZED_EVENT = 'hrhelper:unauthorized';

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearToken();
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    return Promise.reject(error);
  },
);
