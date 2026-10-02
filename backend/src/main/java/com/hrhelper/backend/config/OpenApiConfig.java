package com.hrhelper.backend.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    private static final String BEARER = "bearerAuth";

    @Bean
    public OpenAPI hrHelperOpenApi() {
        return new OpenAPI()
                .info(
                        new Info()
                                .title("HR Helper Backend API")
                                .version("0.1.0")
                                .description(
                                        "Application backend orchestrating the NLP service: "
                                                + "auth, CVs, job descriptions and asynchronous matching."))
                .addSecurityItem(new SecurityRequirement().addList(BEARER))
                .components(
                        new Components()
                                .addSecuritySchemes(
                                        BEARER,
                                        new SecurityScheme()
                                                .type(SecurityScheme.Type.HTTP)
                                                .scheme("bearer")
                                                .bearerFormat("JWT")));
    }
}
