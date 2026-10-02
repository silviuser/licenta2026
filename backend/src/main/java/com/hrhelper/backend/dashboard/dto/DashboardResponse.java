package com.hrhelper.backend.dashboard.dto;

import java.util.List;

/** Single-call payload for the landing dashboard (REWORK 2 D30). */
public record DashboardResponse(DashboardKpis kpis, List<PositionSummary> positions) {}
