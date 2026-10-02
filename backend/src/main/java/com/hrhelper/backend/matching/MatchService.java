package com.hrhelper.backend.matching;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.matching.dto.MatchJobResponse;
import jakarta.persistence.criteria.Predicate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Read side of match jobs (REWORK 1: jobs are per-JD; creation lives in
 * {@link JdMatchService}). Serves status + the stored report for polling and the
 * history list.
 */
@Service
public class MatchService {

    private static final Logger log = LoggerFactory.getLogger(MatchService.class);

    private final MatchJobRepository jobRepository;
    private final ObjectMapper nlpObjectMapper;

    public MatchService(
            MatchJobRepository jobRepository,
            @Qualifier("nlpObjectMapper") ObjectMapper nlpObjectMapper) {
        this.jobRepository = jobRepository;
        this.nlpObjectMapper = nlpObjectMapper;
    }

    @Transactional(readOnly = true)
    public MatchJobResponse get(UUID ownerId, UUID jobId) {
        MatchJob job =
                jobRepository
                        .findByIdAndOwnerId(jobId, ownerId)
                        .orElseThrow(() -> new NotFoundException("match job not found"));
        return toResponse(job);
    }

    @Transactional(readOnly = true)
    public Page<MatchJob> history(
            UUID ownerId, UUID jdId, JobStatus status, Pageable pageable) {
        Specification<MatchJob> spec =
                (root, query, cb) -> {
                    List<Predicate> predicates = new ArrayList<>();
                    predicates.add(cb.equal(root.get("ownerId"), ownerId));
                    if (jdId != null) {
                        predicates.add(cb.equal(root.get("jdId"), jdId));
                    }
                    if (status != null) {
                        predicates.add(cb.equal(root.get("status"), status));
                    }
                    return cb.and(predicates.toArray(new Predicate[0]));
                };
        return jobRepository.findAll(spec, pageable);
    }

    public MatchJobResponse toResponse(MatchJob job) {
        JsonNode result = null;
        if (job.getResultJson() != null) {
            try {
                result = nlpObjectMapper.readTree(job.getResultJson());
            } catch (Exception ex) {
                log.warn("Could not parse stored result_json for job {}", job.getId());
            }
        }
        return MatchJobResponse.from(job, result);
    }
}
