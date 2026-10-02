package com.hrhelper.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Public-link + abuse-protection settings (REWORK 3 D32/D38).
 *
 * @param publicBaseUrl base URL the recruiter-facing apply link is built from
 *     (the SPA serves {@code /apply/{token}}), e.g. {@code http://localhost:5173}
 * @param rateLimitGetPerMinute max GET requests per IP per minute on {@code /api/public/**}
 * @param rateLimitPostPerHour max POST requests (applications) per IP per hour
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String publicBaseUrl, int rateLimitGetPerMinute, int rateLimitPostPerHour) {

    public AppProperties {
        if (publicBaseUrl == null || publicBaseUrl.isBlank()) {
            publicBaseUrl = "http://localhost:5173";
        }
        // Trim a trailing slash so URL building stays "<base>/apply/<token>".
        if (publicBaseUrl.endsWith("/")) {
            publicBaseUrl = publicBaseUrl.substring(0, publicBaseUrl.length() - 1);
        }
        if (rateLimitGetPerMinute <= 0) {
            rateLimitGetPerMinute = 60;
        }
        if (rateLimitPostPerHour <= 0) {
            rateLimitPostPerHour = 10;
        }
    }

    /** Full public apply URL for a token (D32). */
    public String applyUrl(String token) {
        return publicBaseUrl + "/apply/" + token;
    }
}
