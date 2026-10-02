import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  attachApplications,
  deleteApplication,
  listApplications,
} from '../api/applications';
import { MATCH_POLL_INTERVAL_MS } from '../lib/constants';

export const applicationKeys = {
  all: ['applications'] as const,
  list: (jdId: string) => ['applications', 'list', jdId] as const,
};

const isPending = (s: string | null) => s === 'PENDING' || s === 'PROCESSING';

export function useApplications(jdId: string | undefined) {
  return useQuery({
    queryKey: applicationKeys.list(jdId ?? ''),
    queryFn: () => listApplications(jdId as string),
    enabled: Boolean(jdId),
    // Poll while any attached CV is still being processed (D26).
    refetchInterval: (query) =>
      query.state.data?.some((a) => isPending(a.cvProcessingStatus))
        ? MATCH_POLL_INTERVAL_MS
        : false,
  });
}

export function useAttachApplications(jdId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cvIds: string[]) => attachApplications(jdId, cvIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: applicationKeys.list(jdId) }),
  });
}

export function useDeleteApplication(jdId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) => deleteApplication(jdId, applicationId),
    onSuccess: () => qc.invalidateQueries({ queryKey: applicationKeys.list(jdId) }),
  });
}
