package com.hrhelper.backend.matching;

import com.hrhelper.backend.application.Application;
import com.hrhelper.backend.cv.Cv;
import java.util.UUID;

/**
 * One CV in a per-JD match pool, tagged with how it got there:
 * {@code DIRECT} (applied to this JD) or {@code OTHER_JD} (pulled in via selective
 * pooling, D27). For {@code OTHER_JD} entries {@code sourceJdId}/{@code sourceJdTitle}
 * record which source position it came from (D29); both are null for {@code DIRECT}.
 *
 * <p>{@code origin} + candidate contact fields carry the application's provenance
 * (REWORK 3 D37): set for candidate-link submissions, null for recruiter ones.
 */
public record PoolEntry(
        Cv cv,
        String source,
        UUID sourceJdId,
        String sourceJdTitle,
        String origin,
        String candidateName,
        String candidateEmail,
        String candidatePhone) {

    public static final String DIRECT = "DIRECT";
    public static final String OTHER_JD = "OTHER_JD";

    /** A directly-applied candidate (no source position). */
    public static PoolEntry direct(Cv cv, Application app) {
        return new PoolEntry(
                cv,
                DIRECT,
                null,
                null,
                app.getOrigin().name(),
                app.getCandidateName(),
                app.getCandidateEmail(),
                app.getCandidatePhone());
    }

    /** A candidate pulled in from another position. */
    public static PoolEntry fromOtherJd(
            Cv cv, UUID sourceJdId, String sourceJdTitle, Application app) {
        return new PoolEntry(
                cv,
                OTHER_JD,
                sourceJdId,
                sourceJdTitle,
                app.getOrigin().name(),
                app.getCandidateName(),
                app.getCandidateEmail(),
                app.getCandidatePhone());
    }
}
