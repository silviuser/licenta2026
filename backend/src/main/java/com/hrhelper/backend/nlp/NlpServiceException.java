package com.hrhelper.backend.nlp;

/**
 * Domain exception raised when the NLP service returns a non-2xx response or is
 * unreachable. Carries the stable NLP error code so the matching layer can
 * persist it on the failed job and the API can surface it coherently (§11).
 */
public class NlpServiceException extends RuntimeException {

    private final String errorCode;
    private final int status;
    private final boolean transientError;

    public NlpServiceException(String errorCode, String detail, int status, boolean transientError) {
        super(detail);
        this.errorCode = errorCode;
        this.status = status;
        this.transientError = transientError;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public int getStatus() {
        return status;
    }

    /** True for retryable conditions (503 readiness, connection timeout); never for 4xx. */
    public boolean isTransient() {
        return transientError;
    }
}
