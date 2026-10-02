package com.hrhelper.backend.nlp.dto;

import java.util.List;

/** Mirrors NLP {@code MatchRequest} (§6). */
public record MatchRequest(
        String cvId, ExtractResponse enriched, String jdId, List<RequirementDto> requirements) {}
