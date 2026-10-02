package com.hrhelper.backend.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

/** Enables {@code @CreatedDate} / {@code @LastModifiedDate} population on entities. */
@Configuration
@EnableJpaAuditing
public class JpaConfig {}
