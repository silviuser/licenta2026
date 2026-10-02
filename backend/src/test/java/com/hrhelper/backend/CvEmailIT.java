package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.hrhelper.backend.support.AbstractIntegrationTest;
import com.hrhelper.backend.support.AuthTestHelper;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.RecordedRequest;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

/** Email extraction, resolution, manual override and JD-list exposure (REWORK 4). */
class CvEmailIT extends AbstractIntegrationTest {

    private static final byte[] PDF = "%PDF-1.4 cv with email".getBytes();

    /** /v1/extract returns a contact block carrying a primary email. */
    @BeforeEach
    void stubExtractionWithEmail() {
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
                                                            "warnings", List.of(),
                                                            "contact",
                                                                    Map.of(
                                                                            "emails",
                                                                            List.of("ana.pop@example.com"),
                                                                            "primary_email",
                                                                            "ana.pop@example.com"))));
                        } catch (Exception e) {
                            return new MockResponse().setResponseCode(500);
                        }
                    }
                });
    }

    private String upload(String token) throws Exception {
        MvcResult res =
                mockMvc.perform(
                                multipart("/api/cvs")
                                        .file(new MockMultipartFile("files", "cv.pdf", "application/pdf", PDF))
                                        .header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isAccepted())
                        .andReturn();
        return objectMapper
                .readTree(res.getResponse().getContentAsString())
                .get("results")
                .get(0)
                .get("cvId")
                .asText();
    }

    private JsonNode getCv(String token, String cvId) throws Exception {
        return objectMapper.readTree(
                mockMvc.perform(get("/api/cvs/" + cvId).header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsString());
    }

    private void awaitExtractedEmail(String token, String cvId) {
        Awaitility.await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(200))
                .until(() -> !getCv(token, cvId).get("extractedEmail").isNull());
    }

    @Test
    void extractionPopulatesEmailAndResolvesAsExtracted() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-x@example.com", "password123");
        String cvId = upload(token);
        awaitExtractedEmail(token, cvId);

        JsonNode cv = getCv(token, cvId);
        org.assertj.core.api.Assertions.assertThat(cv.get("extractedEmail").asText())
                .isEqualTo("ana.pop@example.com");
        org.assertj.core.api.Assertions.assertThat(cv.get("effectiveEmail").asText())
                .isEqualTo("ana.pop@example.com");
        org.assertj.core.api.Assertions.assertThat(cv.get("emailSource").asText()).isEqualTo("EXTRACTED");
    }

    @Test
    void manualOverrideTakesPrecedenceAndClearingReverts() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-m@example.com", "password123");
        String cvId = upload(token);
        awaitExtractedEmail(token, cvId);

        // Set a manual override.
        mockMvc.perform(
                        patch("/api/cvs/" + cvId + "/email")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(
                                        Map.of("manualEmail", "Recruiter.Choice@Example.com"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.manualEmail").value("recruiter.choice@example.com"))
                .andExpect(jsonPath("$.effectiveEmail").value("recruiter.choice@example.com"))
                .andExpect(jsonPath("$.emailSource").value("MANUAL"));

        // Clearing reverts to the extracted address.
        mockMvc.perform(
                        patch("/api/cvs/" + cvId + "/email")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(Map.of("manualEmail", ""))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.manualEmail").doesNotExist())
                .andExpect(jsonPath("$.effectiveEmail").value("ana.pop@example.com"))
                .andExpect(jsonPath("$.emailSource").value("EXTRACTED"));
    }

    @Test
    void invalidManualEmailIsRejectedServerSide() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-bad@example.com", "password123");
        String cvId = upload(token);

        mockMvc.perform(
                        patch("/api/cvs/" + cvId + "/email")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(
                                        Map.of("manualEmail", "not-an-email"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_email"));
    }

    @Test
    void cannotPatchAnotherUsersCv() throws Exception {
        String tokenA =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-a@example.com", "password123");
        String tokenB =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-b@example.com", "password123");
        String cvId = upload(tokenA);

        mockMvc.perform(
                        patch("/api/cvs/" + cvId + "/email")
                                .header(HttpHeaders.AUTHORIZATION, tokenB)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(
                                        Map.of("manualEmail", "x@example.com"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void applicationListExposesResolvedEmail() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "email-app@example.com", "password123");
        String cvId = upload(token);
        awaitExtractedEmail(token, cvId);

        // Create a JD and attach the CV (recruiter origin → resolves to EXTRACTED).
        String jdBody =
                objectMapper.writeValueAsString(
                        Map.of(
                                "title", "Role",
                                "requirements",
                                        List.of(Map.of("text", "Java", "importance", "required", "confidence", 0.9))));
        MvcResult jd =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(jdBody))
                        .andExpect(status().isCreated())
                        .andReturn();
        String jdId = objectMapper.readTree(jd.getResponse().getContentAsString()).get("id").asText();

        mockMvc.perform(
                        post("/api/jds/" + jdId + "/applications")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(Map.of("cvIds", List.of(cvId)))))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].effectiveEmail").value("ana.pop@example.com"))
                .andExpect(jsonPath("$[0].emailSource").value("EXTRACTED"));
    }
}
