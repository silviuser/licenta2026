package com.hrhelper.backend.common;

import java.util.List;
import org.springframework.data.domain.Page;

/** Lightweight pagination envelope so JPA {@code Page} internals never leak into the API. */
public record PageResponse<T>(
        List<T> content, int page, int size, long totalElements, int totalPages) {

    public static <T> PageResponse<T> from(Page<T> page) {
        return new PageResponse<>(
                page.getContent(),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages());
    }
}
