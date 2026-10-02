package com.hrhelper.backend.application.dto;

import java.util.List;
import java.util.UUID;

/**
 * Outcome of attaching CVs to a JD: newly created links, those that already
 * existed (idempotent skip), and CV ids not found / not owned by the recruiter.
 */
public record AttachApplicationsResponse(
        List<ApplicationResponse> created, List<UUID> alreadyExisted, List<UUID> notFound) {}
