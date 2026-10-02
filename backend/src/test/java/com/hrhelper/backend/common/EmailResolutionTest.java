package com.hrhelper.backend.common;

import static org.assertj.core.api.Assertions.assertThat;

import com.hrhelper.backend.common.EmailResolution.Resolved;
import org.junit.jupiter.api.Test;

/** Unit tests for the effective-email resolution rule (REWORK 4 D42). */
class EmailResolutionTest {

    @Test
    void candidateFormWinsOverEverything() {
        Resolved r = EmailResolution.resolve("form@x.com", "manual@x.com", "extracted@x.com");
        assertThat(r.email()).isEqualTo("form@x.com");
        assertThat(r.source()).isEqualTo(EmailSource.CANDIDATE_FORM);
    }

    @Test
    void manualWinsWhenNoForm() {
        Resolved r = EmailResolution.resolve(null, "manual@x.com", "extracted@x.com");
        assertThat(r.email()).isEqualTo("manual@x.com");
        assertThat(r.source()).isEqualTo(EmailSource.MANUAL);
    }

    @Test
    void extractedUsedWhenNoFormOrManual() {
        Resolved r = EmailResolution.resolve(null, null, "extracted@x.com");
        assertThat(r.email()).isEqualTo("extracted@x.com");
        assertThat(r.source()).isEqualTo(EmailSource.EXTRACTED);
    }

    @Test
    void noneWhenAllAbsentOrBlank() {
        Resolved r = EmailResolution.resolve(null, "   ", "");
        assertThat(r.email()).isNull();
        assertThat(r.source()).isEqualTo(EmailSource.NONE);
    }

    @Test
    void resolvedEmailIsNormalisedToLowercaseTrimmed() {
        Resolved r = EmailResolution.resolve(null, "  Manual@Example.COM ", null);
        assertThat(r.email()).isEqualTo("manual@example.com");
        assertThat(r.source()).isEqualTo(EmailSource.MANUAL);
    }

    @Test
    void normalizeBlankBecomesNull() {
        assertThat(EmailResolution.normalize("  ")).isNull();
        assertThat(EmailResolution.normalize(null)).isNull();
        assertThat(EmailResolution.normalize(" Ana@X.com ")).isEqualTo("ana@x.com");
    }

    @Test
    void validSyntaxAcceptsStandardAddresses() {
        assertThat(EmailResolution.isValidSyntax("ana.pop+jobs@example.co.uk")).isTrue();
        assertThat(EmailResolution.isValidSyntax(" ANA@EXAMPLE.COM ")).isTrue();
    }

    @Test
    void validSyntaxRejectsMalformed() {
        assertThat(EmailResolution.isValidSyntax(null)).isFalse();
        assertThat(EmailResolution.isValidSyntax("notanemail")).isFalse();
        assertThat(EmailResolution.isValidSyntax("a@b")).isFalse();
        assertThat(EmailResolution.isValidSyntax("a@b.")).isFalse();
        assertThat(EmailResolution.isValidSyntax("@example.com")).isFalse();
    }
}
