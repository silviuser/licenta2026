package com.hrhelper.backend.apply;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hrhelper.backend.common.ErrorResponse;
import com.hrhelper.backend.common.RequestIdFilter;
import com.hrhelper.backend.config.AppProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * In-memory per-IP rate limiting on {@code /api/public/**} (REWORK 3 D38). No new
 * infrastructure: a fixed-window counter per (IP, method) that auto-resets when the
 * window rolls over, so the map stays bounded by the number of distinct clients.
 * GET (reads) and POST (applications) have separate budgets; preflight/others pass.
 */
@Component
public class PublicRateLimitFilter extends OncePerRequestFilter {

    private static final String PUBLIC_PREFIX = "/api/public/";
    private static final long MINUTE_MS = 60_000L;
    private static final long HOUR_MS = 3_600_000L;

    private final AppProperties appProperties;
    private final ObjectMapper objectMapper;
    private final ConcurrentHashMap<String, Window> windows = new ConcurrentHashMap<>();

    public PublicRateLimitFilter(AppProperties appProperties, ObjectMapper objectMapper) {
        this.appProperties = appProperties;
        this.objectMapper = objectMapper;
    }

    private record Window(long start, AtomicInteger count) {}

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(PUBLIC_PREFIX);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long windowMs;
        int limit;
        String method = request.getMethod();
        if ("GET".equalsIgnoreCase(method)) {
            windowMs = MINUTE_MS;
            limit = appProperties.rateLimitGetPerMinute();
        } else if ("POST".equalsIgnoreCase(method)) {
            windowMs = HOUR_MS;
            limit = appProperties.rateLimitPostPerHour();
        } else {
            chain.doFilter(request, response);
            return;
        }

        if (exceeded(clientIp(request), method, windowMs, limit)) {
            writeTooManyRequests(response);
            return;
        }
        chain.doFilter(request, response);
    }

    private boolean exceeded(String ip, String method, long windowMs, int limit) {
        long windowStart = (System.currentTimeMillis() / windowMs) * windowMs;
        String key = ip + "|" + method;
        Window window =
                windows.compute(
                        key,
                        (k, existing) ->
                                (existing == null || existing.start() != windowStart)
                                        ? new Window(windowStart, new AtomicInteger(0))
                                        : existing);
        return window.count().incrementAndGet() > limit;
    }

    /** First hop of X-Forwarded-For when present (dev/proxy), else the socket address. */
    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (StringUtils.hasText(forwarded)) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private void writeTooManyRequests(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter()
                .write(
                        objectMapper.writeValueAsString(
                                ErrorResponse.of(
                                        "rate_limited",
                                        "too many requests, please try again later",
                                        RequestIdFilter.current())));
    }
}
