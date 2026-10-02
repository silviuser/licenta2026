package com.hrhelper.backend.apply;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ApplyTokenGeneratorTest {

    private final ApplyTokenGenerator generator = new ApplyTokenGenerator();

    @Test
    void tokenIsUrlSafeAndHighEntropy() {
        String token = generator.generate();
        // 32 random bytes → 43 base64url chars (no padding), ≥128 bits of entropy.
        assertThat(token).hasSize(43);
        assertThat(token).matches("[A-Za-z0-9_-]+");
        assertThat(token).doesNotContain("=");
    }

    @Test
    void tokensAreUnique() {
        Set<String> tokens = new HashSet<>();
        for (int i = 0; i < 1000; i++) {
            tokens.add(generator.generate());
        }
        assertThat(tokens).hasSize(1000);
    }
}
