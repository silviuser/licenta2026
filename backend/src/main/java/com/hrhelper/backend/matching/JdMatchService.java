package com.hrhelper.backend.matching;

import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * Creates and dispatches a per-JD match job (REWORK 1 D24). Validates JD
 * ownership, persists a PENDING job, and starts the async worker after commit.
 */
@Service
public class JdMatchService {

    private static final Logger log = LoggerFactory.getLogger(JdMatchService.class);

    private final MatchJobRepository jobRepository;
    private final JobDescriptionRepository jdRepository;
    private final JdMatchProcessor processor;

    public JdMatchService(
            MatchJobRepository jobRepository,
            JobDescriptionRepository jdRepository,
            JdMatchProcessor processor) {
        this.jobRepository = jobRepository;
        this.jdRepository = jdRepository;
        this.processor = processor;
    }

    @Transactional
    public MatchJob createMatch(UUID ownerId, UUID jdId, List<UUID> requestedSourceJdIds) {
        JobDescription jd =
                jdRepository
                        .findByIdAndOwnerId(jdId, ownerId)
                        .orElseThrow(() -> new NotFoundException("job description not found"));

        // The NLP scorer rejects an empty requirement list (it is a client bug):
        // fail fast with a clear error instead of launching a job whose every
        // candidate fails opaquely (REWORK 1 smoke-test hardening).
        if (jd.getRequirements().isEmpty()) {
            throw new BadRequestException(
                    "no_requirements",
                    "this position has no requirements to match against; add requirements first");
        }

        List<UUID> sourceJdIds = validateSources(ownerId, jdId, requestedSourceJdIds);

        MatchJob job = new MatchJob(UUID.randomUUID(), ownerId, jdId, sourceJdIds);
        job = jobRepository.save(job);
        log.info(
                "Created per-JD match job {} for jd {} (owner {}, {} source JDs)",
                job.getId(),
                jdId,
                ownerId,
                sourceJdIds.size());

        final UUID jobId = job.getId();
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            processor.process(jobId, jdId, ownerId, sourceJdIds);
                        }
                    });
        } else {
            processor.process(jobId, jdId, ownerId, sourceJdIds);
        }
        return job;
    }

    /**
     * Validates selective-pooling sources (D28): dedup, reject the target JD, and
     * require every source to exist and belong to the recruiter (D6 isolation).
     */
    private List<UUID> validateSources(UUID ownerId, UUID jdId, List<UUID> requested) {
        if (requested == null || requested.isEmpty()) {
            return List.of();
        }
        List<UUID> deduped = new java.util.ArrayList<>(new LinkedHashSet<>(requested));
        for (UUID sourceId : deduped) {
            if (sourceId.equals(jdId)) {
                throw new BadRequestException(
                        "source_includes_target",
                        "a position cannot pull applications from itself");
            }
            jdRepository
                    .findByIdAndOwnerId(sourceId, ownerId)
                    .orElseThrow(() -> new NotFoundException("source job description not found"));
        }
        return deduped;
    }
}
