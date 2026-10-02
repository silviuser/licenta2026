package com.hrhelper.backend.application.dto;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import java.util.UUID;

/** Attach existing library CVs to a JD (REWORK 1 F5). */
public record AttachApplicationsRequest(@NotEmpty List<UUID> cvIds) {}
