package com.hrhelper.backend.config;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/** Dedicated executors for asynchronous processing (D9 / §8, REWORK 1 §3.2). */
@Configuration
public class AsyncConfig {

    @Bean(name = "matchExecutor")
    public Executor matchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("match-");
        executor.initialize();
        return executor;
    }

    /** Background CV/JD extraction at upload/creation (REWORK 1 D17/D18). */
    @Bean(name = "extractExecutor")
    public Executor extractExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        // Queue must be able to hold a whole bulk upload (hrhelper.cv.max-bulk-files,
        // default 100). With the old capacity of 50 a 99-file upload overflowed the
        // pool (max 4 threads + 50 queued = 54) and the ~55th dispatch hit the default
        // AbortPolicy -> TaskRejectedException, surfaced to the user as a 500 while the
        // CV rows had already been committed. Sized with headroom so a bulk upload that
        // overlaps the startup email-backfill cannot be rejected either.
        executor.setQueueCapacity(250);
        executor.setThreadNamePrefix("extract-");
        executor.initialize();
        return executor;
    }
}
