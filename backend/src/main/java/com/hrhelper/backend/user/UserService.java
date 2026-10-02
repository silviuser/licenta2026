package com.hrhelper.backend.user;

import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.security.JwtTokenProvider;
import com.hrhelper.backend.user.dto.LoginRequest;
import com.hrhelper.backend.user.dto.LoginResponse;
import com.hrhelper.backend.user.dto.RegisterRequest;
import java.util.UUID;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider tokenProvider;

    public UserService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JwtTokenProvider tokenProvider) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.tokenProvider = tokenProvider;
    }

    @Transactional
    public User register(RegisterRequest request) {
        String email = request.email().trim().toLowerCase();
        if (userRepository.existsByEmail(email)) {
            throw new BadRequestException("email_taken", "an account with this email already exists");
        }
        User user =
                new User(
                        UUID.randomUUID(),
                        email,
                        passwordEncoder.encode(request.password()),
                        request.fullName().trim(),
                        Role.RECRUITER);
        return userRepository.save(user);
    }

    @Transactional(readOnly = true)
    public LoginResponse login(LoginRequest request) {
        String email = request.email().trim().toLowerCase();
        User user =
                userRepository
                        .findByEmail(email)
                        .orElseThrow(() -> new BadCredentialsException("invalid credentials"));
        if (!user.isEnabled()
                || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
            throw new BadCredentialsException("invalid credentials");
        }
        String token = tokenProvider.generateToken(user);
        return new LoginResponse(token, tokenProvider.getExpirySeconds(), user.getRole().name());
    }

    @Transactional(readOnly = true)
    public User getById(UUID id) {
        return userRepository.findById(id).orElseThrow(() -> new NotFoundException("user not found"));
    }
}
