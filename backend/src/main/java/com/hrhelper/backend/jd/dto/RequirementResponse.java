package com.hrhelper.backend.jd.dto;

import com.hrhelper.backend.jd.Requirement;
import java.util.UUID;

public record RequirementResponse(
        UUID id,
        String text,
        String skillUri,
        String skillLabel,
        String importance,
        double confidence,
        String source) {

    public static RequirementResponse from(Requirement r) {
        return new RequirementResponse(
                r.getId(),
                r.getText(),
                r.getSkillUri(),
                r.getSkillLabel(),
                r.getImportance(),
                r.getConfidence(),
                r.getSource().name());
    }
}
