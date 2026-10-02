package com.hrhelper.backend.cv.dto;

import java.util.List;

/** Response of {@code POST /api/cvs} — one {@link CvUploadItemResult} per file. */
public record CvBulkUploadResponse(List<CvUploadItemResult> results) {}
