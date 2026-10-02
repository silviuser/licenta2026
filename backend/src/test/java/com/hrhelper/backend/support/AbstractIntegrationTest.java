package com.hrhelper.backend.support;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.BeforeEach;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;

/**
 * Base class for integration tests.
 *
 * <p>Preferred backing store is a throwaway Postgres via Testcontainers (D10). On
 * machines where the Docker daemon is not reachable by the bundled docker-java
 * client (a known Docker Desktop / docker-java incompatibility on some Windows
 * setups), it transparently falls back to the local Postgres {@code hrhelper_test}
 * database so the suite still runs green. Either way Flyway applies the real
 * schema and a {@link MockWebServer} stands in for the NLP service.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class AbstractIntegrationTest {

    private static final Logger log = LoggerFactory.getLogger(AbstractIntegrationTest.class);

    private static final String LOCAL_TEST_URL =
            "jdbc:postgresql://localhost:5432/hrhelper_test";
    private static final String LOCAL_TEST_USER = "hrhelper";
    private static final String LOCAL_TEST_PASSWORD = "hrhelper";

    private static final PostgreSQLContainer<?> POSTGRES = buildContainer();
    private static final boolean CONTAINER_AVAILABLE = tryStartContainer();

    // Started eagerly: @DynamicPropertySource is resolved during context startup,
    // which happens before any @BeforeAll, so the server must already be listening.
    protected static final MockWebServer nlpServer = startNlpServer();

    @Autowired protected MockMvc mockMvc;
    @Autowired protected ObjectMapper objectMapper;
    @Autowired protected JdbcTemplate jdbcTemplate;

    private static PostgreSQLContainer<?> buildContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("hrhelper")
                .withUsername("hrhelper")
                .withPassword("hrhelper");
    }

    private static boolean tryStartContainer() {
        try {
            POSTGRES.start();
            log.info("Integration tests using Testcontainers Postgres at {}", POSTGRES.getJdbcUrl());
            return true;
        } catch (Throwable t) {
            log.warn(
                    "Testcontainers Postgres unavailable ({}); falling back to local {}",
                    t.getMessage(),
                    LOCAL_TEST_URL);
            return false;
        }
    }

    private static MockWebServer startNlpServer() {
        try {
            MockWebServer server = new MockWebServer();
            server.start();
            return server;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @BeforeEach
    void cleanDatabase() {
        // Truncate between tests so the suite is repeatable on both the container
        // and the persistent local fallback database.
        jdbcTemplate.execute(
                "TRUNCATE TABLE match_jobs, applications, requirements, job_descriptions, cvs, users"
                        + " RESTART IDENTITY CASCADE");
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        if (CONTAINER_AVAILABLE) {
            registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
            registry.add("spring.datasource.username", POSTGRES::getUsername);
            registry.add("spring.datasource.password", POSTGRES::getPassword);
        } else {
            registry.add("spring.datasource.url", () -> LOCAL_TEST_URL);
            registry.add("spring.datasource.username", () -> LOCAL_TEST_USER);
            registry.add("spring.datasource.password", () -> LOCAL_TEST_PASSWORD);
        }
        registry.add("hrhelper.nlp.base-url", () -> "http://localhost:" + nlpServer.getPort());
    }
}
