package com.hrhelper.backend.matching.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.hrhelper.backend.matching.MatchJob;
import java.time.Instant;
import java.util.UUID;

/**
 * Status + (on success) result of a match job. {@code result} carries the full
 * NLP {@code MatchResponse} as a JSON tree so the recruiter UI gets the matched /
 * unmatched lists without a second round-trip.
 */
public record MatchJobResponse(
        UUID jobId,
        UUID cvId,
        UUID jdId,
        String status,
        Double overallScore,
        String overallClass,
        Double requiredCoverage,
        Double niceToHaveCoverage,
        String pipelineVersion,
        String errorCode,
        String errorDetail,
        JsonNode result,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt) {

    public static MatchJobResponse from(MatchJob job, JsonNode result) {
        return new MatchJobResponse(
                job.getId(),
                job.getCvId(),
                job.getJdId(),
                job.getStatus().name(),
                job.getOverallScore(),
                job.getOverallClass(),
                job.getRequiredCoverage(),
                job.getNiceToHaveCoverage(),
                job.getPipelineVersion(),
                job.getErrorCode(),
                job.getErrorDetail(),
                result,
                job.getCreatedAt(),
                job.getStartedAt(),
                job.getFinishedAt());
    }
}
