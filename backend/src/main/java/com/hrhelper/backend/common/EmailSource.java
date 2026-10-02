package com.hrhelper.backend.common;

/**
 * Where a candidate's effective email came from (REWORK 4 D42). Surfaced in DTOs
 * so the UI can badge the address (public form / manual / extracted / none).
 */
public enum EmailSource {
    /** Provided by the candidate via the public apply link (D34). */
    CANDIDATE_FORM,
    /** Set or corrected by the recruiter (D45). */
    MANUAL,
    /** Mined from the CV text by the NLP service (D40). */
    EXTRACTED,
    /** No address available from any source. */
    NONE
}
