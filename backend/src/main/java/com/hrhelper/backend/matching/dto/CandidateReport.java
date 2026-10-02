package com.hrhelper.backend.matching.dto;

import com.hrhelper.backend.common.EmailSource;
import java.util.List;
import java.util.UUID;

/**
 * Per-candidate entry in a per-JD match report (REWORK 1 D25 / REWORK 2 D29).
 * Derived deterministically from the NLP {@code MatchResponse} — no LLM. For
 * pooled candidates {@code sourceJdId}/{@code sourceJdTitle} name the position the
 * CV was pulled from; both are null for directly-applied candidates.
 *
 * <p>{@code origin} + candidate contact fields surface where the application came
 * from (REWORK 3 D37): populated for candidate-link applications, null otherwise.
 *
 * <p>{@code effectiveEmail} + {@code emailSource} (REWORK 4 D42) are the resolved
 * contact address the UI acts on (mailto / contact bar), already a snapshot at
 * match time — a later manual edit shows up in the next match (D45).
 */
public record CandidateReport(
        Integer rank,
        UUID cvId,
        String filename,
        String source,
        UUID sourceJdId,
        String sourceJdTitle,
        String origin,
        String candidateName,
        String candidateEmail,
        String candidatePhone,
        String effectiveEmail,
        EmailSource emailSource,
        String status,
        Double overallScore,
        String overallClass,
        Double requiredCoverage,
        Double niceToHaveCoverage,
        List<MatchedSkill> matchedSkills,
        MissingSkills missingSkills,
        String explanation,
        String errorCode) {}
