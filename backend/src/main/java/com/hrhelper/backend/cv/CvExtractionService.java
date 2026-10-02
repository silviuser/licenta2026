package com.hrhelper.backend.cv;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hrhelper.backend.nlp.NlpClient;
import com.hrhelper.backend.nlp.NlpServiceException;
import com.hrhelper.backend.nlp.dto.ExtractResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

/**
 * Obtains a CV's {@code ExtractResponse}, reusing the per-CV cache (D13) or
 * calling {@code /v1/extract} once and caching it. Shared by the upload-time
 * background worker ({@link CvProcessor}) and the per-JD match worker, which may
 * lazily extract a CV that was never processed (REWORK 1 D24 — "wait/trigger,
 * don't fail"). Transient NLP failures get one retry; 4xx never do.
 */
@Service
public class CvExtractionService {

    private static final Logger log = LoggerFactory.getLogger(CvExtractionService.class);
    private static final int MAX_TRANSIENT_RETRIES = 2;

    private final NlpClient nlpClient;
    private final CvProcessingService processingService;
    private final ObjectMapper nlpObjectMapper;

    public CvExtractionService(
            NlpClient nlpClient,
            CvProcessingService processingService,
            @Qualifier("nlpObjectMapper") ObjectMapper nlpObjectMapper) {
        this.nlpClient = nlpClient;
        this.processingService = processingService;
        this.nlpObjectMapper = nlpObjectMapper;
    }

    /**
     * Returns the cached extraction if present, otherwise extracts, caches it on
     * the CV (marking it READY), and returns it. Throws on NLP failure — the
     * caller decides whether that fails a whole CV or just one match candidate.
     */
    public ExtractResponse obtainExtraction(Cv cv) throws Exception {
        if (cv.getExtractedCandidates() != null && !cv.getExtractedCandidates().isBlank()) {
            log.debug("Reusing cached extraction for CV {}", cv.getId());
            return nlpObjectMapper.readValue(cv.getExtractedCandidates(), ExtractResponse.class);
        }
        ExtractResponse extracted =
                extractWithRetry(cv.getId().toString(), cv.getPdfData(), cv.getOriginalFilename());
        String json = nlpObjectMapper.writeValueAsString(extracted);
        processingService.markReadyWithExtraction(
                cv.getId(), extracted.detectedLanguage(), primaryEmail(extracted), json);
        return extracted;
    }

    /**
     * Backfill a single CV's {@code extractedEmail} (REWORK 4 D46). Idempotent and
     * NLP-frugal: if the cache is already on the new schema (carries a {@code contact}
     * block), the email is derived from it with no NLP call; only legacy caches —
     * serialized before this feature — trigger a fresh {@code /v1/extract}, which
     * also refreshes the cache so a later run takes the cheap path. Re-running never
     * duplicates work: once a CV has an extracted email it leaves the backfill set,
     * and email-less CVs are recognised by their already-present {@code contact} block.
     */
    public String backfillEmail(Cv cv) throws Exception {
        ExtractResponse cached = parseCache(cv);
        if (cached != null && cached.contact() != null) {
            String email = primaryEmail(cached);
            if (email != null) {
                processingService.setExtractedEmail(cv.getId(), email);
            }
            return email; // Cache already on the new schema — no NLP round-trip needed.
        }
        ExtractResponse fresh =
                extractWithRetry(cv.getId().toString(), cv.getPdfData(), cv.getOriginalFilename());
        String json = nlpObjectMapper.writeValueAsString(fresh);
        String email = primaryEmail(fresh);
        processingService.markReadyWithExtraction(
                cv.getId(), fresh.detectedLanguage(), email, json);
        return email;
    }

    private ExtractResponse parseCache(Cv cv) {
        if (cv.getExtractedCandidates() == null || cv.getExtractedCandidates().isBlank()) {
            return null;
        }
        try {
            return nlpObjectMapper.readValue(cv.getExtractedCandidates(), ExtractResponse.class);
        } catch (Exception ex) {
            log.warn("Could not parse cached extraction for CV {} during backfill", cv.getId());
            return null;
        }
    }

    private static String primaryEmail(ExtractResponse extracted) {
        return extracted.contact() != null ? extracted.contact().primaryEmail() : null;
    }

    private ExtractResponse extractWithRetry(String cvId, byte[] pdf, String filename) {
        int attempt = 0;
        while (true) {
            try {
                return nlpClient.extract(cvId, pdf, filename);
            } catch (NlpServiceException ex) {
                attempt++;
                if (!ex.isTransient() || attempt >= MAX_TRANSIENT_RETRIES) {
                    throw ex;
                }
                log.info(
                        "Transient extract failure ({}), retry {}/{}",
                        ex.getErrorCode(),
                        attempt,
                        MAX_TRANSIENT_RETRIES);
            }
        }
    }
}
