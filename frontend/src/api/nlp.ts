import { apiClient } from './client';
import type { NlpInfo } from './types';

export async function getNlpInfo(): Promise<NlpInfo> {
  const { data } = await apiClient.get<NlpInfo>('/api/nlp/info');
  return data;
}
