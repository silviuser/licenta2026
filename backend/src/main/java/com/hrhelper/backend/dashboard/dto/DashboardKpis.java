package com.hrhelper.backend.dashboard.dto;

/** Top-row KPI values for the dashboard (D30). {@code lastMatch} is null if none. */
public record DashboardKpis(
        long openPositions,
        long uniqueCandidates,
        long cvsProcessing,
        LastMatchKpi lastMatch) {}
