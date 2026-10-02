package com.hrhelper.backend.application.dto;

import java.util.UUID;

/** Projection for per-JD application counts (dashboard aggregation, D30). */
public interface JdApplicationCount {

    UUID getJdId();

    long getCount();
}
