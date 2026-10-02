package com.hrhelper.backend.nlp.dto;

/** Mirrors NLP {@code ErrorResponse} (§6) — the non-2xx body of the NLP service. */
public record NlpErrorDto(String error, String detail, String requestId) {}
