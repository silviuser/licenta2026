import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getMatchJob, listMatches, startJdMatch } from '../api/matches';
import type { MatchFilters } from '../api/matches';
import { MATCH_POLL_INTERVAL_MS } from '../lib/constants';

export const matchKeys = {
  all: ['matches'] as const,
  job: (jobId: string) => ['matches', 'job', jobId] as const,
  history: (filters: MatchFilters) => ['matches', 'history', filters] as const,
};

export function useStartJdMatch() {
  const qc = useQueryClient();
  return useMutation<
    { jobId: string; status: string },
    Error,
    { jdId: string; sourceJdIds: string[] }
  >({
    mutationFn: ({ jdId, sourceJdIds }) => startJdMatch(jdId, sourceJdIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: matchKeys.all }),
  });
}

/** Poll a match job until it reaches a terminal state (§7). */
export function useMatchJob(jobId: string | undefined) {
  return useQuery({
    queryKey: matchKeys.job(jobId ?? ''),
    queryFn: () => getMatchJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'PENDING' || status === 'RUNNING' ? MATCH_POLL_INTERVAL_MS : false;
    },
  });
}

export function useMatchHistory(filters: MatchFilters = {}) {
  return useQuery({
    queryKey: matchKeys.history(filters),
    queryFn: () => listMatches(filters),
  });
}
