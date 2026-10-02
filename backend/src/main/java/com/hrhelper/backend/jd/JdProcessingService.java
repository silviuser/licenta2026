package com.hrhelper.backend.jd;

import com.hrhelper.backend.nlp.dto.JdRequirementDto;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Short, self-contained transactions for the async JD extraction worker
 * (REWORK 1 §3.2). Each write commits independently — no DB connection is held
 * across the NLP round-trip.
 */
@Service
public class JdProcessingService {

    private final JobDescriptionRepository jdRepository;

    public JdProcessingService(JobDescriptionRepository jdRepository) {
        this.jdRepository = jdRepository;
    }

    @Transactional
    public void markProcessing(UUID jdId) {
        jdRepository
                .findById(jdId)
                .ifPresent(
                        jd -> {
                            jd.markProcessing();
                            jdRepository.save(jd);
                        });
    }

    /**
     * Replaces the JD's requirements with the extracted candidates (all
     * {@code source=EXTRACTED}, default {@code importance=required} per D18) and
     * marks the JD READY.
     */
    @Transactional
    public void markReadyWithRequirements(UUID jdId, List<JdRequirementDto> extracted) {
        jdRepository
                .findById(jdId)
                .ifPresent(
                        jd -> {
                            List<Requirement> reqs = new ArrayList<>();
                            for (int i = 0; i < extracted.size(); i++) {
                                JdRequirementDto e = extracted.get(i);
                                reqs.add(
                                        new Requirement(
                                                UUID.randomUUID(),
                                                jd,
                                                e.text(),
                                                e.skillUri(),
                                                e.skillLabel(),
                                                "required",
                                                e.confidence(),
                                                i,
                                                RequirementSource.EXTRACTED));
                            }
                            jd.replaceRequirements(reqs);
                            jd.markReady();
                            jdRepository.save(jd);
                        });
    }

    @Transactional
    public void markFailed(UUID jdId, String error) {
        jdRepository
                .findById(jdId)
                .ifPresent(
                        jd -> {
                            jd.markFailed(truncate(error));
                            jdRepository.save(jd);
                        });
    }

    private String truncate(String s) {
        if (s == null) {
            return null;
        }
        return s.length() > 4000 ? s.substring(0, 4000) : s;
    }
}
