package com.hrhelper.backend.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

/** One position in the dashboard list (D30) with its application count + last match. */
public record PositionSummary(
        UUID jdId,
        String title,
        String processingStatus,
        long applicationCount,
        Instant createdAt,
        PositionLastMatch lastMatch) {}
