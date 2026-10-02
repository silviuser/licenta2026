package com.hrhelper.backend.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hrhelper.backend.user.Role;
import com.hrhelper.backend.user.User;
import io.jsonwebtoken.JwtException;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class JwtTokenProviderTest {

    private final JwtTokenProvider provider =
            new JwtTokenProvider(
                    new JwtProperties(
                            "test-only-secret-key-that-is-sufficiently-long-for-hs256-signing-0123456789",
                            120));

    private User sampleUser() {
        return new User(
                UUID.randomUUID(), "alice@example.com", "hash", "Alice", Role.RECRUITER);
    }

    @Test
    void generatesAndParsesRoundTrip() {
        User user = sampleUser();
        String token = provider.generateToken(user);

        JwtTokenProvider.ParsedToken parsed = provider.parse(token);

        assertThat(parsed.userId()).isEqualTo(user.getId());
        assertThat(parsed.email()).isEqualTo("alice@example.com");
        assertThat(parsed.role()).isEqualTo(Role.RECRUITER);
    }

    @Test
    void rejectsTokenSignedWithDifferentSecret() {
        String token =
                new JwtTokenProvider(
                                new JwtProperties(
                                        "a-completely-different-secret-key-also-long-enough-for-hs256-000000",
                                        120))
                        .generateToken(sampleUser());

        assertThatThrownBy(() -> provider.parse(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsGarbageToken() {
        assertThatThrownBy(() -> provider.parse("not.a.jwt")).isInstanceOf(Exception.class);
    }

    @Test
    void expirySecondsDerivedFromMinutes() {
        assertThat(provider.getExpirySeconds()).isEqualTo(120 * 60);
    }
}
