package com.hrhelper.backend.cv;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.hrhelper.backend.nlp.NlpClient;
import com.hrhelper.backend.nlp.dto.ContactDto;
import com.hrhelper.backend.nlp.dto.ExtractResponse;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** Backfill idempotency + NLP-frugality (REWORK 4 D46). */
class CvExtractionServiceBackfillTest {

    private final ObjectMapper nlpMapper =
            new ObjectMapper()
                    .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                    .findAndRegisterModules();

    private Cv cvWithCache(String cacheJson) {
        Cv cv =
                new Cv(
                        UUID.randomUUID(),
                        UUID.randomUUID(),
                        "cv.pdf",
                        "application/pdf",
                        8,
                        "%PDF-1.4".getBytes(),
                        "hash");
        cv.setExtractedCandidates(cacheJson);
        cv.markReady();
        return cv;
    }

    private String cacheJson(ContactDto contact) throws Exception {
        return nlpMapper.writeValueAsString(
                new ExtractResponse("x", "en", List.of(), "v", List.of(), contact));
    }

    @Test
    void freshCacheWithEmail_setsEmail_noNlpCall() throws Exception {
        NlpClient nlp = mock(NlpClient.class);
        CvProcessingService proc = mock(CvProcessingService.class);
        CvExtractionService svc = new CvExtractionService(nlp, proc, nlpMapper);

        Cv cv = cvWithCache(cacheJson(new ContactDto(List.of("ana@x.com"), "ana@x.com")));

        String email = svc.backfillEmail(cv);

        assertThatEmail(email, "ana@x.com");
        verify(proc).setExtractedEmail(eq(cv.getId()), eq("ana@x.com"));
        verify(nlp, never()).extract(anyString(), any(), anyString());
    }

    @Test
    void freshCacheWithoutEmail_noWrite_noNlpCall() throws Exception {
        NlpClient nlp = mock(NlpClient.class);
        CvProcessingService proc = mock(CvProcessingService.class);
        CvExtractionService svc = new CvExtractionService(nlp, proc, nlpMapper);

        Cv cv = cvWithCache(cacheJson(new ContactDto(List.of(), null)));

        String email = svc.backfillEmail(cv);

        org.assertj.core.api.Assertions.assertThat(email).isNull();
        verify(proc, never()).setExtractedEmail(any(), anyString());
        verify(nlp, never()).extract(anyString(), any(), anyString());
    }

    @Test
    void legacyCacheWithoutContact_reExtracts_andPersists() throws Exception {
        NlpClient nlp = mock(NlpClient.class);
        CvProcessingService proc = mock(CvProcessingService.class);
        CvExtractionService svc = new CvExtractionService(nlp, proc, nlpMapper);

        // Old-schema cache: contact == null.
        Cv cv = cvWithCache(cacheJson(null));
        when(nlp.extract(anyString(), any(), anyString()))
                .thenReturn(
                        new ExtractResponse(
                                "x",
                                "en",
                                List.of(),
                                "v",
                                List.of(),
                                new ContactDto(List.of("ion@x.com"), "ion@x.com")));

        String email = svc.backfillEmail(cv);

        assertThatEmail(email, "ion@x.com");
        verify(nlp, times(1)).extract(anyString(), any(), anyString());
        // Cache refreshed + email persisted via the ready-with-extraction path.
        verify(proc).markReadyWithExtraction(eq(cv.getId()), eq("en"), eq("ion@x.com"), anyString());
    }

    @Test
    void rerunOnFreshCacheIsIdempotent_neverCallsNlp() throws Exception {
        NlpClient nlp = mock(NlpClient.class);
        CvProcessingService proc = mock(CvProcessingService.class);
        CvExtractionService svc = new CvExtractionService(nlp, proc, nlpMapper);

        Cv cv = cvWithCache(cacheJson(new ContactDto(List.of("ana@x.com"), "ana@x.com")));

        svc.backfillEmail(cv);
        svc.backfillEmail(cv);

        verify(proc, times(2)).setExtractedEmail(eq(cv.getId()), eq("ana@x.com"));
        verify(nlp, never()).extract(anyString(), any(), anyString());
    }

    private static void assertThatEmail(String actual, String expected) {
        org.assertj.core.api.Assertions.assertThat(actual).isEqualTo(expected);
    }
}
