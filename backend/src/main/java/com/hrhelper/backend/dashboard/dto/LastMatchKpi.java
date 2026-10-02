package com.hrhelper.backend.dashboard.dto;

import java.time.Instant;
import java.util.UUID;

/** The most recent finished match across all positions (D30 KPI). */
public record LastMatchKpi(
        UUID jobId, UUID jdId, String jdTitle, Instant finishedAt, Double topScore) {}
