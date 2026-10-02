package com.hrhelper.backend.apply;

import com.hrhelper.backend.apply.dto.ApplyLinkResponse;
import com.hrhelper.backend.apply.dto.SetApplyLinkRequest;
import com.hrhelper.backend.security.CurrentUser;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Recruiter-facing apply-link management (REWORK 3 D33). Owner-scoped (D6). */
@RestController
@RequestMapping("/api/jds/{jdId}/apply-link")
public class ApplyLinkController {

    private final ApplyLinkService applyLinkService;

    public ApplyLinkController(ApplyLinkService applyLinkService) {
        this.applyLinkService = applyLinkService;
    }

    /** Generate or regenerate the token (the old one stops working) and enable it. */
    @PostMapping
    public ApplyLinkResponse generate(@PathVariable UUID jdId) {
        return applyLinkService.generate(CurrentUser.id(), jdId);
    }

    @PutMapping
    public ApplyLinkResponse setEnabled(
            @PathVariable UUID jdId, @Valid @RequestBody SetApplyLinkRequest request) {
        return applyLinkService.setEnabled(CurrentUser.id(), jdId, request.enabled());
    }

    @GetMapping
    public ApplyLinkResponse state(@PathVariable UUID jdId) {
        return applyLinkService.getState(CurrentUser.id(), jdId);
    }
}
