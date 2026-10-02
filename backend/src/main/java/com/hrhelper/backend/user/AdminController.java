package com.hrhelper.backend.user;

import com.hrhelper.backend.common.PageResponse;
import com.hrhelper.backend.user.dto.UserResponse;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final UserRepository userRepository;

    public AdminController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    /** ADMIN-only (enforced by {@code /api/admin/**} rule in SecurityConfig). */
    @GetMapping("/users")
    public PageResponse<UserResponse> listUsers(Pageable pageable) {
        return PageResponse.from(userRepository.findAll(pageable).map(UserResponse::from));
    }
}
