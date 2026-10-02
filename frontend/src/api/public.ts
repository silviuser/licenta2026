import axios from 'axios';
import type { PublicApplyRequest, PublicApplyResponse, PublicJobView } from './types';

/**
 * Dedicated client for the public, unauthenticated apply endpoints (REWORK 3).
 * Deliberately separate from {@link apiClient}: no JWT is attached and no 401
 * interceptor fires, since a candidate has no session.
 */
const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';

export const publicClient = axios.create({ baseURL });

export async function getPublicJob(token: string): Promise<PublicJobView> {
  const { data } = await publicClient.get<PublicJobView>(
    `/api/public/apply/${encodeURIComponent(token)}`,
  );
  return data;
}

export async function submitApplication(
  token: string,
  body: PublicApplyRequest,
): Promise<PublicApplyResponse> {
  const form = new FormData();
  form.append('name', body.name);
  form.append('email', body.email);
  form.append('phone', body.phone);
  form.append('file', body.file);
  const { data } = await publicClient.post<PublicApplyResponse>(
    `/api/public/apply/${encodeURIComponent(token)}`,
    form,
  );
  return data;
}
