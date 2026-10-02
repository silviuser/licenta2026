package com.hrhelper.backend.nlp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hrhelper.backend.common.RequestIdFilter;
import com.hrhelper.backend.nlp.dto.ExtractJdRequest;
import com.hrhelper.backend.nlp.dto.ExtractJdResponse;
import com.hrhelper.backend.nlp.dto.ExtractResponse;
import com.hrhelper.backend.nlp.dto.InfoResponse;
import com.hrhelper.backend.nlp.dto.MatchRequest;
import com.hrhelper.backend.nlp.dto.MatchResponse;
import com.hrhelper.backend.nlp.dto.NlpErrorDto;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;

/**
 * Hand-written client for the NLP service (D8 / §10). Maps every non-2xx
 * response to a {@link NlpServiceException} carrying the stable NLP error code,
 * and propagates the {@code X-Request-ID} correlation header.
 */
@Component
public class NlpClient {

    private static final Logger log = LoggerFactory.getLogger(NlpClient.class);

    private final WebClient webClient;
    private final ObjectMapper objectMapper;
    private final long timeoutSeconds;

    public NlpClient(
            @Qualifier("nlpWebClient") WebClient webClient,
            @Qualifier("nlpObjectMapper") ObjectMapper objectMapper,
            NlpProperties properties) {
        this.webClient = webClient;
        this.objectMapper = objectMapper;
        this.timeoutSeconds = properties.timeoutSeconds();
    }

    /** POST /v1/extract — multipart PDF upload. */
    public ExtractResponse extract(String cvId, byte[] pdf, String filename) {
        MultipartBodyBuilder mp = new MultipartBodyBuilder();
        mp.part("cv_id", cvId);
        ByteArrayResource pdfResource =
                new ByteArrayResource(pdf) {
                    @Override
                    public String getFilename() {
                        return filename != null ? filename : "cv.pdf";
                    }
                };
        mp.part("cv_pdf", pdfResource).contentType(MediaType.APPLICATION_PDF);

        return webClient
                .post()
                .uri("/v1/extract")
                .header(RequestIdFilter.HEADER, RequestIdFilter.current())
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(mp.build()))
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::toException)
                .bodyToMono(ExtractResponse.class)
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorMap(this::mapConnectivity)
                .block();
    }

    /** POST /v1/extract-jd — free-text JD → candidate requirements (REWORK 1). */
    public ExtractJdResponse extractJd(String jdId, String text, String language) {
        ExtractJdRequest body = new ExtractJdRequest(jdId, text, language);
        return webClient
                .post()
                .uri("/v1/extract-jd")
                .header(RequestIdFilter.HEADER, RequestIdFilter.current())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::toException)
                .bodyToMono(ExtractJdResponse.class)
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorMap(this::mapConnectivity)
                .block();
    }

    /** POST /v1/match — JSON body. */
    public MatchResponse match(MatchRequest request) {
        return webClient
                .post()
                .uri("/v1/match")
                .header(RequestIdFilter.HEADER, RequestIdFilter.current())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::toException)
                .bodyToMono(MatchResponse.class)
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorMap(this::mapConnectivity)
                .block();
    }

    /** GET /v1/info — service identity proxied to the UI. */
    public InfoResponse info() {
        return webClient
                .get()
                .uri("/v1/info")
                .header(RequestIdFilter.HEADER, RequestIdFilter.current())
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::toException)
                .bodyToMono(InfoResponse.class)
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorMap(this::mapConnectivity)
                .block();
    }

    /** GET /v1/readyz — 200 when warm, 503 when cold. Never throws. */
    public boolean isReady() {
        try {
            return Boolean.TRUE.equals(
                    webClient
                            .get()
                            .uri("/v1/readyz")
                            .retrieve()
                            .toBodilessEntity()
                            .map(r -> r.getStatusCode().is2xxSuccessful())
                            .timeout(Duration.ofSeconds(timeoutSeconds))
                            .onErrorReturn(false)
                            .block());
        } catch (Exception ex) {
            log.debug("readyz probe failed: {}", ex.getMessage());
            return false;
        }
    }

    /** Deserializes the NLP {@code ErrorResponse} body and raises a domain exception. */
    private Mono<? extends Throwable> toException(org.springframework.web.reactive.function.client.ClientResponse response) {
        int status = response.statusCode().value();
        boolean transientError = status == 503;
        return response
                .bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(
                        body -> {
                            String code = "nlp_error";
                            String detail = "NLP service returned HTTP " + status;
                            try {
                                if (!body.isBlank()) {
                                    NlpErrorDto dto = objectMapper.readValue(body, NlpErrorDto.class);
                                    if (dto.error() != null) {
                                        code = dto.error();
                                    }
                                    if (dto.detail() != null) {
                                        detail = dto.detail();
                                    }
                                }
                            } catch (Exception parseError) {
                                log.debug("Could not parse NLP error body: {}", parseError.getMessage());
                            }
                            return new NlpServiceException(code, detail, status, transientError);
                        });
    }

    /** Maps connectivity / timeout failures to a transient domain exception. */
    private Throwable mapConnectivity(Throwable ex) {
        if (ex instanceof NlpServiceException) {
            return ex;
        }
        if (ex instanceof TimeoutException || ex instanceof WebClientRequestException) {
            return new NlpServiceException(
                    "nlp_unreachable", "NLP service is unreachable: " + ex.getMessage(), 503, true);
        }
        return ex;
    }
}
