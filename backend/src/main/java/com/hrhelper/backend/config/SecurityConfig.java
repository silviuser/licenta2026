package com.hrhelper.backend.config;

import com.hrhelper.backend.apply.PublicRateLimitFilter;
import com.hrhelper.backend.common.ErrorResponse;
import com.hrhelper.backend.common.RequestIdFilter;
import com.hrhelper.backend.security.JwtAuthenticationFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Arrays;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final PublicRateLimitFilter publicRateLimitFilter;
    private final CorsProperties corsProperties;
    private final ObjectMapper objectMapper;

    public SecurityConfig(
            JwtAuthenticationFilter jwtAuthenticationFilter,
            PublicRateLimitFilter publicRateLimitFilter,
            CorsProperties corsProperties,
            ObjectMapper objectMapper) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.publicRateLimitFilter = publicRateLimitFilter;
        this.corsProperties = corsProperties;
        this.objectMapper = objectMapper;
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.csrf(AbstractHttpConfigurer::disable)
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .sessionManagement(
                        sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(
                        auth ->
                                auth.requestMatchers(
                                                "/api/auth/register",
                                                "/api/auth/login",
                                                "/api/health",
                                                "/api/public/**",
                                                "/v3/api-docs/**",
                                                "/swagger-ui/**",
                                                "/swagger-ui.html")
                                        .permitAll()
                                        .requestMatchers("/api/admin/**")
                                        .hasRole("ADMIN")
                                        .anyRequest()
                                        .authenticated())
                .exceptionHandling(
                        eh ->
                                eh.authenticationEntryPoint(
                                                (req, res, ex) ->
                                                        writeError(
                                                                res,
                                                                HttpStatus.UNAUTHORIZED,
                                                                "unauthorized",
                                                                "authentication required"))
                                        .accessDeniedHandler(
                                                (req, res, ex) ->
                                                        writeError(
                                                                res,
                                                                HttpStatus.FORBIDDEN,
                                                                "forbidden",
                                                                "insufficient role")))
                .addFilterBefore(
                        jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
                // Throttle /api/public/** per IP before the request reaches the controller (D38).
                .addFilterBefore(publicRateLimitFilter, JwtAuthenticationFilter.class);
        return http.build();
    }

    private void writeError(
            HttpServletResponse response, HttpStatus status, String error, String detail)
            throws java.io.IOException {
        response.setStatus(status.value());
        response.setContentType("application/json");
        response.getWriter()
                .write(
                        objectMapper.writeValueAsString(
                                ErrorResponse.of(error, detail, RequestIdFilter.current())));
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(corsProperties.allowOrigins());
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setExposedHeaders(List.of("X-Request-ID"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration config)
            throws Exception {
        return config.getAuthenticationManager();
    }

    @ConfigurationProperties(prefix = "hrhelper.cors")
    public record CorsProperties(List<String> allowOrigins) {
        public CorsProperties {
            if (allowOrigins == null) {
                allowOrigins = List.of();
            }
        }
    }
}
