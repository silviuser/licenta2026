package com.hrhelper.backend.application;

/**
 * How an {@link Application} was created (REWORK 3 D37).
 *
 * <ul>
 *   <li>{@code RECRUITER} — the recruiter attached/uploaded the CV (existing flows).
 *   <li>{@code CANDIDATE_LINK} — the candidate applied through a public apply link;
 *       contact details (name/email/phone) are recorded on the application.
 * </ul>
 */
public enum ApplicationOrigin {
    RECRUITER,
    CANDIDATE_LINK
}
