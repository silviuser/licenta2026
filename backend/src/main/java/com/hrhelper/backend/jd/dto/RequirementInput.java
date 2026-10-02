package com.hrhelper.backend.jd.dto;

import com.hrhelper.backend.jd.RequirementSource;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** One requirement in a JD create/update request. */
public record RequirementInput(
        @NotBlank String text,
        String skillUri,
        String skillLabel,
        @NotBlank @Pattern(regexp = "required|nice_to_have") String importance,
        @DecimalMin("0.0") @DecimalMax("1.0") Double confidence,
        @Pattern(regexp = "EXTRACTED|MANUAL") String source) {

    public double confidenceOrDefault() {
        return confidence != null ? confidence : 0.5;
    }

    /**
     * Provenance of this row. Items the recruiter adds are {@code MANUAL}; an
     * extracted item kept during editing may echo {@code EXTRACTED} (D18).
     */
    public RequirementSource sourceOrDefault() {
        return "EXTRACTED".equals(source) ? RequirementSource.EXTRACTED : RequirementSource.MANUAL;
    }
}
