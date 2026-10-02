import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createJd,
  deleteJd,
  getJd,
  listJds,
  updateJd,
  updateRequirements,
} from '../api/jds';
import type { JdRequest, PageParams, RequirementInput } from '../api/types';
import { MATCH_POLL_INTERVAL_MS } from '../lib/constants';

export const jdKeys = {
  all: ['jds'] as const,
  list: (params: PageParams) => ['jds', 'list', params] as const,
  detail: (id: string) => ['jds', 'detail', id] as const,
};

const isPending = (s: string) => s === 'PENDING' || s === 'PROCESSING';

export function useJds(params: PageParams = {}) {
  return useQuery({
    queryKey: jdKeys.list(params),
    queryFn: () => listJds(params),
    refetchInterval: (query) =>
      query.state.data?.content.some((jd) => isPending(jd.processingStatus))
        ? MATCH_POLL_INTERVAL_MS
        : false,
  });
}

export function useJd(id: string | undefined) {
  return useQuery({
    queryKey: jdKeys.detail(id ?? ''),
    queryFn: () => getJd(id as string),
    enabled: Boolean(id),
    // Poll while requirements are being extracted in the background (D18).
    refetchInterval: (query) =>
      query.state.data && isPending(query.state.data.processingStatus)
        ? MATCH_POLL_INTERVAL_MS
        : false,
  });
}

export function useCreateJd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JdRequest) => createJd(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: jdKeys.all }),
  });
}

export function useUpdateJd(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JdRequest) => updateJd(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: jdKeys.all }),
  });
}

export function useUpdateRequirements(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (requirements: RequirementInput[]) => updateRequirements(id, requirements),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: jdKeys.detail(id) });
      qc.invalidateQueries({ queryKey: jdKeys.all });
    },
  });
}

export function useDeleteJd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteJd(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: jdKeys.all }),
  });
}
