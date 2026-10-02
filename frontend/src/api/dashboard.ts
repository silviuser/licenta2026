import { apiClient } from './client';
import type { DashboardResponse } from './types';

/** Landing dashboard read model (REWORK 2 D30): KPIs + positions in one call. */
export async function getDashboard(): Promise<DashboardResponse> {
  const { data } = await apiClient.get<DashboardResponse>('/api/dashboard');
  return data;
}
