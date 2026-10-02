package com.hrhelper.backend.jd.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * Create/replace a JD. {@code requirements} is now optional (REWORK 1 D18): when
 * omitted/empty the backend extracts requirements from {@code descriptionText} in
 * the background; when present they are treated as manual.
 */
public record JdRequest(
        @NotBlank @Size(max = 512) String title,
        String descriptionText,
        @Valid List<RequirementInput> requirements) {

    public List<RequirementInput> requirementsOrEmpty() {
        return requirements != null ? requirements : List.of();
    }
}
