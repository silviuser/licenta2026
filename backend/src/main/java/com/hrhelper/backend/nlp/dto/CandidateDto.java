package com.hrhelper.backend.nlp.dto;

/** Mirrors NLP {@code CandidateSchema} (§6). */
public record CandidateDto(
        String escoUri,
        String skillLabel,
        String surfaceForm,
        String section,
        String source,
        double confidence,
        double semanticSimilarity) {}
