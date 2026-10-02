package com.hrhelper.backend.common;

import java.util.regex.Pattern;

/**
 * The single place that resolves a candidate's <em>effective</em> email (REWORK 4
 * D42) and validates address syntax. Pure and dependency-free so it can be unit
 * tested in isolation and reused by every DTO that exposes a contact address.
 *
 * <p>Precedence (D42): the public-form email (candidate-link submissions, D34)
 * wins, then the recruiter's manual override, then the value extracted from the
 * CV text, then nothing.
 */
public final class EmailResolution {

    private EmailResolution() {}

    /**
     * Standard {@code local@domain.tld} shape. Mirrors the conservative phase-1
     * pattern used by the NLP extractor (a dotted domain with an alphabetic TLD),
     * so what the UI accepts on manual edit matches what extraction produces.
     */
    private static final Pattern SYNTAX =
            Pattern.compile("^[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}$");

    /** The resolved address plus the source it came from. */
    public record Resolved(String email, EmailSource source) {}

    /**
     * Resolve in D42 precedence order. Inputs may be {@code null}/blank; the first
     * present one wins (normalised to trimmed lowercase).
     */
    public static Resolved resolve(String candidateFormEmail, String manualEmail, String extractedEmail) {
        if (isPresent(candidateFormEmail)) {
            return new Resolved(normalize(candidateFormEmail), EmailSource.CANDIDATE_FORM);
        }
        if (isPresent(manualEmail)) {
            return new Resolved(normalize(manualEmail), EmailSource.MANUAL);
        }
        if (isPresent(extractedEmail)) {
            return new Resolved(normalize(extractedEmail), EmailSource.EXTRACTED);
        }
        return new Resolved(null, EmailSource.NONE);
    }

    /** Server-side syntactic validation for the manual-edit PATCH (D45). */
    public static boolean isValidSyntax(String email) {
        return email != null && SYNTAX.matcher(email.trim()).matches();
    }

    /** Lowercase + trim, or {@code null} for null/blank input. */
    public static String normalize(String email) {
        if (email == null) {
            return null;
        }
        String trimmed = email.trim();
        return trimmed.isEmpty() ? null : trimmed.toLowerCase();
    }

    private static boolean isPresent(String s) {
        return s != null && !s.isBlank();
    }
}
