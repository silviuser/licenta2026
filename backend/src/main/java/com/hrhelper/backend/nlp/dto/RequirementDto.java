package com.hrhelper.backend.nlp.dto;

/** Mirrors NLP {@code RequirementSchema} (§6). {@code confidence} defaults to 0.5. */
public record RequirementDto(
        String text,
        String skillUri,
        String skillLabel,
        String importance,
        double confidence) {}
