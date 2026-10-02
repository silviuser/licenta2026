package com.hrhelper.backend.apply.dto;

import jakarta.validation.constraints.NotNull;

/** Toggle a JD's apply link on/off (REWORK 3 D33). */
public record SetApplyLinkRequest(@NotNull Boolean enabled) {}
