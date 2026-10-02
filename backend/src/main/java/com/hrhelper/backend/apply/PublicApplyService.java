package com.hrhelper.backend.apply;

import com.hrhelper.backend.application.Application;
import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.apply.dto.PublicJobView;
import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvProcessor;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.io.IOException;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

/**
 * Handles public candidate applications (REWORK 3 D34–D39). Resolves the apply
 * token to an active JD (else a generic 404, D38), validates the submission, then:
 *
 * <ul>
 *   <li>dedups on (jd, email): the same candidate re-applying replaces their CV and
 *       refreshes contact details (D36);
 *   <li>dedups on content hash per owner: byte-identical files reuse the existing CV
 *       with no reprocessing (D22/D36);
 *   <li>creates the CV (if new) under the JD owner's library and an
 *       {@code Application(CANDIDATE_LINK)}, kicking off background extraction (D39);
 *   <li>removes the previous CV if a replacement leaves it unreferenced (D36 / Q3).
 * </ul>
 */
@Service
public class PublicApplyService {

    private static final Logger log = LoggerFactory.getLogger(PublicApplyService.class);

    // Lenient, defensive validators — the candidate sees helpful field errors,
    // while resource-existence stays a generic 404 (D38).
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    private static final Pattern PHONE = Pattern.compile("^[+]?[0-9 ()./-]{6,32}$");

    private final JobDescriptionRepository jdRepository;
    private final ApplicationRepository applicationRepository;
    private final CvRepository cvRepository;
    private final CvProcessor cvProcessor;
    private final long maxPdfBytes;

    public PublicApplyService(
            JobDescriptionRepository jdRepository,
            ApplicationRepository applicationRepository,
            CvRepository cvRepository,
            CvProcessor cvProcessor,
            @Value("${hrhelper.max-pdf-mb:20}") long maxPdfMb) {
        this.jdRepository = jdRepository;
        this.applicationRepository = applicationRepository;
        this.cvRepository = cvRepository;
        this.cvProcessor = cvProcessor;
        this.maxPdfBytes = maxPdfMb * 1024L * 1024L;
    }

    public enum ApplyStatus {
        RECEIVED,
        UPDATED
    }

    @Transactional(readOnly = true)
    public PublicJobView getJobView(String token) {
        JobDescription jd = resolveActiveJd(token);
        return new PublicJobView(jd.getTitle(), jd.getDescriptionText());
    }

    @Transactional
    public ApplyStatus apply(
            String token, String name, String email, String phone, MultipartFile file) {
        JobDescription jd = resolveActiveJd(token);
        UUID ownerId = jd.getOwnerId();
        UUID jdId = jd.getId();

        String cleanName = name == null ? "" : name.trim();
        String cleanEmail = email == null ? "" : email.trim();
        String cleanPhone = phone == null ? "" : phone.trim();
        validate(cleanName, cleanEmail, cleanPhone, file);

        byte[] bytes = readBytes(file);
        if (!PdfFileSupport.hasPdfMagic(bytes)) {
            throw new BadRequestException("invalid_file", "your CV must be a valid PDF file");
        }
        String hash = PdfFileSupport.sha256Hex(bytes);

        Optional<Application> existing =
                applicationRepository.findByJdIdAndCandidateEmailIgnoreCase(jdId, cleanEmail);
        CvRef ref = findOrCreateCv(ownerId, bytes, hash, file);

        if (existing.isPresent()) {
            return reapply(existing.get(), jdId, cleanName, cleanEmail, cleanPhone, ref);
        }
        ensureNoForeignLink(ref.cvId(), jdId, null);
        Application app =
                Application.fromCandidateLink(
                        UUID.randomUUID(),
                        ownerId,
                        ref.cvId(),
                        jdId,
                        cleanName,
                        cleanEmail,
                        cleanPhone);
        applicationRepository.save(app);
        if (ref.created()) {
            dispatchExtractionAfterCommit(ref.cvId());
        }
        log.info("Candidate application RECEIVED for jd {} (cv {})", jdId, ref.cvId());
        return ApplyStatus.RECEIVED;
    }

    /** Re-application of an existing (jd, email) candidate (D36). */
    private ApplyStatus reapply(
            Application app, UUID jdId, String name, String email, String phone, CvRef ref) {
        UUID oldCvId = app.getCvId();
        app.updateCandidateContact(name, email, phone);

        if (oldCvId.equals(ref.cvId())) {
            // Same file as the candidate's current CV — nothing to reprocess.
            applicationRepository.save(app);
            log.info("Candidate re-application UPDATED (contact only) for jd {}", jdId);
            return ApplyStatus.UPDATED;
        }

        ensureNoForeignLink(ref.cvId(), jdId, app.getId());
        app.setCvId(ref.cvId());
        applicationRepository.save(app);
        cleanupOrphan(oldCvId);
        if (ref.created()) {
            dispatchExtractionAfterCommit(ref.cvId());
        }
        log.info("Candidate re-application UPDATED (CV replaced) for jd {} (cv {})", jdId, ref.cvId());
        return ApplyStatus.UPDATED;
    }

    private record CvRef(UUID cvId, boolean created) {}

    /** Reuse an owner's byte-identical CV (D22), else create a new PENDING CV. */
    private CvRef findOrCreateCv(UUID ownerId, byte[] bytes, String hash, MultipartFile file) {
        return cvRepository
                .findByOwnerIdAndContentHash(ownerId, hash)
                .map(cv -> new CvRef(cv.getId(), false))
                .orElseGet(
                        () -> {
                            Cv cv =
                                    cvRepository.save(
                                            new Cv(
                                                    UUID.randomUUID(),
                                                    ownerId,
                                                    filename(file),
                                                    "application/pdf",
                                                    bytes.length,
                                                    bytes,
                                                    hash));
                            return new CvRef(cv.getId(), true);
                        });
    }

    /**
     * Guards the unique (cv_id, jd_id) link. With per-owner hash dedup, a CV is
     * byte-identical to a file — so a different candidate submitting the exact same
     * PDF to the same JD would collide. This essentially never happens with real
     * résumés; reject it generically rather than corrupt either application.
     */
    private void ensureNoForeignLink(UUID cvId, UUID jdId, UUID selfApplicationId) {
        applicationRepository
                .findByCvIdAndJdId(cvId, jdId)
                .filter(other -> selfApplicationId == null || !other.getId().equals(selfApplicationId))
                .ifPresent(
                        other -> {
                            throw new BadRequestException(
                                    "duplicate_submission",
                                    "this submission could not be accepted");
                        });
    }

    /** Delete the superseded CV if no application references it anymore (Q3). */
    private void cleanupOrphan(UUID cvId) {
        if (applicationRepository.countByCvId(cvId) == 0) {
            cvRepository.deleteById(cvId);
            log.info("Removed orphaned CV {} after replacement", cvId);
        }
    }

    private JobDescription resolveActiveJd(String token) {
        return jdRepository
                .findByApplyToken(token)
                .filter(JobDescription::isApplyLinkEnabled)
                .orElseThrow(() -> new NotFoundException("not found"));
    }

    private void validate(String name, String email, String phone, MultipartFile file) {
        if (name.isBlank()) {
            throw new BadRequestException("invalid_name", "please provide your name");
        }
        if (!EMAIL.matcher(email).matches()) {
            throw new BadRequestException("invalid_email", "please provide a valid email address");
        }
        if (!PHONE.matcher(phone).matches()) {
            throw new BadRequestException("invalid_phone", "please provide a valid phone number");
        }
        if (file == null || file.isEmpty()) {
            throw new BadRequestException("invalid_file", "please attach your CV as a PDF");
        }
        String contentType = file.getContentType();
        if (contentType == null || !contentType.toLowerCase().contains("application/pdf")) {
            throw new BadRequestException("invalid_file", "your CV must be a PDF file");
        }
        if (file.getSize() > maxPdfBytes) {
            throw new BadRequestException("payload_too_large", "your CV exceeds the size limit");
        }
    }

    private byte[] readBytes(MultipartFile file) {
        try {
            return file.getBytes();
        } catch (IOException e) {
            throw new BadRequestException("invalid_file", "your CV could not be read");
        }
    }

    private String filename(MultipartFile file) {
        return file.getOriginalFilename() != null ? file.getOriginalFilename() : "cv.pdf";
    }

    private void dispatchExtractionAfterCommit(UUID cvId) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            cvProcessor.process(cvId);
                        }
                    });
        } else {
            cvProcessor.process(cvId);
        }
    }
}
