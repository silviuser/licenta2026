package com.hrhelper.backend.common;

/**
 * Thrown when a resource does not exist OR is not owned by the current user.
 * Per the per-user isolation rule (D6 / §9) a cross-user access yields 404,
 * not 403, so resource existence is not disclosed.
 */
public class NotFoundException extends RuntimeException {

    public NotFoundException(String message) {
        super(message);
    }
}
