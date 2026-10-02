package com.hrhelper.backend.user.dto;

public record LoginResponse(String accessToken, long expiresIn, String role) {}
