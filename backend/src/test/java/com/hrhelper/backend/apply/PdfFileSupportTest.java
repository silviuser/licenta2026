package com.hrhelper.backend.apply;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class PdfFileSupportTest {

    @Test
    void recognisesPdfMagicHeader() {
        assertThat(PdfFileSupport.hasPdfMagic("%PDF-1.7\n...".getBytes(StandardCharsets.US_ASCII)))
                .isTrue();
    }

    @Test
    void rejectsNonPdfBytes() {
        assertThat(PdfFileSupport.hasPdfMagic("PK zip".getBytes(StandardCharsets.US_ASCII)))
                .isFalse();
        assertThat(PdfFileSupport.hasPdfMagic("hi".getBytes(StandardCharsets.US_ASCII))).isFalse();
        assertThat(PdfFileSupport.hasPdfMagic(new byte[0])).isFalse();
        assertThat(PdfFileSupport.hasPdfMagic(null)).isFalse();
    }

    @Test
    void sha256IsStableAndContentSensitive() {
        byte[] a = "%PDF-alpha".getBytes(StandardCharsets.US_ASCII);
        byte[] b = "%PDF-beta".getBytes(StandardCharsets.US_ASCII);
        assertThat(PdfFileSupport.sha256Hex(a)).isEqualTo(PdfFileSupport.sha256Hex(a));
        assertThat(PdfFileSupport.sha256Hex(a)).isNotEqualTo(PdfFileSupport.sha256Hex(b));
        assertThat(PdfFileSupport.sha256Hex(a)).hasSize(64);
    }
}
