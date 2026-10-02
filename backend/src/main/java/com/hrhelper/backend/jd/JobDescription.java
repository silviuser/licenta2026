package com.hrhelper.backend.jd;

import com.hrhelper.backend.common.Auditable;
import com.hrhelper.backend.common.ProcessingStatus;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "job_descriptions")
public class JobDescription extends Auditable {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(name = "title", nullable = false)
    private String title;

    @Column(name = "description_text")
    private String descriptionText;

    /** Background requirement-extraction lifecycle (D18 / D26). */
    @Enumerated(EnumType.STRING)
    @Column(name = "processing_status", nullable = false)
    private ProcessingStatus processingStatus = ProcessingStatus.READY;

    @Column(name = "processing_error")
    private String processingError;

    /** Public apply link (REWORK 3 D32/D33). The token is the capability credential. */
    @Column(name = "apply_token")
    private String applyToken;

    @Column(name = "apply_link_enabled", nullable = false)
    private boolean applyLinkEnabled = false;

    @OneToMany(
            mappedBy = "jobDescription",
            cascade = CascadeType.ALL,
            orphanRemoval = true,
            fetch = jakarta.persistence.FetchType.EAGER)
    @OrderBy("sortOrder ASC")
    private List<Requirement> requirements = new ArrayList<>();

    protected JobDescription() {
        // JPA
    }

    public JobDescription(UUID id, UUID ownerId, String title, String descriptionText) {
        this.id = id;
        this.ownerId = ownerId;
        this.title = title;
        this.descriptionText = descriptionText;
    }

    public UUID getId() {
        return id;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getDescriptionText() {
        return descriptionText;
    }

    public void setDescriptionText(String descriptionText) {
        this.descriptionText = descriptionText;
    }

    public List<Requirement> getRequirements() {
        return requirements;
    }

    public void replaceRequirements(List<Requirement> newRequirements) {
        this.requirements.clear();
        this.requirements.addAll(newRequirements);
    }

    public ProcessingStatus getProcessingStatus() {
        return processingStatus;
    }

    public String getProcessingError() {
        return processingError;
    }

    public void setProcessingStatus(ProcessingStatus processingStatus) {
        this.processingStatus = processingStatus;
    }

    public void markProcessing() {
        this.processingStatus = ProcessingStatus.PROCESSING;
        this.processingError = null;
    }

    public void markReady() {
        this.processingStatus = ProcessingStatus.READY;
        this.processingError = null;
    }

    public void markFailed(String error) {
        this.processingStatus = ProcessingStatus.FAILED;
        this.processingError = error;
    }

    public String getApplyToken() {
        return applyToken;
    }

    public void setApplyToken(String applyToken) {
        this.applyToken = applyToken;
    }

    public boolean isApplyLinkEnabled() {
        return applyLinkEnabled;
    }

    public void setApplyLinkEnabled(boolean applyLinkEnabled) {
        this.applyLinkEnabled = applyLinkEnabled;
    }
}
