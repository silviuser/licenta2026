package com.hrhelper.backend.user.dto;

import com.hrhelper.backend.user.User;
import java.util.UUID;

public record UserResponse(UUID id, String email, String fullName, String role, boolean enabled) {

    public static UserResponse from(User user) {
        return new UserResponse(
                user.getId(),
                user.getEmail(),
                user.getFullName(),
                user.getRole().name(),
                user.isEnabled());
    }
}
