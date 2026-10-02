package com.hrhelper.backend.matching.dto;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Full per-JD match report stored in {@code MatchJob.result_json} and surfaced
 * via {@code GET /api/matches/{jobId}} (REWORK 1 D25 / REWORK 2 D27). {@code
 * sourceJdIds} are the other positions this match pulled applications from.
 */
public record MatchReport(
        UUID jdId,
        List<UUID> sourceJdIds,
        Instant generatedAt,
        int requiredTotal,
        int niceToHaveTotal,
        List<CandidateReport> candidates) {}
