package com.hrhelper.backend;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.hrhelper.backend.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;

/**
 * Public POST rate limiting (REWORK 3 D38). Runs in its own context (a distinct
 * property set), so the in-memory counter map starts fresh and the low budget
 * here doesn't leak into {@link PublicApplyFlowIT}.
 */
@TestPropertySource(properties = {"app.rate-limit-post-per-hour=3"})
class PublicRateLimitIT extends AbstractIntegrationTest {

    @Test
    void postsBeyondTheHourlyBudgetAreRejectedWith429() throws Exception {
        String ip = "203.0.113.7";
        // The filter counts every request before the controller; the token need not
        // exist — the first 3 reach the controller (404), the 4th is throttled.
        for (int i = 0; i < 3; i++) {
            mockMvc.perform(
                            multipart("/api/public/apply/whatever-token")
                                    .file(new MockMultipartFile("file", "cv.pdf", "application/pdf", "%PDF-X".getBytes()))
                                    .param("name", "X")
                                    .param("email", "x@x.com")
                                    .param("phone", "0712345678")
                                    .header("X-Forwarded-For", ip))
                    .andExpect(status().isNotFound());
        }

        mockMvc.perform(
                        multipart("/api/public/apply/whatever-token")
                                .file(new MockMultipartFile("file", "cv.pdf", "application/pdf", "%PDF-X".getBytes()))
                                .param("name", "X")
                                .param("email", "x@x.com")
                                .param("phone", "0712345678")
                                .header("X-Forwarded-For", ip))
                .andExpect(status().isTooManyRequests());
    }
}
