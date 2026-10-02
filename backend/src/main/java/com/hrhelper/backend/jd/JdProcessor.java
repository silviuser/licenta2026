package com.hrhelper.backend.jd;

import com.hrhelper.backend.nlp.NlpClient;
import com.hrhelper.backend.nlp.NlpServiceException;
import com.hrhelper.backend.nlp.dto.ExtractJdResponse;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

/**
 * Background JD requirement-extraction worker (REWORK 1 D18). Dispatched after
 * the create transaction commits. Marks the JD PROCESSING, calls
 * {@code /v1/extract-jd}, replaces requirements ({@code source=EXTRACTED}) and
 * marks READY, or FAILED on error. Transient NLP failures get one retry.
 */
@Component
public class JdProcessor {

    private static final Logger log = LoggerFactory.getLogger(JdProcessor.class);
    private static final int MAX_TRANSIENT_RETRIES = 2;

    private final JdProcessingService processingService;
    private final NlpClient nlpClient;

    public JdProcessor(JdProcessingService processingService, NlpClient nlpClient) {
        this.processingService = processingService;
        this.nlpClient = nlpClient;
    }

    @Async("extractExecutor")
    public void process(UUID jdId, String text) {
        log.info("Extracting requirements for JD {}", jdId);
        processingService.markProcessing(jdId);
        try {
            ExtractJdResponse response = extractWithRetry(jdId.toString(), text);
            processingService.markReadyWithRequirements(jdId, response.requirements());
            log.info("JD {} READY ({} requirements)", jdId, response.requirements().size());
        } catch (NlpServiceException ex) {
            log.warn("JD {} extraction FAILED: {} ({})", jdId, ex.getErrorCode(), ex.getMessage());
            processingService.markFailed(jdId, ex.getErrorCode() + ": " + ex.getMessage());
        } catch (Exception ex) {
            log.error("JD {} extraction FAILED with unexpected error", jdId, ex);
            processingService.markFailed(jdId, ex.getMessage());
        }
    }

    private ExtractJdResponse extractWithRetry(String jdId, String text) {
        int attempt = 0;
        while (true) {
            try {
                return nlpClient.extractJd(jdId, text, null);
            } catch (NlpServiceException ex) {
                attempt++;
                if (!ex.isTransient() || attempt >= MAX_TRANSIENT_RETRIES) {
                    throw ex;
                }
                log.info(
                        "Transient extract-jd failure ({}), retry {}/{}",
                        ex.getErrorCode(),
                        attempt,
                        MAX_TRANSIENT_RETRIES);
            }
        }
    }
}
