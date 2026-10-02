package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

/** Attach/list/detach library CVs on a JD (REWORK 1 F5–F7). */
class ApplicationControllerIT extends AbstractIntegrationTest {

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

    private String createJd(String token) throws Exception {
        String body =
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
                                        .content(body))
                        .andExpect(status().isCreated())
                        .andReturn();
        return objectMapper.readTree(jd.getResponse().getContentAsString()).get("id").asText();
    }

    private String uploadCv(String token, String filename, byte[] bytes) throws Exception {
        MvcResult res =
                mockMvc.perform(
                                multipart("/api/cvs")
                                        .file(new MockMultipartFile("files", filename, "application/pdf", bytes))
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

    @Test
    void attachListAndDetachLibraryCvs() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "app-owner@example.com", "password123");
        String jdId = createJd(token);
        String cvId = uploadCv(token, "alice.pdf", "%PDF-ALICE".getBytes());

        // Attach.
        MvcResult attached =
                mockMvc.perform(
                                post("/api/jds/" + jdId + "/applications")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(objectMapper.writeValueAsString(Map.of("cvIds", List.of(cvId)))))
                        .andExpect(status().isCreated())
                        .andExpect(jsonPath("$.created.length()").value(1))
                        .andReturn();
        String applicationId =
                objectMapper
                        .readTree(attached.getResponse().getContentAsString())
                        .get("created")
                        .get(0)
                        .get("applicationId")
                        .asText();

        // Idempotent re-attach.
        mockMvc.perform(
                        post("/api/jds/" + jdId + "/applications")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(Map.of("cvIds", List.of(cvId)))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.created.length()").value(0))
                .andExpect(jsonPath("$.alreadyExisted.length()").value(1));

        // List.
        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].cvId").value(cvId))
                .andExpect(jsonPath("$[0].filename").value("alice.pdf"));

        // Detach (link only — the CV stays in the library).
        mockMvc.perform(
                        delete("/api/jds/" + jdId + "/applications/" + applicationId)
                                .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
        // CV still in the library.
        mockMvc.perform(get("/api/cvs/" + cvId).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk());
    }

    @Test
    void cannotAttachToAnotherUsersJd() throws Exception {
        String tokenA =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "app-a@example.com", "password123");
        String tokenB =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "app-b@example.com", "password123");
        String jdId = createJd(tokenA);
        String cvId = uploadCv(tokenB, "b.pdf", "%PDF-B".getBytes());

        mockMvc.perform(
                        post("/api/jds/" + jdId + "/applications")
                                .header(HttpHeaders.AUTHORIZATION, tokenB)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(Map.of("cvIds", List.of(cvId)))))
                .andExpect(status().isNotFound());
    }
}
