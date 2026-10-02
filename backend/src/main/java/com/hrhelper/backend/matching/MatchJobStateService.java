package com.hrhelper.backend.matching;

import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Short, self-contained transactions for the async worker. Kept separate from
 * {@link MatchProcessor} so each DB write commits independently and no DB
 * connection is held across the slow NLP round-trips.
 */
@Service
public class MatchJobStateService {

    private final MatchJobRepository jobRepository;
    private final CvRepository cvRepository;
    private final JobDescriptionRepository jdRepository;

    public MatchJobStateService(
            MatchJobRepository jobRepository,
            CvRepository cvRepository,
            JobDescriptionRepository jdRepository) {
        this.jobRepository = jobRepository;
        this.cvRepository = cvRepository;
        this.jdRepository = jdRepository;
    }

    @Transactional
    public void markRunning(UUID jobId) {
        jobRepository
                .findById(jobId)
                .ifPresent(
                        job -> {
                            job.markRunning();
                            jobRepository.save(job);
                        });
    }

    @Transactional
    public void markFailed(UUID jobId, String errorCode, String errorDetail) {
        jobRepository
                .findById(jobId)
                .ifPresent(
                        job -> {
                            job.markFailed(errorCode, truncate(errorDetail));
                            jobRepository.save(job);
                        });
    }

    @Transactional
    public void markSucceededJd(
            UUID jobId,
            String resultJson,
            String pipelineVersion,
            int candidateCount,
            Double topScore) {
        jobRepository
                .findById(jobId)
                .ifPresent(
                        job -> {
                            job.markSucceededJd(resultJson, pipelineVersion, candidateCount, topScore);
                            jobRepository.save(job);
                        });
    }

    @Transactional(readOnly = true)
    public Cv loadCv(UUID cvId) {
        return cvRepository.findById(cvId).orElseThrow();
    }

    @Transactional(readOnly = true)
    public JobDescription loadJd(UUID jdId) {
        JobDescription jd = jdRepository.findById(jdId).orElseThrow();
        jd.getRequirements().size(); // force-init the EAGER collection inside the tx
        return jd;
    }

    private String truncate(String s) {
        if (s == null) {
            return null;
        }
        return s.length() > 4000 ? s.substring(0, 4000) : s;
    }
}
