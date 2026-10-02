package com.hrhelper.backend.cv.dto;

import jakarta.validation.constraints.Size;

/**
 * Body for {@code PATCH /api/cvs/{id}/email} (REWORK 4 D45). A null or blank
 * {@code manualEmail} clears the override (reverting to the extracted address);
 * a non-blank value is validated syntactically server-side before it is stored.
 */
public record CvEmailUpdateRequest(@Size(max = 320) String manualEmail) {}
