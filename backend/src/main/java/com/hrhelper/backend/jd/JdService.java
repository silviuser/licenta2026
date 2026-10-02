package com.hrhelper.backend.jd;

import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.common.ProcessingStatus;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.dto.JdRequest;
import com.hrhelper.backend.jd.dto.RequirementInput;
import com.hrhelper.backend.matching.MatchJobRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class JdService {

    private static final Logger log = LoggerFactory.getLogger(JdService.class);

    private final JobDescriptionRepository jdRepository;
    private final JdProcessor jdProcessor;
    private final ApplicationRepository applicationRepository;
    private final MatchJobRepository matchJobRepository;
    private final CvRepository cvRepository;

    public JdService(
            JobDescriptionRepository jdRepository,
            JdProcessor jdProcessor,
            ApplicationRepository applicationRepository,
            MatchJobRepository matchJobRepository,
            CvRepository cvRepository) {
        this.jdRepository = jdRepository;
        this.jdProcessor = jdProcessor;
        this.applicationRepository = applicationRepository;
        this.matchJobRepository = matchJobRepository;
        this.cvRepository = cvRepository;
    }

    /**
     * Creates a JD. With explicit requirements they are stored as-is (manual,
     * status READY). Without requirements but with description text, requirements
     * are extracted in the background (status PENDING → /v1/extract-jd) per D18.
     */
    @Transactional
    public JobDescription create(UUID ownerId, JdRequest request) {
        JobDescription jd =
                new JobDescription(
                        UUID.randomUUID(), ownerId, request.title(), request.descriptionText());

        List<RequirementInput> inputs = request.requirementsOrEmpty();
        boolean extractFromText =
                inputs.isEmpty()
                        && request.descriptionText() != null
                        && !request.descriptionText().isBlank();

        if (extractFromText) {
            jd.setProcessingStatus(ProcessingStatus.PENDING);
        } else {
            jd.replaceRequirements(buildRequirements(jd, inputs));
            jd.setProcessingStatus(ProcessingStatus.READY);
        }
        jd = jdRepository.save(jd);

        if (extractFromText) {
            dispatchExtraction(jd.getId(), request.descriptionText());
        }
        return jd;
    }

    @Transactional(readOnly = true)
    public Page<JobDescription> list(UUID ownerId, Pageable pageable) {
        return jdRepository.findByOwnerId(ownerId, pageable);
    }

    @Transactional(readOnly = true)
    public JobDescription get(UUID ownerId, UUID jdId) {
        return jdRepository
                .findByIdAndOwnerId(jdId, ownerId)
                .orElseThrow(() -> new NotFoundException("job description not found"));
    }

    /** Updates title + description. Requirements are managed via {@link #updateRequirements}. */
    @Transactional
    public JobDescription update(UUID ownerId, UUID jdId, JdRequest request) {
        JobDescription jd = get(ownerId, jdId);
        jd.setTitle(request.title());
        jd.setDescriptionText(request.descriptionText());
        if (request.requirements() != null) {
            jd.replaceRequirements(buildRequirements(jd, request.requirements()));
        }
        return jdRepository.save(jd);
    }

    /** Replaces the requirement list (REWORK 1 F4): add/remove/update importance. */
    @Transactional
    public JobDescription updateRequirements(
            UUID ownerId, UUID jdId, List<RequirementInput> inputs) {
        JobDescription jd = get(ownerId, jdId);
        jd.replaceRequirements(buildRequirements(jd, inputs));
        return jdRepository.save(jd);
    }

    /**
     * Deletes the JD plus its DB-cascaded children (requirements, applications,
     * match_jobs) and then drops any CVs that became orphaned by this delete —
     * i.e. CVs that no other JD's applications or match_jobs reference. Shared
     * CVs (same candidate applied to another position) are preserved.
     */
    @Transactional
    public void delete(UUID ownerId, UUID jdId) {
        JobDescription jd = get(ownerId, jdId);
        List<UUID> candidateCvIds = applicationRepository.findDistinctCvIdsByJdId(jdId);
        jdRepository.delete(jd);
        jdRepository.flush();
        for (UUID cvId : candidateCvIds) {
            if (applicationRepository.countByCvId(cvId) == 0
                    && matchJobRepository.countByCvId(cvId) == 0) {
                cvRepository.deleteById(cvId);
                log.info("Removed orphaned CV {} after deleting JD {}", cvId, jdId);
            }
        }
    }

    private List<Requirement> buildRequirements(
            JobDescription jd, List<RequirementInput> inputs) {
        List<Requirement> result = new ArrayList<>();
        for (int i = 0; i < inputs.size(); i++) {
            RequirementInput in = inputs.get(i);
            result.add(
                    new Requirement(
                            UUID.randomUUID(),
                            jd,
                            in.text(),
                            in.skillUri(),
                            in.skillLabel(),
                            in.importance(),
                            in.confidenceOrDefault(),
                            i,
                            in.sourceOrDefault()));
        }
        return result;
    }

    private void dispatchExtraction(UUID jdId, String text) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            jdProcessor.process(jdId, text);
                        }
                    });
        } else {
            jdProcessor.process(jdId, text);
        }
    }
}
