package com.hrhelper.backend.support;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** Registers a user and returns a usable {@code Bearer} token for integration tests. */
public final class AuthTestHelper {

    private AuthTestHelper() {}

    public static String registerAndLogin(
            MockMvc mockMvc, ObjectMapper mapper, String email, String password) throws Exception {
        mockMvc.perform(
                post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                mapper.writeValueAsString(
                                        Map.of(
                                                "email", email,
                                                "password", password,
                                                "fullName", "Test User"))));

        String body =
                mockMvc.perform(
                                post("/api/auth/login")
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(
                                                mapper.writeValueAsString(
                                                        Map.of("email", email, "password", password))))
                        .andReturn()
                        .getResponse()
                        .getContentAsString();
        JsonNode node = mapper.readTree(body);
        return "Bearer " + node.get("accessToken").asText();
    }
}
