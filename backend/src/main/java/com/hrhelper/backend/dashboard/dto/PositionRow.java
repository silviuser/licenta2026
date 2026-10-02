package com.hrhelper.backend.dashboard.dto;

import com.hrhelper.backend.common.ProcessingStatus;
import java.time.Instant;
import java.util.UUID;

/** Lightweight JD projection for the dashboard (D30) — no requirements loaded. */
public interface PositionRow {

    UUID getJdId();

    String getTitle();

    ProcessingStatus getProcessingStatus();

    Instant getCreatedAt();
}
