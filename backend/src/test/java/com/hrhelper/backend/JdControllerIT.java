package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.hrhelper.backend.support.AbstractIntegrationTest;
import com.hrhelper.backend.support.AuthTestHelper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

class JdControllerIT extends AbstractIntegrationTest {

    private String jdBody() throws Exception {
        return objectMapper.writeValueAsString(
                Map.of(
                        "title", "Senior Backend Engineer",
                        "descriptionText", "Build services.",
                        "requirements",
                                List.of(
                                        Map.of("text", "Java", "importance", "required", "confidence", 0.9),
                                        Map.of("text", "Kafka", "importance", "nice_to_have"))));
    }

    @Test
    void createReadAndContainsRequirements() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jd-owner@example.com", "password123");

        MvcResult created =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, token)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(jdBody()))
                        .andExpect(status().isCreated())
                        .andExpect(jsonPath("$.requirements.length()").value(2))
                        .andExpect(jsonPath("$.requirements[0].importance").value("required"))
                        .andReturn();

        JsonNode node = objectMapper.readTree(created.getResponse().getContentAsString());
        String jdId = node.get("id").asText();

        mockMvc.perform(get("/api/jds/" + jdId).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Senior Backend Engineer"));
    }

    @Test
    void emptyRequirementsWithNoTextCreatesEmptyReadyJd() throws Exception {
        // REWORK 1 D18: requirements are optional. With no description text either,
        // the JD is created empty and READY (the recruiter will add requirements).
        String token =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jd-empty@example.com", "password123");
        String body =
                objectMapper.writeValueAsString(
                        Map.of("title", "Role", "requirements", List.of()));

        mockMvc.perform(
                        post("/api/jds")
                                .header(HttpHeaders.AUTHORIZATION, token)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.requirements.length()").value(0))
                .andExpect(jsonPath("$.processingStatus").value("READY"));
    }

    @Test
    void crossUserAccessReturns404() throws Exception {
        String tokenA =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jd-a@example.com", "password123");
        String tokenB =
                AuthTestHelper.registerAndLogin(mockMvc, objectMapper, "jd-b@example.com", "password123");

        MvcResult created =
                mockMvc.perform(
                                post("/api/jds")
                                        .header(HttpHeaders.AUTHORIZATION, tokenA)
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(jdBody()))
                        .andExpect(status().isCreated())
                        .andReturn();
        String jdId =
                objectMapper.readTree(created.getResponse().getContentAsString()).get("id").asText();

        mockMvc.perform(get("/api/jds/" + jdId).header(HttpHeaders.AUTHORIZATION, tokenB))
                .andExpect(status().isNotFound());
        mockMvc.perform(delete("/api/jds/" + jdId).header(HttpHeaders.AUTHORIZATION, tokenB))
                .andExpect(status().isNotFound());
    }
}
