package com.hrhelper.backend.cv.dto;

import java.util.UUID;

/**
 * Per-file outcome of a bulk upload (REWORK 1 D21/D22). Each file is processed
 * independently — one failure never blocks the rest.
 *
 * <ul>
 *   <li>{@code CREATED} — new CV stored; extraction dispatched in background.</li>
 *   <li>{@code DUPLICATE} — same content hash already owned; existing CV reused.</li>
 *   <li>{@code REJECTED} — validation failed ({@code reason} carries the code).</li>
 * </ul>
 */
public record CvUploadItemResult(
        String filename, String status, UUID cvId, UUID applicationId, String reason) {

    public static CvUploadItemResult created(String filename, UUID cvId, UUID applicationId) {
        return new CvUploadItemResult(filename, "CREATED", cvId, applicationId, null);
    }

    public static CvUploadItemResult duplicate(String filename, UUID cvId, UUID applicationId) {
        return new CvUploadItemResult(filename, "DUPLICATE", cvId, applicationId, null);
    }

    public static CvUploadItemResult rejected(String filename, String reason) {
        return new CvUploadItemResult(filename, "REJECTED", null, null, reason);
    }
}
