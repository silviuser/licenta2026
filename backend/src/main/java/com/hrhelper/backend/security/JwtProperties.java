package com.hrhelper.backend.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "hrhelper.jwt")
public record JwtProperties(String secret, long expiryMinutes) {}
