package com.hrhelper.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.hrhelper.backend.nlp.NlpProperties;
import io.netty.channel.ChannelOption;
import io.netty.handler.timeout.ReadTimeoutHandler;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

/** Builds the {@link WebClient} used to talk to the NLP service (D8 / §10). */
@Configuration
public class WebClientConfig {

    /** Jackson mapper that maps the NLP service's snake_case fields to Java camelCase. */
    @Bean(name = "nlpObjectMapper")
    public ObjectMapper nlpObjectMapper() {
        return new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .findAndRegisterModules();
    }

    @Bean(name = "nlpWebClient")
    public WebClient nlpWebClient(
            NlpProperties properties,
            @Qualifier("nlpObjectMapper") ObjectMapper nlpObjectMapper) {
        long timeoutSec = properties.timeoutSeconds();
        HttpClient httpClient =
                HttpClient.create()
                        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 10_000)
                        .responseTimeout(Duration.ofSeconds(timeoutSec))
                        .doOnConnected(
                                conn ->
                                        conn.addHandlerLast(
                                                new ReadTimeoutHandler(timeoutSec, TimeUnit.SECONDS)));

        // Raise the in-memory buffer limit: ExtractResponse for a large CV can be sizeable.
        int maxBytes = 16 * 1024 * 1024;
        return WebClient.builder()
                .baseUrl(properties.baseUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(
                        c -> {
                            c.defaultCodecs().maxInMemorySize(maxBytes);
                            c.defaultCodecs()
                                    .jackson2JsonEncoder(
                                            new Jackson2JsonEncoder(
                                                    nlpObjectMapper, MediaType.APPLICATION_JSON));
                            c.defaultCodecs()
                                    .jackson2JsonDecoder(
                                            new Jackson2JsonDecoder(
                                                    nlpObjectMapper, MediaType.APPLICATION_JSON));
                        })
                .build();
    }
}
