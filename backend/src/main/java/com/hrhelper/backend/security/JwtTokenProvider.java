package com.hrhelper.backend.security;

import com.hrhelper.backend.user.Role;
import com.hrhelper.backend.user.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/** Issues and validates HS256 JWTs carrying the user id, email and role. */
@Component
public class JwtTokenProvider {

    private final SecretKey key;
    private final long expiryMinutes;

    public JwtTokenProvider(JwtProperties properties) {
        this.key = Keys.hmacShaKeyFor(properties.secret().getBytes(StandardCharsets.UTF_8));
        this.expiryMinutes = properties.expiryMinutes();
    }

    public String generateToken(User user) {
        Instant now = Instant.now();
        Instant expiry = now.plus(Duration.ofMinutes(expiryMinutes));
        return Jwts.builder()
                .subject(user.getId().toString())
                .claim("email", user.getEmail())
                .claim("role", user.getRole().name())
                .issuedAt(Date.from(now))
                .expiration(Date.from(expiry))
                .signWith(key)
                .compact();
    }

    public long getExpirySeconds() {
        return expiryMinutes * 60;
    }

    /** Parses and validates a token, returning its claims, or throws {@link JwtException}. */
    public ParsedToken parse(String token) {
        Claims claims =
                Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        UUID userId = UUID.fromString(claims.getSubject());
        String email = claims.get("email", String.class);
        Role role = Role.valueOf(claims.get("role", String.class));
        return new ParsedToken(userId, email, role);
    }

    public record ParsedToken(UUID userId, String email, Role role) {}
}
