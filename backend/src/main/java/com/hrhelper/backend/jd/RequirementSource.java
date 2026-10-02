package com.hrhelper.backend.jd;

/**
 * Provenance of a JD {@link Requirement} (REWORK 1 D18).
 *
 * <ul>
 *   <li>{@code EXTRACTED} — produced by the NLP {@code /v1/extract-jd} pipeline.</li>
 *   <li>{@code MANUAL} — entered or edited by the recruiter.</li>
 * </ul>
 */
public enum RequirementSource {
    EXTRACTED,
    MANUAL
}
