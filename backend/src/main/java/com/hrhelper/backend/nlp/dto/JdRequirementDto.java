package com.hrhelper.backend.nlp.dto;

/** Mirrors NLP {@code JdRequirementSchema} (REWORK 1 §2). No {@code importance}. */
public record JdRequirementDto(
        String text, String skillUri, String skillLabel, double confidence) {}
