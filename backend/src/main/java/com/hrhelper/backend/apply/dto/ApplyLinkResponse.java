package com.hrhelper.backend.apply.dto;

/**
 * Current state of a JD's public apply link (REWORK 3 D33).
 *
 * @param exists whether a token has been generated
 * @param enabled whether the link currently accepts applications
 * @param url the full public apply URL, or null when no token exists yet
 */
public record ApplyLinkResponse(boolean exists, boolean enabled, String url) {

    public static ApplyLinkResponse none() {
        return new ApplyLinkResponse(false, false, null);
    }

    public static ApplyLinkResponse of(boolean enabled, String url) {
        return new ApplyLinkResponse(true, enabled, url);
    }
}
