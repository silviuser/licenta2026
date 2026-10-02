package com.hrhelper.backend.nlp.dto;

import java.util.List;

/** Mirrors NLP {@code ExtractJdResponse} (REWORK 1 §2). */
public record ExtractJdResponse(
        String jdId,
        String detectedLanguage,
        List<JdRequirementDto> requirements,
        String pipelineVersion,
        List<String> warnings) {}
