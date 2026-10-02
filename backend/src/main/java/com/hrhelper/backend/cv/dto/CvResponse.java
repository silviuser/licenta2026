package com.hrhelper.backend.cv.dto;

import com.hrhelper.backend.common.EmailResolution;
import com.hrhelper.backend.common.EmailSource;
import com.hrhelper.backend.cv.Cv;
import java.time.Instant;
import java.util.UUID;

/**
 * CV metadata exposed to the API — never includes the PDF binary.
 *
 * <p>{@code extractedEmail}/{@code manualEmail} are the raw stored values; the
 * resolved {@code effectiveEmail}/{@code emailSource} (REWORK 4 D42) reflect the
 * CV in isolation (no application context, so the public-form email never applies).
 */
public record CvResponse(
        UUID id,
        String originalFilename,
        String contentType,
        long sizeBytes,
        String detectedLanguage,
        boolean extractionCached,
        String processingStatus,
        String processingError,
        String contentHash,
        String extractedEmail,
        String manualEmail,
        String effectiveEmail,
        EmailSource emailSource,
        Instant createdAt) {

    public static CvResponse from(Cv cv) {
        EmailResolution.Resolved email =
                EmailResolution.resolve(null, cv.getManualEmail(), cv.getExtractedEmail());
        return new CvResponse(
                cv.getId(),
                cv.getOriginalFilename(),
                cv.getContentType(),
                cv.getSizeBytes(),
                cv.getDetectedLanguage(),
                cv.getExtractedCandidates() != null,
                cv.getProcessingStatus().name(),
                cv.getProcessingError(),
                cv.getContentHash(),
                cv.getExtractedEmail(),
                cv.getManualEmail(),
                email.email(),
                email.source(),
                cv.getCreatedAt());
    }
}
