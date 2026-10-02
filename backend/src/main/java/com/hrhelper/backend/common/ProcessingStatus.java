package com.hrhelper.backend.common;

/**
 * Background-processing lifecycle for CVs and JDs (REWORK 1 D26). Visible to the
 * frontend, which polls while anything is {@code PENDING} or {@code PROCESSING}.
 */
public enum ProcessingStatus {
    PENDING,
    PROCESSING,
    READY,
    FAILED
}
