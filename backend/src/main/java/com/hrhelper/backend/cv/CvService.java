package com.hrhelper.backend.cv;

import com.hrhelper.backend.application.Application;
import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.common.EmailResolution;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.cv.dto.CvBulkUploadResponse;
import com.hrhelper.backend.cv.dto.CvUploadItemResult;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CvService {

    private static final Logger log = LoggerFactory.getLogger(CvService.class);

    private final CvRepository cvRepository;
    private final JobDescriptionRepository jdRepository;
    private final ApplicationRepository applicationRepository;
    private final CvProcessor cvProcessor;
    private final long maxPdfBytes;
    private final int maxBulkFiles;

    public CvService(
            CvRepository cvRepository,
            JobDescriptionRepository jdRepository,
            ApplicationRepository applicationRepository,
            CvProcessor cvProcessor,
            @Value("${hrhelper.max-pdf-mb:20}") long maxPdfMb,
            @Value("${hrhelper.cv.max-bulk-files:100}") int maxBulkFiles) {
        this.cvRepository = cvRepository;
        this.jdRepository = jdRepository;
        this.applicationRepository = applicationRepository;
        this.cvProcessor = cvProcessor;
        this.maxPdfBytes = maxPdfMb * 1024L * 1024L;
        this.maxBulkFiles = maxBulkFiles;
    }

    /**
     * Bulk upload (REWORK 1 D21/D22): 1..N PDFs, each processed independently.
     * Dedup by SHA-256 per owner. When {@code jdId} is present, an
     * {@link Application} is created for each file. Extraction runs in the
     * background; the response returns immediately with per-file statuses (202).
     */
    @Transactional
    public CvBulkUploadResponse uploadBatch(UUID ownerId, List<MultipartFile> files, UUID jdId) {
        if (files == null || files.isEmpty()) {
            throw new BadRequestException("empty_upload", "no files were uploaded");
        }
        if (files.size() > maxBulkFiles) {
            throw new BadRequestException(
                    "too_many_files", "at most " + maxBulkFiles + " files per upload are allowed");
        }

        JobDescription jd = null;
        if (jdId != null) {
            jd =
                    jdRepository
                            .findByIdAndOwnerId(jdId, ownerId)
                            .orElseThrow(() -> new NotFoundException("job description not found"));
        }

        List<CvUploadItemResult> results = new ArrayList<>();
        List<UUID> createdCvIds = new ArrayList<>();
        Map<String, UUID> seenHashes = new HashMap<>();

        for (MultipartFile file : files) {
            String filename =
                    file.getOriginalFilename() != null ? file.getOriginalFilename() : "cv.pdf";
            String rejection = validate(file);
            if (rejection != null) {
                results.add(CvUploadItemResult.rejected(filename, rejection));
                continue;
            }

            byte[] bytes;
            try {
                bytes = file.getBytes();
            } catch (IOException e) {
                results.add(CvUploadItemResult.rejected(filename, "upload_failed"));
                continue;
            }
            String hash = sha256Hex(bytes);

            UUID existingCvId = seenHashes.get(hash);
            if (existingCvId == null) {
                existingCvId =
                        cvRepository
                                .findByOwnerIdAndContentHash(ownerId, hash)
                                .map(Cv::getId)
                                .orElse(null);
            }

            boolean duplicate = existingCvId != null;
            UUID cvId;
            if (duplicate) {
                cvId = existingCvId;
            } else {
                Cv cv =
                        new Cv(
                                UUID.randomUUID(),
                                ownerId,
                                filename,
                                "application/pdf",
                                bytes.length,
                                bytes,
                                hash);
                cv = cvRepository.save(cv);
                cvId = cv.getId();
                createdCvIds.add(cvId);
                seenHashes.put(hash, cvId);
            }

            UUID applicationId = jd != null ? attachApplication(ownerId, jd.getId(), cvId) : null;
            results.add(
                    duplicate
                            ? CvUploadItemResult.duplicate(filename, cvId, applicationId)
                            : CvUploadItemResult.created(filename, cvId, applicationId));
        }

        dispatchExtraction(createdCvIds);
        return new CvBulkUploadResponse(results);
    }

    @Transactional(readOnly = true)
    public Page<Cv> list(UUID ownerId, Pageable pageable) {
        return cvRepository.findByOwnerId(ownerId, pageable);
    }

    @Transactional(readOnly = true)
    public Cv get(UUID ownerId, UUID cvId) {
        return cvRepository
                .findByIdAndOwnerId(cvId, ownerId)
                .orElseThrow(() -> new NotFoundException("CV not found"));
    }

    @Transactional
    public void delete(UUID ownerId, UUID cvId) {
        Cv cv = get(ownerId, cvId);
        cvRepository.delete(cv);
    }

    /**
     * Set or clear the recruiter's manual email override (REWORK 4 D45). Owner-scoped
     * (D6); a blank/null value clears the override (reverting to the extracted email);
     * a non-blank value is validated syntactically server-side and stored normalised.
     */
    @Transactional
    public Cv updateEmail(UUID ownerId, UUID cvId, String manualEmail) {
        Cv cv = get(ownerId, cvId);
        String normalized = EmailResolution.normalize(manualEmail);
        if (normalized != null && !EmailResolution.isValidSyntax(normalized)) {
            throw new BadRequestException("invalid_email", "not a valid email address");
        }
        cv.setManualEmail(normalized);
        return cvRepository.save(cv);
    }

    /** Idempotent: returns the existing application id, or creates a new link. */
    private UUID attachApplication(UUID ownerId, UUID jdId, UUID cvId) {
        return applicationRepository
                .findByCvIdAndJdId(cvId, jdId)
                .map(Application::getId)
                .orElseGet(
                        () -> {
                            Application app =
                                    applicationRepository.save(
                                            new Application(UUID.randomUUID(), ownerId, cvId, jdId));
                            return app.getId();
                        });
    }

    private void dispatchExtraction(List<UUID> cvIds) {
        if (cvIds.isEmpty()) {
            return;
        }
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            dispatchAll(cvIds);
                        }
                    });
        } else {
            dispatchAll(cvIds);
        }
    }

    /**
     * Submit each CV to the async extract worker, tolerating a saturated executor.
     * A {@link TaskRejectedException} must never escape here: this runs inside the
     * upload's {@code afterCommit} callback, where a thrown exception would propagate
     * out of the (already-committed) transaction and surface to the client as a 500
     * even though the rows were persisted. Any CV left undispatched stays PENDING and
     * is picked up by {@link CvRecoveryRunner} on the next startup.
     */
    private void dispatchAll(List<UUID> cvIds) {
        for (UUID cvId : cvIds) {
            try {
                cvProcessor.process(cvId);
            } catch (TaskRejectedException ex) {
                log.warn(
                        "extractExecutor saturated; CV {} left PENDING for recovery ({})",
                        cvId,
                        ex.getMessage());
            }
        }
    }

    /** Returns a rejection code, or {@code null} if the file is acceptable. */
    private String validate(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            return "empty_upload";
        }
        String contentType = file.getContentType();
        if (contentType == null || !contentType.toLowerCase().contains("application/pdf")) {
            return "invalid_content_type";
        }
        if (file.getSize() > maxPdfBytes) {
            return "payload_too_large";
        }
        return null;
    }

    private String sha256Hex(byte[] bytes) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
