package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.hrhelper.backend.support.AbstractIntegrationTest;
import com.hrhelper.backend.support.AuthTestHelper;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

class AuthFlowIT extends AbstractIntegrationTest {

    @Test
    void registerLoginAndMe() throws Exception {
        String token =
                AuthTestHelper.registerAndLogin(
                        mockMvc, objectMapper, "auth-user@example.com", "password123");

        mockMvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("auth-user@example.com"))
                .andExpect(jsonPath("$.role").value("RECRUITER"));
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    }

    @Test
    void duplicateRegistrationRejected() throws Exception {
        Map<String, String> body =
                Map.of("email", "dup@example.com", "password", "password123", "fullName", "Dup");
        mockMvc.perform(
                        post("/api/auth/register")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated());
        mockMvc.perform(
                        post("/api/auth/register")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("email_taken"));
    }

    @Test
    void loginWithWrongPasswordIs401() throws Exception {
        Map<String, String> reg =
                Map.of("email", "wrongpw@example.com", "password", "password123", "fullName", "X");
        mockMvc.perform(
                post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(reg)));

        mockMvc.perform(
                        post("/api/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(
                                        objectMapper.writeValueAsString(
                                                Map.of(
                                                        "email", "wrongpw@example.com",
                                                        "password", "incorrect"))))
                .andExpect(status().isUnauthorized());
    }
}
