package com.hrhelper.backend.jd;

import com.hrhelper.backend.common.PageResponse;
import com.hrhelper.backend.jd.dto.JdRequest;
import com.hrhelper.backend.jd.dto.JdResponse;
import com.hrhelper.backend.jd.dto.RequirementsUpdateRequest;
import com.hrhelper.backend.security.CurrentUser;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/jds")
public class JdController {

    private final JdService jdService;

    public JdController(JdService jdService) {
        this.jdService = jdService;
    }

    @PostMapping
    public ResponseEntity<JdResponse> create(@Valid @RequestBody JdRequest request) {
        JobDescription jd = jdService.create(CurrentUser.id(), request);
        return ResponseEntity.status(HttpStatus.CREATED).body(JdResponse.from(jd));
    }

    @GetMapping
    public PageResponse<JdResponse> list(Pageable pageable) {
        return PageResponse.from(jdService.list(CurrentUser.id(), pageable).map(JdResponse::from));
    }

    @GetMapping("/{id}")
    public JdResponse get(@PathVariable UUID id) {
        return JdResponse.from(jdService.get(CurrentUser.id(), id));
    }

    @PutMapping("/{id}")
    public JdResponse update(@PathVariable UUID id, @Valid @RequestBody JdRequest request) {
        return JdResponse.from(jdService.update(CurrentUser.id(), id, request));
    }

    /** Edit the requirement list (REWORK 1 F4): add/remove/update importance. */
    @PutMapping("/{id}/requirements")
    public JdResponse updateRequirements(
            @PathVariable UUID id, @Valid @RequestBody RequirementsUpdateRequest request) {
        return JdResponse.from(
                jdService.updateRequirements(CurrentUser.id(), id, request.requirements()));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable UUID id) {
        jdService.delete(CurrentUser.id(), id);
        return ResponseEntity.noContent().build();
    }
}
