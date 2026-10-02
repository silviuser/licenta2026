import { apiClient } from './client';
import type { CvBulkUploadResponse, CvResponse, Page, PageParams } from './types';

/**
 * Set or clear a CV's manual email override (REWORK 4 D45). A null/blank value
 * clears it, reverting the effective email to the extracted address.
 */
export async function updateCvEmail(id: string, manualEmail: string | null): Promise<CvResponse> {
  const { data } = await apiClient.patch<CvResponse>(`/api/cvs/${id}/email`, { manualEmail });
  return data;
}

export async function listCvs(params: PageParams = {}): Promise<Page<CvResponse>> {
  const { data } = await apiClient.get<Page<CvResponse>>('/api/cvs', {
    params: { page: 0, size: 20, sort: 'createdAt,desc', ...params },
  });
  return data;
}

export async function getCv(id: string): Promise<CvResponse> {
  const { data } = await apiClient.get<CvResponse>(`/api/cvs/${id}`);
  return data;
}

/** Fetch a CV's PDF bytes (auth + owner-scoped) for inline viewing/downloading. */
export async function fetchCvBlob(id: string): Promise<Blob> {
  const { data } = await apiClient.get(`/api/cvs/${id}/file`, { responseType: 'blob' });
  return data as Blob;
}

/**
 * Bulk upload (REWORK 1 D21): 1..N PDFs in the `files` field, optional `jdId`
 * to also create applications. Returns 202 with per-file results.
 */
export async function uploadCvs(
  files: File[],
  jdId?: string,
): Promise<CvBulkUploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  const { data } = await apiClient.post<CvBulkUploadResponse>('/api/cvs', form, {
    params: jdId ? { jdId } : undefined,
  });
  return data;
}

