package com.hrhelper.backend;

import static org.springframework.http.HttpHeaders.AUTHORIZATION;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
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
import org.assertj.core.api.Assertions;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;

/** Public candidate apply flow (REWORK 3 D32–D39). */
class PublicApplyFlowIT extends AbstractIntegrationTest {

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

    // ---- happy path -------------------------------------------------------

    @Test
    void candidateAppliesThroughLinkAndShowsUpForRecruiter() throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-ok@example.com", "password123");
        String jdId = createJd(token, "Backend Engineer", "Build backend services.");
        String applyToken = generateLink(token, jdId);

        // Public job view exposes only title + description (D35).
        mockMvc.perform(get("/api/public/apply/" + applyToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.jobTitle").value("Backend Engineer"))
                .andExpect(jsonPath("$.jobDescription").value("Build backend services."));

        // Candidate applies.
        applyPost(applyToken, "1.1.1.1", "Alice Candidate", "alice@candidate.com", "+40 712 345 678",
                        "application/pdf", "%PDF-ALICE".getBytes())
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("RECEIVED"));

        // Recruiter sees the application with origin + contact details (D37).
        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].origin").value("CANDIDATE_LINK"))
                .andExpect(jsonPath("$[0].candidateName").value("Alice Candidate"))
                .andExpect(jsonPath("$[0].candidateEmail").value("alice@candidate.com"))
                .andExpect(jsonPath("$[0].candidatePhone").value("+40 712 345 678"));

        // The candidate is scored like any other applicant (D39), provenance carried into the report.
        String jobId = startMatch(token, jdId);
        JsonNode report = pollUntilTerminal(token, jobId).get("result");
        JsonNode candidate = report.get("candidates").get(0);
        Assertions.assertThat(candidate.get("origin").asText()).isEqualTo("CANDIDATE_LINK");
        Assertions.assertThat(candidate.get("candidate_name").asText()).isEqualTo("Alice Candidate");
    }

    // ---- disabled / regenerated tokens -----------------------------------

    @Test
    void disabledLinkReturnsGeneric404() throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-off@example.com", "password123");
        String jdId = createJd(token, "Role", "desc");
        String applyToken = generateLink(token, jdId);

        // Disable the link.
        mockMvc.perform(
                        put("/api/jds/" + jdId + "/apply-link")
                                .header(AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(Map.of("enabled", false))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false));

        mockMvc.perform(get("/api/public/apply/" + applyToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("not_found"));

        applyPost(applyToken, "2.2.2.2", "Bob", "bob@x.com", "0712345678", "application/pdf",
                        "%PDF-BOB".getBytes())
                .andExpect(status().isNotFound());
    }

    @Test
    void regeneratingInvalidatesTheOldToken() throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-regen@example.com", "password123");
        String jdId = createJd(token, "Role", "desc");
        String oldToken = generateLink(token, jdId);
        String newToken = generateLink(token, jdId); // regenerate

        Assertions.assertThat(newToken).isNotEqualTo(oldToken);
        mockMvc.perform(get("/api/public/apply/" + oldToken)).andExpect(status().isNotFound());
        mockMvc.perform(get("/api/public/apply/" + newToken)).andExpect(status().isOk());
    }

    @Test
    void unknownTokenReturnsGeneric404() throws Exception {
        mockMvc.perform(get("/api/public/apply/totally-made-up-token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("not_found"));
    }

    // ---- re-application: replace CV, dedup by email+JD (D36) --------------

    @Test
    void reapplyReplacesCvAndRemovesOrphan() throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-reapply@example.com", "password123");
        String jdId = createJd(token, "Role", "desc");
        String applyToken = generateLink(token, jdId);

        applyPost(applyToken, "3.3.3.3", "Carol", "carol@x.com", "0712345678", "application/pdf",
                        "%PDF-CAROL-V1".getBytes())
                .andExpect(status().isCreated());
        String firstCvId = onlyApplicationCvId(token, jdId);
        awaitCvStatus(token, firstCvId, "READY");

        // Same email, different file → CV replaced, application updated (D36).
        applyPost(applyToken, "3.3.3.3", "Carol Updated", "carol@x.com", "0700000000", "application/pdf",
                        "%PDF-CAROL-V2".getBytes())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UPDATED"));

        // Still one application, now pointing at a new CV with refreshed contact.
        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(AUTHORIZATION, token))
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].candidateName").value("Carol Updated"))
                .andExpect(jsonPath("$[0].candidatePhone").value("0700000000"));
        String secondCvId = onlyApplicationCvId(token, jdId);
        Assertions.assertThat(secondCvId).isNotEqualTo(firstCvId);

        // The superseded CV is gone (Q3 orphan cleanup); the new one is in the library.
        mockMvc.perform(get("/api/cvs/" + firstCvId).header(AUTHORIZATION, token))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/cvs/" + secondCvId).header(AUTHORIZATION, token))
                .andExpect(status().isOk());
    }

    @Test
    void reapplyWithIdenticalFileReusesCv() throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-same@example.com", "password123");
        String jdId = createJd(token, "Role", "desc");
        String applyToken = generateLink(token, jdId);

        byte[] same = "%PDF-DAVE".getBytes();
        applyPost(applyToken, "4.4.4.4", "Dave", "dave@x.com", "0712345678", "application/pdf", same)
                .andExpect(status().isCreated());
        String firstCvId = onlyApplicationCvId(token, jdId);

        applyPost(applyToken, "4.4.4.4", "Dave Again", "dave@x.com", "0712345678", "application/pdf", same)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UPDATED"));

        String secondCvId = onlyApplicationCvId(token, jdId);
        Assertions.assertThat(secondCvId).isEqualTo(firstCvId); // identical bytes → same CV reused
    }

    // ---- validation (D34/D38) --------------------------------------------

    @Test
    void rejectsNonPdfContentType() throws Exception {
        String applyToken = activeToken("pa-val1@example.com");
        applyPost(applyToken, "5.5.5.1", "X", "x@x.com", "0712345678", "text/plain",
                        "%PDF-but-text".getBytes())
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_file"));
    }

    @Test
    void rejectsPdfContentTypeWithoutMagicBytes() throws Exception {
        String applyToken = activeToken("pa-val2@example.com");
        applyPost(applyToken, "5.5.5.2", "X", "x@x.com", "0712345678", "application/pdf",
                        "this is not really a pdf".getBytes())
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_file"));
    }

    @Test
    void rejectsInvalidEmail() throws Exception {
        String applyToken = activeToken("pa-val3@example.com");
        applyPost(applyToken, "5.5.5.3", "X", "not-an-email", "0712345678", "application/pdf",
                        "%PDF-X".getBytes())
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_email"));
    }

    @Test
    void rejectsMissingName() throws Exception {
        String applyToken = activeToken("pa-val4@example.com");
        // No name param at all.
        mockMvc.perform(
                        multipart("/api/public/apply/" + applyToken)
                                .file(new MockMultipartFile("file", "cv.pdf", "application/pdf", "%PDF-X".getBytes()))
                                .param("email", "x@x.com")
                                .param("phone", "0712345678")
                                .header("X-Forwarded-For", "5.5.5.4"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_name"));
    }

    // ---- isolation (D6) ---------------------------------------------------

    @Test
    void anotherRecruiterCannotSeeTheApplication() throws Exception {
        String owner = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-owner@example.com", "password123");
        String other = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "pa-other@example.com", "password123");
        String jdId = createJd(owner, "Role", "desc");
        String applyToken = generateLink(owner, jdId);

        applyPost(applyToken, "6.6.6.6", "Eve", "eve@x.com", "0712345678", "application/pdf",
                        "%PDF-EVE".getBytes())
                .andExpect(status().isCreated());

        // The other recruiter cannot read this JD's applications (owner-scoped → 404).
        mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(AUTHORIZATION, other))
                .andExpect(status().isNotFound());
    }

    // ---- helpers ----------------------------------------------------------

    private String createJd(String token, String title, String description) throws Exception {
        String body =
                objectMapper.writeValueAsString(
                        Map.of(
                                "title", title,
                                "descriptionText", description,
                                "requirements",
                                        List.of(Map.of("text", "Java", "importance", "required", "confidence", 0.9))));
        MvcResult jd =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body))
                        .andExpect(status().isCreated())
                        .andReturn();
        return objectMapper.readTree(jd.getResponse().getContentAsString()).get("id").asText();
    }

    private String generateLink(String token, String jdId) throws Exception {
        MvcResult res =
                mockMvc.perform(post("/api/jds/" + jdId + "/apply-link").header(AUTHORIZATION, token))
                        .andExpect(status().isOk())
                        .andExpect(jsonPath("$.enabled").value(true))
                        .andReturn();
        String url = objectMapper.readTree(res.getResponse().getContentAsString()).get("url").asText();
        return url.substring(url.lastIndexOf("/apply/") + "/apply/".length());
    }

    /** Register a fresh recruiter, create a JD and return its active apply token. */
    private String activeToken(String email) throws Exception {
        String token = AuthTestHelper.registerAndLogin(mockMvc, objectMapper, email, "password123");
        String jdId = createJd(token, "Role", "desc");
        return generateLink(token, jdId);
    }

    private org.springframework.test.web.servlet.ResultActions applyPost(
            String applyToken,
            String ip,
            String name,
            String email,
            String phone,
            String fileContentType,
            byte[] bytes)
            throws Exception {
        return mockMvc.perform(
                multipart("/api/public/apply/" + applyToken)
                        .file(new MockMultipartFile("file", "cv.pdf", fileContentType, bytes))
                        .param("name", name)
                        .param("email", email)
                        .param("phone", phone)
                        .header("X-Forwarded-For", ip));
    }

    private String onlyApplicationCvId(String token, String jdId) throws Exception {
        MvcResult res =
                mockMvc.perform(get("/api/jds/" + jdId + "/applications").header(AUTHORIZATION, token))
                        .andExpect(status().isOk())
                        .andReturn();
        return objectMapper.readTree(res.getResponse().getContentAsString()).get(0).get("cvId").asText();
    }

    private void awaitCvStatus(String token, String cvId, String expected) {
        Awaitility.await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(200))
                .until(
                        () ->
                                objectMapper
                                        .readTree(
                                                mockMvc.perform(
                                                                get("/api/cvs/" + cvId)
                                                                        .header(AUTHORIZATION, token))
                                                        .andReturn()
                                                        .getResponse()
                                                        .getContentAsString())
                                        .get("processingStatus")
                                        .asText()
                                        .equals(expected));
    }

    private String startMatch(String token, String jdId) throws Exception {
        MvcResult res =
                mockMvc.perform(
                                post("/api/jds/" + jdId + "/match")
                                        .header(AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(objectMapper.writeValueAsString(Map.of("sourceJdIds", List.of()))))
                        .andExpect(status().isAccepted())
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
                                                                .header(AUTHORIZATION, token))
                                                .andReturn()
                                                .getResponse()
                                                .getContentAsString()),
                        node -> {
                            String s = node.get("status").asText();
                            return s.equals("SUCCEEDED") || s.equals("FAILED");
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

    private static MockResponse json(int code, String body) {
        return new MockResponse()
                .setResponseCode(code)
                .setHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
