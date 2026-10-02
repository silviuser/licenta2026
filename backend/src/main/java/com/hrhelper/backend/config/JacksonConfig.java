package com.hrhelper.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder;

/**
 * Defining the qualified {@code nlpObjectMapper} (snake_case) bean causes Spring
 * Boot to back off its auto-configured {@link ObjectMapper}. This restores the
 * standard camelCase mapper as {@link Primary} so the public API and MVC use it,
 * while the snake_case mapper stays reserved for the NLP client only.
 */
@Configuration
public class JacksonConfig {

    @Bean
    @Primary
    public ObjectMapper objectMapper(Jackson2ObjectMapperBuilder builder) {
        return builder.build();
    }
}
