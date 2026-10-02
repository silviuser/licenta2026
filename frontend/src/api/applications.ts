import { apiClient } from './client';
import type { ApplicationResponse, AttachApplicationsResponse } from './types';

/** Attach existing library CVs to a JD (REWORK 1 F5). */
export async function attachApplications(
  jdId: string,
  cvIds: string[],
): Promise<AttachApplicationsResponse> {
  const { data } = await apiClient.post<AttachApplicationsResponse>(
    `/api/jds/${jdId}/applications`,
    { cvIds },
  );
  return data;
}

export async function listApplications(jdId: string): Promise<ApplicationResponse[]> {
  const { data } = await apiClient.get<ApplicationResponse[]>(`/api/jds/${jdId}/applications`);
  return data;
}

export async function deleteApplication(jdId: string, applicationId: string): Promise<void> {
  await apiClient.delete(`/api/jds/${jdId}/applications/${applicationId}`);
}
