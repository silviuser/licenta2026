package com.hrhelper.backend.nlp.dto;

/**
 * Request body for NLP {@code POST /v1/extract-jd}. Serialised snake_case by the
 * {@code nlpObjectMapper} → {@code jd_id}, {@code text}, {@code language}.
 */
public record ExtractJdRequest(String jdId, String text, String language) {}
