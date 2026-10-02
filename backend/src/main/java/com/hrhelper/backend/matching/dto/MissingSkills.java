package com.hrhelper.backend.matching.dto;

import java.util.List;

/** Unmet requirements, split by importance (REWORK 1 D25). */
public record MissingSkills(List<String> required, List<String> niceToHave) {}
