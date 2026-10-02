package com.hrhelper.backend.apply.dto;

/**
 * Confirmation returned to a candidate after applying (REWORK 3 D34). Carries no
 * internal ids (D38) — only a status and a human message.
 *
 * @param status {@code RECEIVED} for a first application, {@code UPDATED} for a
 *     re-application that replaced the CV / refreshed contact details (D36)
 */
public record PublicApplyResponse(String status, String message) {

    public static final String RECEIVED = "RECEIVED";
    public static final String UPDATED = "UPDATED";

    public static PublicApplyResponse received() {
        return new PublicApplyResponse(RECEIVED, "Your application has been received.");
    }

    public static PublicApplyResponse updated() {
        return new PublicApplyResponse(UPDATED, "Your application has been updated.");
    }
}
