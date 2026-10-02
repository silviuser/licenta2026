package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
import org.assertj.core.api.Assertions;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

/** Dashboard read model (REWORK 2 D30): KPIs + per-position aggregation. */
class DashboardControllerIT extends AbstractIntegrationTest {

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

    @Test
    void dashboardReportsKpisAndPerPositionAggregates() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "dashboard@example.com", "password123");
        String jd1 = createJd(token, "Backend role");
        String jd2 = createJd(token, "Data role");

        uploadToJd(token, jd1, "alice.pdf", "%PDF-ALICE".getBytes());
        uploadToJd(token, jd2, "bob.pdf", "%PDF-BOB".getBytes());

        // Match only jd1 so jd2 has no match yet.
        String jobId = startMatch(token, jd1, List.of());
        pollUntilTerminal(token, jobId);

        JsonNode dash = getDashboard(token);

        JsonNode kpis = dash.get("kpis");
        Assertions.assertThat(kpis.get("openPositions").asInt()).isEqualTo(2);
        Assertions.assertThat(kpis.get("uniqueCandidates").asInt()).isEqualTo(2);
        Assertions.assertThat(kpis.get("lastMatch").get("jdTitle").asText()).isEqualTo("Backend role");
        Assertions.assertThat(kpis.get("lastMatch").get("topScore").asDouble()).isEqualTo(0.42);

        JsonNode positions = dash.get("positions");
        Assertions.assertThat(positions).hasSize(2);

        JsonNode backend = positionByTitle(positions, "Backend role");
        Assertions.assertThat(backend.get("applicationCount").asInt()).isEqualTo(1);
        Assertions.assertThat(backend.get("lastMatch").get("status").asText()).isEqualTo("SUCCEEDED");
        Assertions.assertThat(backend.get("lastMatch").get("topScore").asDouble()).isEqualTo(0.42);

        JsonNode data = positionByTitle(positions, "Data role");
        Assertions.assertThat(data.get("applicationCount").asInt()).isEqualTo(1);
        Assertions.assertThat(data.get("lastMatch").isNull()).isTrue();
    }

    @Test
    void dashboardIsEmptyForNewRecruiter() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "dashboard-empty@example.com", "password123");

        JsonNode dash = getDashboard(token);
        Assertions.assertThat(dash.get("kpis").get("openPositions").asInt()).isEqualTo(0);
        Assertions.assertThat(dash.get("kpis").get("uniqueCandidates").asInt()).isEqualTo(0);
        Assertions.assertThat(dash.get("kpis").get("lastMatch").isNull()).isTrue();
        Assertions.assertThat(dash.get("positions")).isEmpty();
    }

    private JsonNode getDashboard(String token) throws Exception {
        MvcResult res =
                mockMvc.perform(get("/api/dashboard").header(HttpHeaders.AUTHORIZATION, token))
                        .andExpect(status().isOk())
                        .andReturn();
        return objectMapper.readTree(res.getResponse().getContentAsString());
    }

    private JsonNode positionByTitle(JsonNode positions, String title) {
        for (JsonNode p : positions) {
            if (p.get("title").asText().equals(title)) {
                return p;
            }
        }
        throw new AssertionError("position not found: " + title);
    }

    // --- shared helpers (mirrors JdMatchFlowIT) ---

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
        return objectMapper.writeValueAsString(
                Map.ofEntries(
                        Map.entry("cv_id", "x"),
                        Map.entry("jd_id", "y"),
                        Map.entry("overall_score", 0.42),
                        Map.entry("overall_class", "possible"),
                        Map.entry("required_coverage", 1.0),
                        Map.entry("nice_to_have_coverage", 0.0),
                        Map.entry("matched_required", List.of()),
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
                                        .content(objectMapper.writeValueAsString(Map.of("sourceJdIds", sourceJdIds))))
                        .andExpect(status().isAccepted())
                        .andReturn();
        return objectMapper.readTree(res.getResponse().getContentAsString()).get("jobId").asText();
    }

    private void pollUntilTerminal(String token, String jobId) {
        Awaitility.await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(200))
                .until(
                        () -> {
                            JsonNode node =
                                    objectMapper.readTree(
                                            mockMvc.perform(
                                                            get("/api/matches/" + jobId)
                                                                    .header(HttpHeaders.AUTHORIZATION, token))
                                                    .andReturn()
                                                    .getResponse()
                                                    .getContentAsString());
                            String s = node.get("status").asText();
                            return s.equals("SUCCEEDED") || s.equals("FAILED");
                        });
    }

    private static MockResponse json(int code, String body) {
        return new MockResponse()
                .setResponseCode(code)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
