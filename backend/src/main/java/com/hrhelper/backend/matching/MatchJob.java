package com.hrhelper.backend.matching;

import com.hrhelper.backend.common.Auditable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "match_jobs")
public class MatchJob extends Auditable {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    /** Null for per-JD jobs (REWORK 1 D24): a JD-wide match scores N CVs. */
    @Column(name = "cv_id")
    private UUID cvId;

    @Column(name = "jd_id", nullable = false)
    private UUID jdId;

    /**
     * Legacy flag (REWORK 1) kept read-only: {@code source_jd_ids} is now the
     * source of truth (REWORK 2 D27). New jobs still set this to
     * {@code !sourceJdIds.isEmpty()} so the history list keeps a truthful "pulled
     * from other positions" flag.
     */
    @Column(name = "include_other_applications", nullable = false)
    private boolean includeOtherApplications = false;

    /** The other JDs this match pulled applications from (REWORK 2 D27). */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "source_jd_ids")
    private List<UUID> sourceJdIds;

    /** Number of CVs in the dedup'd pool for a per-JD job. */
    @Column(name = "candidate_count")
    private Integer candidateCount;

    /** Top candidate's overall score — denormalised for the dashboard (D30). */
    @Column(name = "top_score")
    private Double topScore;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private JobStatus status = JobStatus.PENDING;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "finished_at")
    private Instant finishedAt;

    @Column(name = "error_code")
    private String errorCode;

    @Column(name = "error_detail")
    private String errorDetail;

    @Column(name = "overall_score")
    private Double overallScore;

    @Column(name = "overall_class")
    private String overallClass;

    @Column(name = "required_coverage")
    private Double requiredCoverage;

    @Column(name = "nice_to_have_coverage")
    private Double niceToHaveCoverage;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "result_json")
    private String resultJson;

    @Column(name = "pipeline_version")
    private String pipelineVersion;

    protected MatchJob() {
        // JPA
    }

    /**
     * Per-JD job (D24/D27): scores every eligible CV; {@code cvId} stays null.
     * {@code sourceJdIds} are the other JDs to pool applications from.
     */
    public MatchJob(UUID id, UUID ownerId, UUID jdId, List<UUID> sourceJdIds) {
        this.id = id;
        this.ownerId = ownerId;
        this.jdId = jdId;
        this.sourceJdIds = sourceJdIds == null ? List.of() : sourceJdIds;
        this.includeOtherApplications = !this.sourceJdIds.isEmpty();
        this.status = JobStatus.PENDING;
    }

    public void markRunning() {
        this.status = JobStatus.RUNNING;
        this.startedAt = Instant.now();
    }

    public void markFailed(String errorCode, String errorDetail) {
        this.status = JobStatus.FAILED;
        this.errorCode = errorCode;
        this.errorDetail = errorDetail;
        this.finishedAt = Instant.now();
    }

    /**
     * Per-JD success (D24/D25): the ranked candidate report lives in
     * {@code resultJson}; the scalar score columns stay null (they describe a
     * single CV, not a JD-wide ranking).
     */
    public void markSucceededJd(
            String resultJson, String pipelineVersion, int candidateCount, Double topScore) {
        this.status = JobStatus.SUCCEEDED;
        this.resultJson = resultJson;
        this.pipelineVersion = pipelineVersion;
        this.candidateCount = candidateCount;
        this.topScore = topScore;
        this.finishedAt = Instant.now();
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

    public UUID getJdId() {
        return jdId;
    }

    public boolean isIncludeOtherApplications() {
        return includeOtherApplications;
    }

    public List<UUID> getSourceJdIds() {
        return sourceJdIds == null ? List.of() : sourceJdIds;
    }

    public Integer getCandidateCount() {
        return candidateCount;
    }

    public Double getTopScore() {
        return topScore;
    }

    public JobStatus getStatus() {
        return status;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public Instant getFinishedAt() {
        return finishedAt;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getErrorDetail() {
        return errorDetail;
    }

    public Double getOverallScore() {
        return overallScore;
    }

    public String getOverallClass() {
        return overallClass;
    }

    public Double getRequiredCoverage() {
        return requiredCoverage;
    }

    public Double getNiceToHaveCoverage() {
        return niceToHaveCoverage;
    }

    public String getResultJson() {
        return resultJson;
    }

    public String getPipelineVersion() {
        return pipelineVersion;
    }
}
