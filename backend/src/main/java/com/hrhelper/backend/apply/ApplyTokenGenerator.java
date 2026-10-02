package com.hrhelper.backend.apply;

import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.stereotype.Component;

/**
 * Generates apply-link tokens (REWORK 3 D32). 32 cryptographically-random bytes
 * encoded URL-safe (no padding) → 43 chars, ~256 bits of entropy — well above the
 * 128-bit floor. The token is the candidate's only credential (a capability URL),
 * so it must be unguessable and is never derived from the JD id.
 */
@Component
public class ApplyTokenGenerator {

    private static final int TOKEN_BYTES = 32;

    private final SecureRandom random = new SecureRandom();
    private final Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();

    public String generate() {
        byte[] bytes = new byte[TOKEN_BYTES];
        random.nextBytes(bytes);
        return encoder.encodeToString(bytes);
    }
}
