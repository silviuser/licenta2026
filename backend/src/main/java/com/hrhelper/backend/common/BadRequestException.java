package com.hrhelper.backend.common;

/** Thrown for client-side validation problems not covered by bean validation. */
public class BadRequestException extends RuntimeException {

    private final String errorCode;

    public BadRequestException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
