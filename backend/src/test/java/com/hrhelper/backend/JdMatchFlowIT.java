package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
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

/** Per-JD match flow (REWORK 1 D24/D25): upload → apply → match → ranked report. */
class JdMatchFlowIT extends AbstractIntegrationTest {

    @BeforeEach
    void stubNlp() {
        nlpServer.setDispatcher(
                new Dispatcher() {
                    @Override
                    public MockResponse dispatch(RecordedRequest request) {
                        try {
                            String path = request.getPath();
                            if (path.startsWith("/v1/extract")) {
                                return json(200, extractJson());
                            }
                            if (path.startsWith("/v1/match")) {
                                return json(200, matchJson());
                            }
                        } catch (Exception e) {
                            return new MockResponse().setResponseCode(500);
                        }
                        return new MockResponse().setResponseCode(404);
                    }
                });
    }

    private String extractJson() throws Exception {
        return objectMapper.writeValueAsString(
                Map.of(
                        "cv_id", "x",
                        "detected_language", "en",
                        "candidates", List.of(),
                        "pipeline_version", "skill_matcher@test",
                        "warnings", List.of()));
    }

    private String matchJson() throws Exception {
        Map<String, Object> matchedJava =
                Map.of(
                        "requirement",
                                Map.of(
                                        "text", "Java",
                                        "skill_uri", "uri:java",
                                        "skill_label", "Java",
                                        "importance", "required",
                                        "confidence", 0.9),
                        "cv_candidate",
                                Map.of(
                                        "esco_uri", "uri:java",
                                        "skill_label", "Java",
                                        "surface_form", "Java 17",
                                        "section", "experience",
                                        "source", "lexical_kept",
                                        "confidence", 0.8,
                                        "semantic_similarity", 0.7),
                        "match_score", 0.91);
        return objectMapper.writeValueAsString(
                Map.ofEntries(
                        Map.entry("cv_id", "x"),
                        Map.entry("jd_id", "y"),
                        Map.entry("overall_score", 0.42),
                        Map.entry("overall_class", "possible"),
                        Map.entry("required_coverage", 1.0),
                        Map.entry("nice_to_have_coverage", 0.0),
                        Map.entry("matched_required", List.of(matchedJava)),
                        Map.entry("matched_nice_to_have", List.of()),
                        Map.entry("unmatched_required", List.of()),
                        Map.entry("unmatched_nice_to_have", List.of()),
                        Map.entry("timestamp", "2026-06-06T12:00:00Z"),
                        Map.entry("pipeline_version", "skill_matcher@test")));
    }

    private String createJd(String token, String title) throws Exception {
        String body =
                objectMapper.writeValueAsString(
                        Map.of(
                                "title", title,
                                "requirements",
                                        List.of(Map.of("text", "Java", "importance", "required", "confidence", 0.9))));
        MvcResult jd =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body))
                        .andExpect(status().isCreated())
                        .andReturn();
        return objectMapper.readTree(jd.getResponse().getContentAsString()).get("id").asText();
    }

    private void uploadToJd(String token, String jdId, String filename, byte[] bytes) throws Exception {
        mockMvc.perform(
                        multipart("/api/cvs")
                                .file(new MockMultipartFile("files", filename, "application/pdf", bytes))
                                .param("jdId", jdId)
                                .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isAccepted());
    }

    private String startMatch(String token, String jdId, List<String> sourceJdIds) throws Exception {
        MvcResult res =
                mockMvc.perform(
                                post("/api/jds/" + jdId + "/match")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(
                                                objectMapper.writeValueAsString(
                                                        Map.of("sourceJdIds", sourceJdIds))))
                        .andExpect(status().isAccepted())
                        .andExpect(jsonPath("$.status").value("PENDING"))
                        .andReturn();
        return objectMapper.readTree(res.getResponse().getContentAsString()).get("jobId").asText();
    }

    private JsonNode pollUntilTerminal(String token, String jobId) {
        return Awaitility.await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(200))
                .until(
                        () ->
                                objectMapper.readTree(
                                        mockMvc.perform(
                                                        get("/api/matches/" + jobId)
                                                                .header(HttpHeaders.AUTHORIZATION, token))
                                                .andReturn()
                                                .getResponse()
                                                .getContentAsString()),
                        node -> {
                            String s = node.get("status").asText();
                            return s.equals("SUCCEEDED") || s.equals("FAILED");
                        });
    }

    @Test
    void perJdMatchProducesRankedReport() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jdmatch-ok@example.com", "password123");
        String jdId = createJd(token, "Backend role");
        uploadToJd(token, jdId, "alice.pdf", "%PDF-ALICE".getBytes());

        String jobId = startMatch(token, jdId, List.of());
        JsonNode result = pollUntilTerminal(token, jobId);

        org.assertj.core.api.Assertions.assertThat(result.get("status").asText()).isEqualTo("SUCCEEDED");
        JsonNode report = result.get("result");
        org.assertj.core.api.Assertions.assertThat(report.get("candidates")).hasSize(1);
        JsonNode candidate = report.get("candidates").get(0);
        org.assertj.core.api.Assertions.assertThat(candidate.get("rank").asInt()).isEqualTo(1);
        org.assertj.core.api.Assertions.assertThat(candidate.get("source").asText()).isEqualTo("DIRECT");
        org.assertj.core.api.Assertions.assertThat(candidate.get("status").asText()).isEqualTo("SUCCEEDED");
        org.assertj.core.api.Assertions.assertThat(candidate.get("overall_score").asDouble())
                .isEqualTo(0.42);
        org.assertj.core.api.Assertions.assertThat(candidate.get("matched_skills")).hasSize(1);
        org.assertj.core.api.Assertions.assertThat(candidate.get("explanation").asText())
                .contains("Covers 1/1 required");
    }

    @Test
    void matchReportCarriesResolvedEffectiveEmail() throws Exception {
        // Override the stub so /v1/extract returns a contact with a primary email.
        nlpServer.setDispatcher(
                new Dispatcher() {
                    @Override
                    public MockResponse dispatch(RecordedRequest request) {
                        try {
                            String path = request.getPath();
                            if (path.startsWith("/v1/extract")) {
                                return json(200, extractJsonWithEmail());
                            }
                            if (path.startsWith("/v1/match")) {
                                return json(200, matchJson());
                            }
                        } catch (Exception e) {
                            return new MockResponse().setResponseCode(500);
                        }
                        return new MockResponse().setResponseCode(404);
                    }
                });

        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jdmatch-email@example.com", "password123");
        String jdId = createJd(token, "Backend role");
        uploadToJd(token, jdId, "alice.pdf", "%PDF-ALICE".getBytes());

        String jobId = startMatch(token, jdId, List.of());
        JsonNode result = pollUntilTerminal(token, jobId);

        JsonNode candidate = result.get("result").get("candidates").get(0);
        org.assertj.core.api.Assertions.assertThat(candidate.get("effective_email").asText())
                .isEqualTo("ana.pop@example.com");
        org.assertj.core.api.Assertions.assertThat(candidate.get("email_source").asText())
                .isEqualTo("EXTRACTED");
    }

    private String extractJsonWithEmail() throws Exception {
        return objectMapper.writeValueAsString(
                Map.of(
                        "cv_id", "x",
                        "detected_language", "en",
                        "candidates", List.of(),
                        "pipeline_version", "skill_matcher@test",
                        "warnings", List.of(),
                        "contact",
                                Map.of(
                                        "emails", List.of("ana.pop@example.com"),
                                        "primary_email", "ana.pop@example.com")));
    }

    @Test
    void matchOnJdWithoutRequirementsIsRejected() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jdmatch-noreq@example.com", "password123");
        // A JD created with an empty requirement list and no description stays READY
        // with zero requirements.
        MvcResult jd =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(objectMapper.writeValueAsString(
                                                Map.of("title", "Empty role", "requirements", List.of()))))
                        .andExpect(status().isCreated())
                        .andReturn();
        String jdId = objectMapper.readTree(jd.getResponse().getContentAsString()).get("id").asText();
        uploadToJd(token, jdId, "alice.pdf", "%PDF-ALICE".getBytes());

        mockMvc.perform(
                        post("/api/jds/" + jdId + "/match")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(
                                        Map.of("sourceJdIds", List.of()))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("no_requirements"));
    }

    @Test
    void matchFromSelectedSourceDedupesAndMarksProvenance() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jdmatch-pool@example.com", "password123");
        String jd1 = createJd(token, "Role 1");
        String jd2 = createJd(token, "Role 2");

        byte[] alice = "%PDF-ALICE".getBytes();
        byte[] bob = "%PDF-BOB".getBytes();

        uploadToJd(token, jd1, "alice.pdf", alice); // applied to jd1
        uploadToJd(token, jd2, "bob.pdf", bob); // applied to jd2
        uploadToJd(token, jd2, "alice-again.pdf", alice); // duplicate of alice, applied to jd2

        String jobId = startMatch(token, jd1, List.of(jd2)); // pull from jd2
        JsonNode result = pollUntilTerminal(token, jobId);

        org.assertj.core.api.Assertions.assertThat(result.get("status").asText()).isEqualTo("SUCCEEDED");
        JsonNode candidates = result.get("result").get("candidates");
        // alice (DIRECT) + bob (OTHER_JD); the duplicate alice from jd2 is dropped.
        org.assertj.core.api.Assertions.assertThat(candidates).hasSize(2);

        JsonNode pooled = null;
        long direct = 0;
        for (JsonNode c : candidates) {
            if (c.get("source").asText().equals("DIRECT")) direct++;
            if (c.get("source").asText().equals("OTHER_JD")) pooled = c;
        }
        org.assertj.core.api.Assertions.assertThat(direct).isEqualTo(1);
        org.assertj.core.api.Assertions.assertThat(pooled).isNotNull();
        // Provenance (D29): the pooled candidate records its source position title.
        org.assertj.core.api.Assertions.assertThat(pooled.get("source_jd_id").asText()).isEqualTo(jd2);
        org.assertj.core.api.Assertions.assertThat(pooled.get("source_jd_title").asText())
                .isEqualTo("Role 2");
        // Report records the selected sources.
        org.assertj.core.api.Assertions.assertThat(result.get("result").get("source_jd_ids").get(0).asText())
                .isEqualTo(jd2);
    }

    @Test
    void matchPullsOnlyFromSelectedSources() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "jdmatch-subset@example.com", "password123");
        String jd1 = createJd(token, "Role 1");
        String jd2 = createJd(token, "Role 2");
        String jd3 = createJd(token, "Role 3");

        uploadToJd(token, jd1, "alice.pdf", "%PDF-ALICE".getBytes()); // direct
        uploadToJd(token, jd2, "bob.pdf", "%PDF-BOB".getBytes()); // selected source
        uploadToJd(token, jd3, "carol.pdf", "%PDF-CAROL".getBytes()); // NOT selected

        String jobId = startMatch(token, jd1, List.of(jd2)); // only jd2 as source
        JsonNode result = pollUntilTerminal(token, jobId);

        JsonNode candidates = result.get("result").get("candidates");
        org.assertj.core.api.Assertions.assertThat(candidates).hasSize(2); // alice + bob, NOT carol
        for (JsonNode c : candidates) {
            org.assertj.core.api.Assertions.assertThat(c.get("filename").asText())
                    .isNotEqualTo("carol.pdf");
        }
    }

    @Test
    void matchRejectsSourceIncludingTarget() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "jdmatch-self@example.com", "password123");
        String jd1 = createJd(token, "Role 1");
        uploadToJd(token, jd1, "alice.pdf", "%PDF-ALICE".getBytes());

        mockMvc.perform(
                        post("/api/jds/" + jd1 + "/match")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        objectMapper.writeValueAsString(
                                                Map.of("sourceJdIds", List.of(jd1)))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("source_includes_target"));
    }

    @Test
    void matchRejectsUnknownSource() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "jdmatch-unknown@example.com", "password123");
        String jd1 = createJd(token, "Role 1");
        uploadToJd(token, jd1, "alice.pdf", "%PDF-ALICE".getBytes());

        mockMvc.perform(
                        post("/api/jds/" + jd1 + "/match")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        objectMapper.writeValueAsString(
                                                Map.of(
                                                        "sourceJdIds",
                                                        List.of(java.util.UUID.randomUUID().toString())))))
                .andExpect(status().isNotFound());
    }

    private static MockResponse json(int code, String body) {
        return new MockResponse()
                .setResponseCode(code)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
