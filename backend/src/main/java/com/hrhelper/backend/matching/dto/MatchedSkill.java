package com.hrhelper.backend.matching.dto;

/** A requirement satisfied by CV evidence (REWORK 1 D25). */
public record MatchedSkill(
        String requirementText,
        String importance,
        String evidenceSurfaceForm,
        String evidenceSection,
        double matchScore) {}
