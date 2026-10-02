package com.hrhelper.backend.application;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * A CV ↔ JD link (REWORK 1 D20). One physical CV exists once in the recruiter's
 * library; applying it to a JD is an {@code Application}. Unique {@code (cvId, jdId)}
 * keeps attaching idempotent.
 *
 * <p>An application carries its {@link ApplicationOrigin} (REWORK 3 D37): recruiter
 * flows leave the candidate fields null; a {@code CANDIDATE_LINK} application
 * records the applicant's name, email and phone and its submission time.
 */
@Entity
@Table(name = "applications")
public class Application {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(name = "cv_id", nullable = false)
    private UUID cvId;

    @Column(name = "jd_id", nullable = false)
    private UUID jdId;

    @Enumerated(EnumType.STRING)
    @Column(name = "origin", nullable = false)
    private ApplicationOrigin origin = ApplicationOrigin.RECRUITER;

    @Column(name = "candidate_name")
    private String candidateName;

    @Column(name = "candidate_email")
    private String candidateEmail;

    @Column(name = "candidate_phone")
    private String candidatePhone;

    @Column(name = "applied_at")
    private Instant appliedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Application() {
        // JPA
    }

    /** Recruiter-created link (bulk upload / attach-from-library). */
    public Application(UUID id, UUID ownerId, UUID cvId, UUID jdId) {
        this.id = id;
        this.ownerId = ownerId;
        this.cvId = cvId;
        this.jdId = jdId;
        this.origin = ApplicationOrigin.RECRUITER;
        this.createdAt = Instant.now();
    }

    /** A submission through a public apply link (REWORK 3 D37). */
    public static Application fromCandidateLink(
            UUID id,
            UUID ownerId,
            UUID cvId,
            UUID jdId,
            String candidateName,
            String candidateEmail,
            String candidatePhone) {
        Application app = new Application();
        app.id = id;
        app.ownerId = ownerId;
        app.cvId = cvId;
        app.jdId = jdId;
        app.origin = ApplicationOrigin.CANDIDATE_LINK;
        app.candidateName = candidateName;
        app.candidateEmail = candidateEmail;
        app.candidatePhone = candidatePhone;
        Instant now = Instant.now();
        app.createdAt = now;
        app.appliedAt = now;
        return app;
    }

    public UUID getId() {
        return id;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public UUID getCvId() {
        return cvId;
    }

    /** Repoint this application at a replacement CV (D36 re-application). */
    public void setCvId(UUID cvId) {
        this.cvId = cvId;
    }

    public UUID getJdId() {
        return jdId;
    }

    public ApplicationOrigin getOrigin() {
        return origin;
    }

    public String getCandidateName() {
        return candidateName;
    }

    public String getCandidateEmail() {
        return candidateEmail;
    }

    public String getCandidatePhone() {
        return candidatePhone;
    }

    public Instant getAppliedAt() {
        return appliedAt;
    }

    /** Refresh the candidate's contact details + submission time on re-application (D36). */
    public void updateCandidateContact(String name, String email, String phone) {
        this.candidateName = name;
        this.candidateEmail = email;
        this.candidatePhone = phone;
        this.appliedAt = Instant.now();
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
