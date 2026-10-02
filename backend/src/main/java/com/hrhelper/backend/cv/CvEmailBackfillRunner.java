package com.hrhelper.backend.cv;

import com.hrhelper.backend.common.ProcessingStatus;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Startup backfill of CV emails (REWORK 4 D46). On {@link ApplicationReadyEvent} it
 * enqueues — on the existing {@code extractExecutor}, so startup is never blocked —
 * a re-extraction of every READY CV that still has no email from any source. Work is
 * done in small batches with a short delay so the NLP service is not flooded
 * (§6). The job is idempotent: per-CV logic lives in
 * {@link CvExtractionService#backfillEmail} and re-running never duplicates work.
 */
@Component
public class CvEmailBackfillRunner {

    private static final Logger log = LoggerFactory.getLogger(CvEmailBackfillRunner.class);

    private final CvRepository cvRepository;
    private final CvProcessingService processingService;
    private final CvExtractionService extractionService;
    private final Executor executor;
    private final boolean enabled;
    private final int batchSize;
    private final long batchDelayMs;

    public CvEmailBackfillRunner(
            CvRepository cvRepository,
            CvProcessingService processingService,
            CvExtractionService extractionService,
            @Qualifier("extractExecutor") Executor executor,
            @Value("${hrhelper.cv.email-backfill.enabled:true}") boolean enabled,
            @Value("${hrhelper.cv.email-backfill.batch-size:25}") int batchSize,
            @Value("${hrhelper.cv.email-backfill.batch-delay-ms:1500}") long batchDelayMs) {
        this.cvRepository = cvRepository;
        this.processingService = processingService;
        this.extractionService = extractionService;
        this.executor = executor;
        this.enabled = enabled;
        this.batchSize = Math.max(1, batchSize);
        this.batchDelayMs = Math.max(0, batchDelayMs);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        if (!enabled) {
            return;
        }
        executor.execute(this::run);
    }

    /** Visible for tests / manual trigger; safe to call repeatedly (idempotent). */
    public void run() {
        List<UUID> ids = cvRepository.findIdsForEmailBackfill(ProcessingStatus.READY);
        if (ids.isEmpty()) {
            return;
        }
        log.info("Email backfill: {} CV(s) without an email — processing", ids.size());

        int processed = 0;
        int withEmail = 0;
        for (int i = 0; i < ids.size(); i++) {
            UUID id = ids.get(i);
            try {
                Cv cv = processingService.loadCv(id);
                String email = extractionService.backfillEmail(cv);
                if (email != null) {
                    withEmail++;
                }
                processed++;
            } catch (Exception ex) {
                log.warn("Email backfill failed for CV {}: {}", id, ex.toString());
            }
            // Throttle between batches so the NLP service is not flooded (§6).
            if (batchDelayMs > 0 && (i + 1) % batchSize == 0 && i + 1 < ids.size()) {
                sleep(batchDelayMs);
            }
        }
        log.info(
                "Email backfill done: {}/{} processed, {} now have an email",
                processed,
                ids.size(),
                withEmail);
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }
}
