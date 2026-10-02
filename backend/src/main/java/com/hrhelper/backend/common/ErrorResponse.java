package com.hrhelper.backend.common;

import java.time.Instant;

/**
 * Uniform error body for all non-2xx responses, mirroring the NLP service's
 * {@code ErrorResponse} shape for end-to-end consistency.
 */
public record ErrorResponse(String error, String detail, String requestId, Instant timestamp) {

    public static ErrorResponse of(String error, String detail, String requestId) {
        return new ErrorResponse(error, detail, requestId, Instant.now());
    }
}
