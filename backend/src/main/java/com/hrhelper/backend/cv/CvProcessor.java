package com.hrhelper.backend.cv;

import com.hrhelper.backend.nlp.NlpServiceException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

/**
 * Background CV extraction worker (REWORK 1 D17). Dispatched after the upload
 * transaction commits. Marks the CV PROCESSING, extracts + caches via
 * {@link CvExtractionService} (which marks it READY), or FAILED on error.
 */
@Component
public class CvProcessor {

    private static final Logger log = LoggerFactory.getLogger(CvProcessor.class);

    private final CvProcessingService processingService;
    private final CvExtractionService extractionService;

    public CvProcessor(
            CvProcessingService processingService, CvExtractionService extractionService) {
        this.processingService = processingService;
        this.extractionService = extractionService;
    }

    @Async("extractExecutor")
    public void process(UUID cvId) {
        processNow(cvId);
    }

    /**
     * Synchronous body of {@link #process}. Runs on the caller's thread, so the startup
     * recovery sweep ({@link CvRecoveryRunner}) can re-drive a stuck CV without routing
     * through the async executor. Idempotent: a CV that already carries a cached
     * extraction is marked READY by {@link CvExtractionService#obtainExtraction} with no
     * NLP round-trip, so re-running never duplicates work.
     */
    public void processNow(UUID cvId) {
        log.info("Processing CV {}", cvId);
        processingService.markProcessing(cvId);
        try {
            Cv cv = processingService.loadCv(cvId);
            extractionService.obtainExtraction(cv); // caches + marks READY
            log.info("CV {} READY", cvId);
        } catch (NlpServiceException ex) {
            log.warn("CV {} extraction FAILED: {} ({})", cvId, ex.getErrorCode(), ex.getMessage());
            processingService.markFailed(cvId, ex.getErrorCode() + ": " + ex.getMessage());
        } catch (Exception ex) {
            log.error("CV {} extraction FAILED with unexpected error", cvId, ex);
            processingService.markFailed(cvId, ex.getMessage());
        }
    }
}
