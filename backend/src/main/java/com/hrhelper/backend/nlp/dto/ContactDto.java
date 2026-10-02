package com.hrhelper.backend.nlp.dto;

import java.util.List;

/**
 * Mirrors NLP {@code ContactSchema} (REWORK 4 D40/D41). The {@code nlpObjectMapper}
 * maps snake_case → camelCase: {@code primary_email} → {@code primaryEmail}.
 * Both fields are nullable for older cached payloads serialized before REWORK 4.
 */
public record ContactDto(List<String> emails, String primaryEmail) {}
