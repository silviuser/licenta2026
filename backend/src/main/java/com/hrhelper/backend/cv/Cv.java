package com.hrhelper.backend.cv;

import com.hrhelper.backend.common.Auditable;
import com.hrhelper.backend.common.ProcessingStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "cvs")
public class Cv extends Auditable {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(name = "original_filename", nullable = false)
    private String originalFilename;

    @Column(name = "content_type", nullable = false)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Lob
    @JdbcTypeCode(SqlTypes.VARBINARY)
    @Column(name = "pdf_data", nullable = false)
    private byte[] pdfData;

    @Column(name = "detected_language")
    private String detectedLanguage;

    /** SHA-256 (hex) of the PDF bytes — unique per owner for dedup (D22). */
    @Column(name = "content_hash")
    private String contentHash;

    /** Background extraction lifecycle (D17 / D26). */
    @Enumerated(EnumType.STRING)
    @Column(name = "processing_status", nullable = false)
    private ProcessingStatus processingStatus = ProcessingStatus.PENDING;

    @Column(name = "processing_error")
    private String processingError;

    /** Cached {@code ExtractResponse} JSON (D13). Invalidated on re-upload. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "extracted_candidates")
    private String extractedCandidates;

    /** Email mined from the CV text (REWORK 4 D42) — from NLP {@code contact.primary_email}. */
    @Column(name = "extracted_email")
    private String extractedEmail;

    /** Recruiter-set email (REWORK 4 D45) — overrides {@link #extractedEmail} when present. */
    @Column(name = "manual_email")
    private String manualEmail;

    protected Cv() {
        // JPA
    }

    public Cv(
            UUID id,
            UUID ownerId,
            String originalFilename,
            String contentType,
            long sizeBytes,
            byte[] pdfData,
            String contentHash) {
        this.id = id;
        this.ownerId = ownerId;
        this.originalFilename = originalFilename;
        this.contentType = contentType;
        this.sizeBytes = sizeBytes;
        this.pdfData = pdfData;
        this.contentHash = contentHash;
        this.processingStatus = ProcessingStatus.PENDING;
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

    public UUID getId() {
        return id;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public String getOriginalFilename() {
        return originalFilename;
    }

    public String getContentType() {
        return contentType;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }

    public byte[] getPdfData() {
        return pdfData;
    }

    public String getDetectedLanguage() {
        return detectedLanguage;
    }

    public void setDetectedLanguage(String detectedLanguage) {
        this.detectedLanguage = detectedLanguage;
    }

    public String getExtractedCandidates() {
        return extractedCandidates;
    }

    public void setExtractedCandidates(String extractedCandidates) {
        this.extractedCandidates = extractedCandidates;
    }

    public String getExtractedEmail() {
        return extractedEmail;
    }

    public void setExtractedEmail(String extractedEmail) {
        this.extractedEmail = extractedEmail;
    }

    public String getManualEmail() {
        return manualEmail;
    }

    public void setManualEmail(String manualEmail) {
        this.manualEmail = manualEmail;
    }

    public String getContentHash() {
        return contentHash;
    }

    public ProcessingStatus getProcessingStatus() {
        return processingStatus;
    }

    public String getProcessingError() {
        return processingError;
    }
}
