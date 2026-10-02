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
 * Startup recovery for CV extraction. Extraction is dispatched only once, at upload
 * time, onto an in-memory executor queue ({@link CvService#uploadBatch} →
 * {@link CvProcessor}). Anything not finished in that burst would otherwise never
 * resolve, and the frontend — which polls while any CV is PENDING/PROCESSING — would
 * spin forever. Three ways a CV gets stranded:
 *
 * <ul>
 *   <li>the executor queue overflows on a large bulk upload and the dispatch is
 *       rejected, leaving the CV PENDING (now also softened by {@code CvService}
 *       catching the rejection);
 *   <li>the process restarts while tasks are still queued (the queue is in-memory);
 *   <li>the process is killed while a task is mid-flight, orphaning the row in
 *       PROCESSING.
 * </ul>
 *
 * On {@link ApplicationReadyEvent} this re-drives every CV still in PENDING/PROCESSING,
 * throttled so the NLP service is not flooded. Enqueued on the existing
 * {@code extractExecutor} so startup is never blocked. Idempotent: a CV that already
 * carries a cached extraction is marked READY without an NLP round-trip (see
 * {@link CvExtractionService#obtainExtraction}), so re-running never duplicates work.
 */
@Component
public class CvRecoveryRunner {

    private static final Logger log = LoggerFactory.getLogger(CvRecoveryRunner.class);

    private final CvRepository cvRepository;
    private final CvProcessor cvProcessor;
    private final Executor executor;
    private final boolean enabled;
    private final int batchSize;
    private final long batchDelayMs;

    public CvRecoveryRunner(
            CvRepository cvRepository,
            CvProcessor cvProcessor,
            @Qualifier("extractExecutor") Executor executor,
            @Value("${hrhelper.cv.recovery.enabled:true}") boolean enabled,
            @Value("${hrhelper.cv.recovery.batch-size:25}") int batchSize,
            @Value("${hrhelper.cv.recovery.batch-delay-ms:1500}") long batchDelayMs) {
        this.cvRepository = cvRepository;
        this.cvProcessor = cvProcessor;
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
        List<UUID> ids =
                cvRepository.findIdsByProcessingStatusIn(
                        List.of(ProcessingStatus.PENDING, ProcessingStatus.PROCESSING));
        if (ids.isEmpty()) {
            return;
        }
        log.info("CV recovery: {} CV(s) stuck in PENDING/PROCESSING — re-dispatching", ids.size());

        int processed = 0;
        for (int i = 0; i < ids.size(); i++) {
            UUID id = ids.get(i);
            try {
                cvProcessor.processNow(id); // synchronous: this thread, not the async pool
                processed++;
            } catch (Exception ex) {
                log.warn("CV recovery failed for {}: {}", id, ex.toString());
            }
            // Throttle between batches so the single-process NLP service is not flooded.
            if (batchDelayMs > 0 && (i + 1) % batchSize == 0 && i + 1 < ids.size()) {
                sleep(batchDelayMs);
            }
        }
        log.info("CV recovery done: {}/{} re-dispatched", processed, ids.size());
    }

    private void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }
}
