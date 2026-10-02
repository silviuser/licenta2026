package com.hrhelper.backend.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

/** The latest match for a position (D30); null on a position never matched. */
public record PositionLastMatch(
        UUID jobId, String status, Double topScore, Instant finishedAt) {}
