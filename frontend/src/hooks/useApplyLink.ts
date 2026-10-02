import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  generateApplyLink,
  getApplyLink,
  setApplyLinkEnabled,
} from '../api/applyLink';

export const applyLinkKeys = {
  detail: (jdId: string) => ['apply-link', jdId] as const,
};

export function useApplyLink(jdId: string | undefined) {
  return useQuery({
    queryKey: applyLinkKeys.detail(jdId ?? ''),
    queryFn: () => getApplyLink(jdId as string),
    enabled: Boolean(jdId),
  });
}

export function useGenerateApplyLink(jdId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => generateApplyLink(jdId),
    onSuccess: (data) => qc.setQueryData(applyLinkKeys.detail(jdId), data),
  });
}

export function useSetApplyLinkEnabled(jdId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => setApplyLinkEnabled(jdId, enabled),
    onSuccess: (data) => qc.setQueryData(applyLinkKeys.detail(jdId), data),
  });
}
