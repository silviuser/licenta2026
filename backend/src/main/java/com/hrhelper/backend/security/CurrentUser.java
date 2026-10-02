package com.hrhelper.backend.security;

import java.util.UUID;
import org.springframework.security.core.context.SecurityContextHolder;

/** Convenience accessor for the authenticated principal's id and role. */
public final class CurrentUser {

    private CurrentUser() {}

    public static AppUserPrincipal principal() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof AppUserPrincipal p) {
            return p;
        }
        throw new IllegalStateException("no authenticated user in security context");
    }

    public static UUID id() {
        return principal().getId();
    }
}
