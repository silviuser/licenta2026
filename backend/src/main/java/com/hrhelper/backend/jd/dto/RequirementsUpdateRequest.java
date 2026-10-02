package com.hrhelper.backend.jd.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;

/**
 * Replace a JD's requirement list (REWORK 1 F4). The full list is sent; items
 * without a recognised {@code source} become {@code MANUAL}. An empty list
 * clears all requirements.
 */
public record RequirementsUpdateRequest(
        @NotNull @Valid List<RequirementInput> requirements) {}
