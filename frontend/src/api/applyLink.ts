import { apiClient } from './client';
import type { ApplyLinkResponse } from './types';

/** Recruiter-facing apply-link management (REWORK 3 D33). Authenticated. */

export async function getApplyLink(jdId: string): Promise<ApplyLinkResponse> {
  const { data } = await apiClient.get<ApplyLinkResponse>(`/api/jds/${jdId}/apply-link`);
  return data;
}

/** Generate or regenerate the token (the old one stops working) and enable it. */
export async function generateApplyLink(jdId: string): Promise<ApplyLinkResponse> {
  const { data } = await apiClient.post<ApplyLinkResponse>(`/api/jds/${jdId}/apply-link`);
  return data;
}

export async function setApplyLinkEnabled(
  jdId: string,
  enabled: boolean,
): Promise<ApplyLinkResponse> {
  const { data } = await apiClient.put<ApplyLinkResponse>(`/api/jds/${jdId}/apply-link`, {
    enabled,
  });
  return data;
}
