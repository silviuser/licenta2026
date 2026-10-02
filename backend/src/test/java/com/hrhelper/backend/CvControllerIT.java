package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.hrhelper.backend.support.AbstractIntegrationTest;
import com.hrhelper.backend.support.AuthTestHelper;
import java.util.List;
import java.util.Map;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

class CvControllerIT extends AbstractIntegrationTest {

    private static final byte[] PDF_BYTES = "%PDF-1.4 fake pdf body".getBytes();

    /**
     * Background extraction fires after upload. Stub /v1/extract so the
     * extract-executor thread completes quickly instead of blocking on the
     * MockWebServer queue.
     */
    @BeforeEach
    void stubExtraction() {
        nlpServer.setDispatcher(
                new Dispatcher() {
                    @Override
                    public MockResponse dispatch(RecordedRequest request) {
                        try {
                            return new MockResponse()
                                    .setResponseCode(200)
                                    .setHeader("Content-Type", "application/json")
                                    .setBody(
                                            objectMapper.writeValueAsString(
                                                    Map.of(
                                                            "cv_id", "x",
                                                            "detected_language", "en",
                                                            "candidates", List.of(),
                                                            "pipeline_version", "skill_matcher@test",
                                                            "warnings", List.of())));
                        } catch (Exception e) {
                            return new MockResponse().setResponseCode(500);
                        }
                    }
                });
    }

    private MockMultipartFile pdf(String name) {
        return new MockMultipartFile("files", name, "application/pdf", PDF_BYTES);
    }

    @Test
    void bulkUploadStoresAndDownloadReturnsIdenticalBytes() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "cv-owner@example.com", "password123");

        MvcResult uploaded =
                mockMvc.perform(
                                multipart("/api/cvs").file(pdf("cv.pdf")).header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isAccepted())
                        .andExpect(jsonPath("$.results[0].status").value("CREATED"))
                        .andReturn();

        JsonNode node = objectMapper.readTree(uploaded.getResponse().getContentAsString());
        String cvId = node.get("results").get(0).get("cvId").asText();

        byte[] downloaded =
                mockMvc.perform(
                                get("/api/cvs/" + cvId + "/file").header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsByteArray();

        org.assertj.core.api.Assertions.assertThat(downloaded).isEqualTo(PDF_BYTES);
    }

    @Test
    void nonPdfFileIsRejectedPerFileNotWholeRequest() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "cv-nonpdf@example.com", "password123");
        MockMultipartFile txt =
                new MockMultipartFile("files", "notes.txt", "text/plain", "hello".getBytes());

        mockMvc.perform(multipart("/api/cvs").file(txt).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.results[0].status").value("REJECTED"))
                .andExpect(jsonPath("$.results[0].reason").value("invalid_content_type"));
    }

    @Test
    void duplicateContentIsReusedNotRecreated() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "cv-dup@example.com", "password123");

        // Five files in one request; two share identical bytes (a duplicate).
        MvcResult res =
                mockMvc.perform(
                                multipart("/api/cvs")
                                        .file(new MockMultipartFile("files", "a.pdf", "application/pdf", "%PDF-A".getBytes()))
                                        .file(new MockMultipartFile("files", "b.pdf", "application/pdf", "%PDF-B".getBytes()))
                                        .file(new MockMultipartFile("files", "c.pdf", "application/pdf", "%PDF-C".getBytes()))
                                        .file(new MockMultipartFile("files", "d.pdf", "application/pdf", "%PDF-D".getBytes()))
                                        .file(new MockMultipartFile("files", "a-again.pdf", "application/pdf", "%PDF-A".getBytes()))
                                        .header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isAccepted())
                        .andReturn();

        JsonNode results = objectMapper.readTree(res.getResponse().getContentAsString()).get("results");
        long created = 0;
        long duplicate = 0;
        for (JsonNode r : results) {
            if (r.get("status").asText().equals("CREATED")) created++;
            if (r.get("status").asText().equals("DUPLICATE")) duplicate++;
        }
        org.assertj.core.api.Assertions.assertThat(created).isEqualTo(4);
        org.assertj.core.api.Assertions.assertThat(duplicate).isEqualTo(1);

        // Library holds 4 distinct CVs, not 5.
        mockMvc.perform(get("/api/cvs?size=50").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void userCannotAccessAnotherUsersCv() throws Exception {
        String tokenA =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "owner-a@example.com", "password123");
        String tokenB =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "owner-b@example.com", "password123");

        MvcResult uploaded =
                mockMvc.perform(
                                multipart("/api/cvs").file(pdf("cv.pdf")).header(HttpHeaders.AUTHORIZATION, tokenA))
                        .andExpect(status().isAccepted())
                        .andReturn();
        String cvId =
                objectMapper
                        .readTree(uploaded.getResponse().getContentAsString())
                        .get("results")
                        .get(0)
                        .get("cvId")
                        .asText();

        mockMvc.perform(get("/api/cvs/" + cvId).header(HttpHeaders.AUTHORIZATION, tokenB))
                .andExpect(status().isNotFound());
    }

    @Test
    void uploadRequiresAuthentication() throws Exception {
        mockMvc.perform(multipart("/api/cvs").file(pdf("cv.pdf")))
                .andExpect(status().isUnauthorized());
    }
}
