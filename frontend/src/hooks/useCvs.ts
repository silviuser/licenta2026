import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchCvBlob, listCvs, updateCvEmail, uploadCvs } from '../api/cvs';
import { useToast } from '../components/toastContext';
import type { CvBulkUploadResponse, CvResponse, PageParams } from '../api/types';
import { MATCH_POLL_INTERVAL_MS } from '../lib/constants';
import { errorMessage } from '../lib/errorMessages';

export const cvKeys = {
  all: ['cvs'] as const,
  list: (params: PageParams) => ['cvs', 'list', params] as const,
};

const isPending = (s: string) => s === 'PENDING' || s === 'PROCESSING';

export function useCvs(params: PageParams = {}) {
  return useQuery({
    queryKey: cvKeys.list(params),
    queryFn: () => listCvs(params),
    // Light polling while any CV is still being processed (D26).
    refetchInterval: (query) =>
      query.state.data?.content.some((cv) => isPending(cv.processingStatus))
        ? MATCH_POLL_INTERVAL_MS
        : false,
  });
}

export function useUploadCvs() {
  const qc = useQueryClient();
  return useMutation<CvBulkUploadResponse, Error, { files: File[]; jdId?: string }>({
    mutationFn: ({ files, jdId }) => uploadCvs(files, jdId),
    onSuccess: () => qc.invalidateQueries({ queryKey: cvKeys.all }),
  });
}

/**
 * Set/clear a CV's manual email (REWORK 4 D45). Returns the updated CV so the
 * caller can reflect the resolved email/source in whatever view it lives in
 * (the match report is a snapshot, the applications list re-resolves live).
 */
export function useUpdateCvEmail() {
  const qc = useQueryClient();
  return useMutation<CvResponse, Error, { cvId: string; manualEmail: string | null }>({
    mutationFn: ({ cvId, manualEmail }) => updateCvEmail(cvId, manualEmail),
    onSuccess: () => qc.invalidateQueries({ queryKey: cvKeys.all }),
  });
}

/**
 * Open a CV's PDF in a new tab. The file endpoint needs the JWT, so we fetch the
 * bytes via the authenticated client and hand the blob to a tab opened
 * synchronously on click (avoids the pop-up blocker); falls back to a download if
 * the tab was blocked. `viewingCvId` lets a row show a spinner on its own button.
 */
export function useViewCv() {
  const { showToast } = useToast();
  const mutation = useMutation({
    mutationFn: (cvId: string) => fetchCvBlob(cvId),
  });

  function viewCv(cvId: string, filename?: string) {
    // Open the tab synchronously (within the click gesture) so it isn't blocked,
    // then point it at the blob once fetched. No 'noopener' here — that would make
    // window.open return null; the tab only ever shows our own same-origin blob.
    const win = window.open('', '_blank');
    mutation.mutate(cvId, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob);
        if (win && !win.closed) {
          win.location.href = url;
        } else {
          const a = document.createElement('a');
          a.href = url;
          a.download = filename ?? `cv-${cvId}.pdf`;
          a.click();
        }
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      onError: (err) => {
        win?.close();
        showToast(errorMessage(err), 'error');
      },
    });
  }

  return { viewCv, viewingCvId: mutation.isPending ? mutation.variables ?? null : null };
}
