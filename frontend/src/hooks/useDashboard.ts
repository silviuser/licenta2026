import { useQuery } from '@tanstack/react-query';
import { getDashboard } from '../api/dashboard';
import { MATCH_POLL_INTERVAL_MS } from '../lib/constants';

export const dashboardKeys = {
  all: ['dashboard'] as const,
};

const isPending = (s: string) => s === 'PENDING' || s === 'PROCESSING';

/**
 * Loads the landing dashboard. Polls lightly while any position is still being
 * processed or CVs are in flight, so KPIs/statuses settle without a refresh.
 */
export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.all,
    queryFn: getDashboard,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const anyProcessing =
        data.kpis.cvsProcessing > 0 ||
        data.positions.some((p) => isPending(p.processingStatus));
      return anyProcessing ? MATCH_POLL_INTERVAL_MS : false;
    },
  });
}
