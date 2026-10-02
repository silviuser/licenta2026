package com.hrhelper.backend.nlp;

import com.hrhelper.backend.nlp.dto.InfoResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Proxies {@code GET /v1/info} of the NLP service for display in the UI (§7). */
@RestController
@RequestMapping("/api/nlp")
public class NlpController {

    private final NlpClient nlpClient;

    public NlpController(NlpClient nlpClient) {
        this.nlpClient = nlpClient;
    }

    @GetMapping("/info")
    public InfoResponse info() {
        return nlpClient.info();
    }
}
