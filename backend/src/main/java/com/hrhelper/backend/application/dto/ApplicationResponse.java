package com.hrhelper.backend.application.dto;

import com.hrhelper.backend.common.EmailSource;
import java.time.Instant;
import java.util.UUID;

/**
 * One application (candidate) on a JD, with the CV's current processing status and
 * — for candidate-link submissions (REWORK 3 D37) — the applicant's contact
 * details and origin. Recruiter-created applications leave the candidate fields null.
 *
 * <p>{@code effectiveEmail} + {@code emailSource} (REWORK 4 D42) are the resolved
 * address the UI acts on, combining the form email, the recruiter's manual override
 * and the CV-extracted address in precedence order.
 */
public record ApplicationResponse(
        UUID applicationId,
        UUID cvId,
        String filename,
        String cvProcessingStatus,
        String origin,
        String candidateName,
        String candidateEmail,
        String candidatePhone,
        String effectiveEmail,
        EmailSource emailSource,
        Instant appliedAt,
        Instant createdAt) {}
