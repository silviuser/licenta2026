package com.hrhelper.backend.jd;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "requirements")
public class Requirement {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "jd_id", nullable = false)
    private JobDescription jobDescription;

    @Column(name = "text", nullable = false)
    private String text;

    @Column(name = "skill_uri")
    private String skillUri;

    @Column(name = "skill_label")
    private String skillLabel;

    /** {@code required} or {@code nice_to_have}. */
    @Column(name = "importance", nullable = false)
    private String importance;

    @Column(name = "confidence", nullable = false)
    private double confidence = 0.5;

    @Column(name = "sort_order", nullable = false)
    private int sortOrder;

    /** Provenance: {@code EXTRACTED} (NLP) or {@code MANUAL} (recruiter). */
    @Enumerated(EnumType.STRING)
    @Column(name = "source", nullable = false)
    private RequirementSource source = RequirementSource.MANUAL;

    protected Requirement() {
        // JPA
    }

    public Requirement(
            UUID id,
            JobDescription jobDescription,
            String text,
            String skillUri,
            String skillLabel,
            String importance,
            double confidence,
            int sortOrder,
            RequirementSource source) {
        this.id = id;
        this.jobDescription = jobDescription;
        this.text = text;
        this.skillUri = skillUri;
        this.skillLabel = skillLabel;
        this.importance = importance;
        this.confidence = confidence;
        this.sortOrder = sortOrder;
        this.source = source;
    }

    public UUID getId() {
        return id;
    }

    public JobDescription getJobDescription() {
        return jobDescription;
    }

    public String getText() {
        return text;
    }

    public String getSkillUri() {
        return skillUri;
    }

    public String getSkillLabel() {
        return skillLabel;
    }

    public String getImportance() {
        return importance;
    }

    public double getConfidence() {
        return confidence;
    }

    public int getSortOrder() {
        return sortOrder;
    }

    public RequirementSource getSource() {
        return source;
    }
}
