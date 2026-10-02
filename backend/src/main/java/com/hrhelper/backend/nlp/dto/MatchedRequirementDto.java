package com.hrhelper.backend.nlp.dto;

/** Mirrors NLP {@code MatchedRequirementSchema} (§6). */
public record MatchedRequirementDto(
        RequirementDto requirement, CandidateDto cvCandidate, double matchScore) {}
