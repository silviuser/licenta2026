package com.hrhelper.backend.config;

import com.hrhelper.backend.config.SecurityConfig.CorsProperties;
import com.hrhelper.backend.nlp.NlpProperties;
import com.hrhelper.backend.security.JwtProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/** Registers all {@code @ConfigurationProperties} record beans. */
@Configuration
@EnableConfigurationProperties({
    JwtProperties.class,
    NlpProperties.class,
    CorsProperties.class,
    AppProperties.class
})
public class PropertiesConfig {}
