package com.hrhelper.backend.dashboard.dto;

import com.hrhelper.backend.matching.JobStatus;
import java.time.Instant;
import java.util.UUID;

/** Scalar match-job projection for the dashboard (D30) — no result_json parsing. */
public interface MatchSummaryRow {

    UUID getJobId();

    UUID getJdId();

    JobStatus getStatus();

    Double getTopScore();

    Instant getFinishedAt();

    Instant getCreatedAt();
}
