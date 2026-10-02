import { apiClient } from './client';
import { applyPriorityShortlist } from './shortlist';
import type { JobStatus, MatchJobResponse, Page, PageParams } from './types';

export interface MatchFilters extends PageParams {
  jdId?: string;
  status?: JobStatus;
}

export interface StartMatchResult {
  jobId: string;
  status: JobStatus;
}

/** Launch a per-JD match (REWORK 2 D27/D28) → 202 with the job id. */
export async function startJdMatch(
  jdId: string,
  sourceJdIds: string[],
): Promise<StartMatchResult> {
  const { data } = await apiClient.post<StartMatchResult>(`/api/jds/${jdId}/match`, {
    sourceJdIds,
  });
  return data;
}

export async function getMatchJob(jobId: string): Promise<MatchJobResponse> {
  const { data } = await apiClient.get<MatchJobResponse>(`/api/matches/${jobId}`);
  return applyPriorityShortlist(data);
}

export async function listMatches(filters: MatchFilters = {}): Promise<Page<MatchJobResponse>> {
  const { page = 0, size = 20, sort = 'createdAt,desc', jdId, status } = filters;
  const { data } = await apiClient.get<Page<MatchJobResponse>>('/api/matches', {
    params: { page, size, sort, jdId, status },
  });
  return data;
}
