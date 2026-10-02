package com.hrhelper.backend.nlp.dto;

import java.time.OffsetDateTime;
import java.util.List;

/** Mirrors NLP {@code MatchResponse} / {@code FullResponse} (§6). */
public record MatchResponse(
        String cvId,
        String jdId,
        double overallScore,
        String overallClass,
        double requiredCoverage,
        double niceToHaveCoverage,
        List<MatchedRequirementDto> matchedRequired,
        List<MatchedRequirementDto> matchedNiceToHave,
        List<RequirementDto> unmatchedRequired,
        List<RequirementDto> unmatchedNiceToHave,
        OffsetDateTime timestamp,
        String pipelineVersion) {}
