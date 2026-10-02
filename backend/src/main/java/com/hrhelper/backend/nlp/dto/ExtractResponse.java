package com.hrhelper.backend.nlp.dto;

import java.util.List;

/**
 * Mirrors NLP {@code ExtractResponse} (§6). Cached on the CV (D13).
 *
 * <p>{@code contact} is additive (REWORK 4 D40): it is {@code null} for payloads
 * cached before this feature, so the startup backfill (D46) refreshes them.
 */
public record ExtractResponse(
        String cvId,
        String detectedLanguage,
        List<CandidateDto> candidates,
        String pipelineVersion,
        List<String> warnings,
        ContactDto contact) {}
