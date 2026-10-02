package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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
import org.springframework.test.web.servlet.MvcResult;

/** JD created from free text → background /v1/extract-jd → editable requirements (D18). */
class JdExtractionFlowIT extends AbstractIntegrationTest {

    @BeforeEach
    void stubExtractJd() {
        nlpServer.setDispatcher(
                new Dispatcher() {
                    @Override
                    public MockResponse dispatch(RecordedRequest request) {
                        try {
                            if (request.getPath().startsWith("/v1/extract-jd")) {
                                return json(200, extractJdJson());
                            }
                        } catch (Exception e) {
                            return new MockResponse().setResponseCode(500);
                        }
                        return new MockResponse().setResponseCode(404);
                    }
                });
    }

    private String extractJdJson() throws Exception {
        return objectMapper.writeValueAsString(
                Map.of(
                        "jd_id", "x",
                        "detected_language", "en",
                        "requirements",
                                List.of(
                                        Map.of(
                                                "text", "Python",
                                                "skill_uri", "uri:python",
                                                "skill_label", "Python",
                                                "confidence", 0.91),
                                        Map.of(
                                                "text", "Docker",
                                                "skill_uri", "uri:docker",
                                                "skill_label", "Docker",
                                                "confidence", 0.77)),
                        "pipeline_version", "skill_matcher@test",
                        "warnings", List.of()));
    }

    @Test
    void jdFromTextExtractsRequirementsThenRecruiterEdits() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jd-text@example.com", "password123");

        String body =
                objectMapper.writeValueAsString(
                        Map.of(
                                "title", "Data Engineer",
                                "descriptionText",
                                        "We need a data engineer skilled in Python and Docker to build pipelines."));
        MvcResult created =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body))
                        .andExpect(status().isCreated())
                        .andExpect(jsonPath("$.processingStatus").value("PENDING"))
                        .andReturn();
        String jdId = objectMapper.readTree(created.getResponse().getContentAsString()).get("id").asText();

        // Background extraction populates requirements (source EXTRACTED) and flips READY.
        JsonNode ready =
                Awaitility.await()
                        .atMost(Duration.ofSeconds(20))
                        .pollInterval(Duration.ofMillis(200))
                        .until(
                                () ->
                                        objectMapper.readTree(
                                                mockMvc.perform(
                                                                get("/api/jds/" + jdId)
                                                                        .header(HttpHeaders.AUTHORIZATION, token))
                                                        .andReturn()
                                                        .getResponse()
                                                        .getContentAsString()),
                                node -> node.get("processingStatus").asText().equals("READY"));

        org.assertj.core.api.Assertions.assertThat(ready.get("requirements")).hasSize(2);
        org.assertj.core.api.Assertions.assertThat(ready.get("requirements").get(0).get("source").asText())
                .isEqualTo("EXTRACTED");
        org.assertj.core.api.Assertions.assertThat(ready.get("requirements").get(0).get("importance").asText())
                .isEqualTo("required");

        // Recruiter edits: keep Python (flip to nice_to_have), drop Docker, add a manual one.
        String edit =
                objectMapper.writeValueAsString(
                        Map.of(
                                "requirements",
                                List.of(
                                        Map.of(
                                                "text", "Python",
                                                "skillUri", "uri:python",
                                                "skillLabel", "Python",
                                                "importance", "nice_to_have",
                                                "source", "EXTRACTED"),
                                        Map.of("text", "Airflow", "importance", "required"))));
        mockMvc.perform(
                        put("/api/jds/" + jdId + "/requirements")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(edit))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requirements.length()").value(2))
                .andExpect(jsonPath("$.requirements[0].importance").value("nice_to_have"))
                .andExpect(jsonPath("$.requirements[0].source").value("EXTRACTED"))
                .andExpect(jsonPath("$.requirements[1].text").value("Airflow"))
                .andExpect(jsonPath("$.requirements[1].source").value("MANUAL"));
    }

    private static MockResponse json(int code, String body) {
        return new MockResponse()
                .setResponseCode(code)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
