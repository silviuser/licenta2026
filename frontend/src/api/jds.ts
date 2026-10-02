import { apiClient } from './client';
import { applyEmployerTemplate, releaseEmployerTemplate } from './requirementTemplates';
import type {
  JdRequest,
  JdResponse,
  Page,
  PageParams,
  RequirementInput,
} from './types';

export async function listJds(params: PageParams = {}): Promise<Page<JdResponse>> {
  const { data } = await apiClient.get<Page<JdResponse>>('/api/jds', {
    params: { page: 0, size: 20, sort: 'updatedAt,desc', ...params },
  });
  return { ...data, content: data.content.map(applyEmployerTemplate) };
}

export async function getJd(id: string): Promise<JdResponse> {
  const { data } = await apiClient.get<JdResponse>(`/api/jds/${id}`);
  return applyEmployerTemplate(data);
}

export async function createJd(body: JdRequest): Promise<JdResponse> {
  const { data } = await apiClient.post<JdResponse>('/api/jds', body);
  return data;
}

export async function updateJd(id: string, body: JdRequest): Promise<JdResponse> {
  const { data } = await apiClient.put<JdResponse>(`/api/jds/${id}`, body);
  return data;
}

export async function updateRequirements(
  id: string,
  requirements: RequirementInput[],
): Promise<JdResponse> {
  const { data } = await apiClient.put<JdResponse>(`/api/jds/${id}/requirements`, {
    requirements,
  });
  // Recruiter has taken ownership of this position's requirements — stop seeding
  // the employer template so their saved edits are shown as-is from now on.
  releaseEmployerTemplate(id);
  return data;
}

export async function deleteJd(id: string): Promise<void> {
  await apiClient.delete(`/api/jds/${id}`);
}
