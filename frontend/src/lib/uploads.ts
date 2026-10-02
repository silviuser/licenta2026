import type { CvBulkUploadResponse } from '../api/types';

/** Summarise a bulk upload into a single, non-blocking toast (REWORK 1 D22). */
export function summariseUpload(
  res: CvBulkUploadResponse,
): { message: string; severity: 'success' | 'warning' } {
  const created = res.results.filter((r) => r.status === 'CREATED').length;
  const duplicate = res.results.filter((r) => r.status === 'DUPLICATE').length;
  const rejected = res.results.filter((r) => r.status === 'REJECTED').length;
  const parts: string[] = [];
  if (created) parts.push(`${created} uploaded`);
  if (duplicate) parts.push(`${duplicate} reused (already in library)`);
  if (rejected) parts.push(`${rejected} rejected`);
  return {
    message: parts.join(' · ') || 'Nothing to upload',
    severity: rejected > 0 ? 'warning' : 'success',
  };
}
