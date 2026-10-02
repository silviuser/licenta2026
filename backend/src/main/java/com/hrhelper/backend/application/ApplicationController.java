package com.hrhelper.backend.application;

import com.hrhelper.backend.application.dto.ApplicationResponse;
import com.hrhelper.backend.application.dto.AttachApplicationsRequest;
import com.hrhelper.backend.application.dto.AttachApplicationsResponse;
import com.hrhelper.backend.security.CurrentUser;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Applications on a JD (REWORK 1 F5–F7). */
@RestController
@RequestMapping("/api/jds/{jdId}/applications")
public class ApplicationController {

    private final ApplicationService applicationService;

    public ApplicationController(ApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @PostMapping
    public ResponseEntity<AttachApplicationsResponse> attach(
            @PathVariable UUID jdId, @Valid @RequestBody AttachApplicationsRequest request) {
        AttachApplicationsResponse body =
                applicationService.attach(CurrentUser.id(), jdId, request.cvIds());
        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @GetMapping
    public List<ApplicationResponse> list(@PathVariable UUID jdId) {
        return applicationService.list(CurrentUser.id(), jdId);
    }

    @DeleteMapping("/{applicationId}")
    public ResponseEntity<Void> delete(
            @PathVariable UUID jdId, @PathVariable UUID applicationId) {
        applicationService.delete(CurrentUser.id(), jdId, applicationId);
        return ResponseEntity.noContent().build();
    }
}
