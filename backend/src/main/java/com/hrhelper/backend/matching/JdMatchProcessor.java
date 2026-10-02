package com.hrhelper.backend.matching;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hrhelper.backend.common.EmailResolution;
import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvExtractionService;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.Requirement;
import com.hrhelper.backend.matching.dto.CandidateReport;
import com.hrhelper.backend.matching.dto.MatchReport;
import com.hrhelper.backend.nlp.NlpClient;
import com.hrhelper.backend.nlp.NlpServiceException;
import com.hrhelper.backend.nlp.dto.ExtractResponse;
import com.hrhelper.backend.nlp.dto.MatchRequest;
import com.hrhelper.backend.nlp.dto.MatchResponse;
import com.hrhelper.backend.nlp.dto.RequirementDto;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

/**
 * Per-JD match worker (REWORK 1 D24/D25). Builds the dedup'd CV pool, scores
 * each CV against the JD (reusing the cached extraction, lazily extracting if a
 * CV was never processed — a single CV failing never fails the job), then
 * persists a deterministic ranked report. Transient NLP failures get one retry.
 */
@Component
public class JdMatchProcessor {

    private static final Logger log = LoggerFactory.getLogger(JdMatchProcessor.class);
    private static final int MAX_TRANSIENT_RETRIES = 2;

    private final MatchJobStateService state;
    private final MatchPoolService poolService;
    private final CvExtractionService extractionService;
    private final NlpClient nlpClient;
    private final ExplanationService explanationService;
    private final ObjectMapper nlpObjectMapper;

    public JdMatchProcessor(
            MatchJobStateService state,
            MatchPoolService poolService,
            CvExtractionService extractionService,
            NlpClient nlpClient,
            ExplanationService explanationService,
            @Qualifier("nlpObjectMapper") ObjectMapper nlpObjectMapper) {
        this.state = state;
        this.poolService = poolService;
        this.extractionService = extractionService;
        this.nlpClient = nlpClient;
        this.explanationService = explanationService;
        this.nlpObjectMapper = nlpObjectMapper;
    }

    private record Scored(PoolEntry entry, MatchResponse mr) {}

    private record Failed(PoolEntry entry, String errorCode) {}

    @Async("matchExecutor")
    public void process(UUID jobId, UUID jdId, UUID ownerId, List<UUID> sourceJdIds) {
        log.info(
                "Processing per-JD match job {} (jd={}, {} source JDs)",
                jobId,
                jdId,
                sourceJdIds == null ? 0 : sourceJdIds.size());
        state.markRunning(jobId);
        try {
            JobDescription jd = state.loadJd(jdId);
            List<RequirementDto> requirements = mapRequirements(jd.getRequirements());
            List<PoolEntry> pool = poolService.buildPool(ownerId, jdId, sourceJdIds);

            List<Scored> scored = new ArrayList<>();
            List<Failed> failed = new ArrayList<>();
            String pipelineVersion = null;

            for (PoolEntry entry : pool) {
                Cv cv = entry.cv();
                try {
                    ExtractResponse enriched = extractionService.obtainExtraction(cv);
                    MatchRequest request =
                            new MatchRequest(
                                    cv.getId().toString(),
                                    enriched,
                                    jd.getId().toString(),
                                    requirements);
                    MatchResponse mr = matchWithRetry(request);
                    if (pipelineVersion == null) {
                        pipelineVersion = mr.pipelineVersion();
                    }
                    scored.add(new Scored(entry, mr));
                } catch (NlpServiceException ex) {
                    log.warn("CV {} match FAILED in job {}: {}", cv.getId(), jobId, ex.getErrorCode());
                    failed.add(new Failed(entry, ex.getErrorCode()));
                } catch (Exception ex) {
                    log.error("CV {} match FAILED in job {}", cv.getId(), jobId, ex);
                    failed.add(new Failed(entry, "internal_error"));
                }
            }

            MatchReport report = buildReport(jd, sourceJdIds, scored, failed);
            Double topScore = scored.isEmpty() ? null : report.candidates().get(0).overallScore();
            String json = nlpObjectMapper.writeValueAsString(report);
            state.markSucceededJd(
                    jobId, json, pipelineVersion != null ? pipelineVersion : "n/a", pool.size(), topScore);
            log.info("Per-JD match job {} SUCCEEDED ({} candidates)", jobId, pool.size());
        } catch (Exception ex) {
            log.error("Per-JD match job {} FAILED", jobId, ex);
            state.markFailed(jobId, "internal_error", ex.getMessage());
        }
    }

    private MatchReport buildReport(
            JobDescription jd, List<UUID> sourceJdIds, List<Scored> scored, List<Failed> failed) {
        scored.sort(Comparator.comparingDouble((Scored s) -> s.mr().overallScore()).reversed());

        List<CandidateReport> candidates = new ArrayList<>();
        int rank = 1;
        for (Scored s : scored) {
            MatchResponse mr = s.mr();
            PoolEntry e = s.entry();
            EmailResolution.Resolved email = resolveEmail(e);
            candidates.add(
                    new CandidateReport(
                            rank++,
                            e.cv().getId(),
                            e.cv().getOriginalFilename(),
                            e.source(),
                            e.sourceJdId(),
                            e.sourceJdTitle(),
                            e.origin(),
                            e.candidateName(),
                            e.candidateEmail(),
                            e.candidatePhone(),
                            email.email(),
                            email.source(),
                            "SUCCEEDED",
                            mr.overallScore(),
                            mr.overallClass(),
                            mr.requiredCoverage(),
                            mr.niceToHaveCoverage(),
                            explanationService.matchedSkills(mr),
                            explanationService.missingSkills(mr),
                            explanationService.explain(mr),
                            null));
        }
        for (Failed f : failed) {
            PoolEntry e = f.entry();
            EmailResolution.Resolved email = resolveEmail(e);
            candidates.add(
                    new CandidateReport(
                            null,
                            e.cv().getId(),
                            e.cv().getOriginalFilename(),
                            e.source(),
                            e.sourceJdId(),
                            e.sourceJdTitle(),
                            e.origin(),
                            e.candidateName(),
                            e.candidateEmail(),
                            e.candidatePhone(),
                            email.email(),
                            email.source(),
                            "FAILED",
                            null,
                            null,
                            null,
                            null,
                            List.of(),
                            null,
                            null,
                            f.errorCode()));
        }

        int requiredTotal =
                (int) jd.getRequirements().stream().filter(r -> "required".equals(r.getImportance())).count();
        int niceToHaveTotal = jd.getRequirements().size() - requiredTotal;

        return new MatchReport(
                jd.getId(),
                sourceJdIds == null ? List.of() : sourceJdIds,
                Instant.now(),
                requiredTotal,
                niceToHaveTotal,
                candidates);
    }

    /** Resolve the effective contact email (D42): form → manual → extracted → none. */
    private EmailResolution.Resolved resolveEmail(PoolEntry e) {
        return EmailResolution.resolve(
                e.candidateEmail(), e.cv().getManualEmail(), e.cv().getExtractedEmail());
    }

    private MatchResponse matchWithRetry(MatchRequest request) {
        int attempt = 0;
        while (true) {
            try {
                return nlpClient.match(request);
            } catch (NlpServiceException ex) {
                attempt++;
                if (!ex.isTransient() || attempt >= MAX_TRANSIENT_RETRIES) {
                    throw ex;
                }
                log.info(
                        "Transient match failure ({}), retry {}/{}",
                        ex.getErrorCode(),
                        attempt,
                        MAX_TRANSIENT_RETRIES);
            }
        }
    }

    private List<RequirementDto> mapRequirements(List<Requirement> requirements) {
        return requirements.stream()
                .map(
                        r ->
                                new RequirementDto(
                                        r.getText(),
                                        r.getSkillUri(),
                                        r.getSkillLabel(),
                                        r.getImportance(),
                                        r.getConfidence()))
                .toList();
    }
}
