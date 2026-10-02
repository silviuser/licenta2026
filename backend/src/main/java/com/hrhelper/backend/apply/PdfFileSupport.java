package com.hrhelper.backend.apply;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * Shared PDF helpers (REWORK 3 D38). Strict validation for the public apply
 * endpoint: content-type alone is forgeable, so the bytes must also start with the
 * {@code %PDF-} magic header.
 */
public final class PdfFileSupport {

    /** {@code %PDF-} — the PDF file signature. */
    private static final byte[] PDF_MAGIC = {0x25, 0x50, 0x44, 0x46, 0x2D};

    private PdfFileSupport() {}

    public static String sha256Hex(byte[] bytes) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    public static boolean hasPdfMagic(byte[] bytes) {
        if (bytes == null || bytes.length < PDF_MAGIC.length) {
            return false;
        }
        for (int i = 0; i < PDF_MAGIC.length; i++) {
            if (bytes[i] != PDF_MAGIC[i]) {
                return false;
            }
        }
        return true;
    }
}
