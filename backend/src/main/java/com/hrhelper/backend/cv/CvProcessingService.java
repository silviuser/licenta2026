package com.hrhelper.backend.cv;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Short, self-contained transactions for the async CV extraction worker
 * (REWORK 1 §3.2). Mirrors {@code MatchJobStateService}: each write commits on
 * its own so no DB connection is held across the slow NLP round-trip.
 */
@Service
public class CvProcessingService {

    private final CvRepository cvRepository;

    public CvProcessingService(CvRepository cvRepository) {
        this.cvRepository = cvRepository;
    }

    @Transactional
    public void markProcessing(UUID cvId) {
        cvRepository
                .findById(cvId)
                .ifPresent(
                        cv -> {
                            cv.markProcessing();
                            cvRepository.save(cv);
                        });
    }

    @Transactional
    public void markReadyWithExtraction(
            UUID cvId, String detectedLanguage, String extractedEmail, String extractedJson) {
        cvRepository
                .findById(cvId)
                .ifPresent(
                        cv -> {
                            cv.setDetectedLanguage(detectedLanguage);
                            cv.setExtractedEmail(extractedEmail);
                            cv.setExtractedCandidates(extractedJson);
                            cv.markReady();
                            cvRepository.save(cv);
                        });
    }

    /** Backfill (D46): set only the extracted email when the cache is already fresh. */
    @Transactional
    public void setExtractedEmail(UUID cvId, String extractedEmail) {
        cvRepository
                .findById(cvId)
                .ifPresent(
                        cv -> {
                            cv.setExtractedEmail(extractedEmail);
                            cvRepository.save(cv);
                        });
    }

    @Transactional
    public void markFailed(UUID cvId, String error) {
        cvRepository
                .findById(cvId)
                .ifPresent(
                        cv -> {
                            cv.markFailed(truncate(error));
                            cvRepository.save(cv);
                        });
    }

    @Transactional(readOnly = true)
    public Cv loadCv(UUID cvId) {
        return cvRepository.findById(cvId).orElseThrow();
    }

    private String truncate(String s) {
        if (s == null) {
            return null;
        }
        return s.length() > 4000 ? s.substring(0, 4000) : s;
    }
}
