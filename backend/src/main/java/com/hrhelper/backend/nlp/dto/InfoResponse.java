package com.hrhelper.backend.nlp.dto;

import java.util.Map;

/** Mirrors NLP {@code InfoResponse} (§6). Proxied to the UI via {@code GET /api/nlp/info}. */
public record InfoResponse(
        String nlpServiceVersion,
        String skillMatcherVersion,
        String skillExtractorVersion,
        String cvExtractorVersion,
        String encoderPath,
        String encoderSha,
        String escoSha,
        Map<String, Double> lockedThresholds,
        String placeholderCaveat) {}
