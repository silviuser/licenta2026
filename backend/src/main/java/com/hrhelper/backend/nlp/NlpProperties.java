package com.hrhelper.backend.nlp;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "hrhelper.nlp")
public record NlpProperties(String baseUrl, long timeoutSeconds) {}
