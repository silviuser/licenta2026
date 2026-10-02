package com.hrhelper.backend.matching;

import com.hrhelper.backend.matching.dto.CreateJdMatchRequest;
import com.hrhelper.backend.security.CurrentUser;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Launch a per-JD match (REWORK 1 F8): {@code POST /api/jds/{id}/match}. */
@RestController
@RequestMapping("/api/jds/{jdId}/match")
public class JdMatchController {

    private final JdMatchService jdMatchService;

    public JdMatchController(JdMatchService jdMatchService) {
        this.jdMatchService = jdMatchService;
    }

    @PostMapping
    public ResponseEntity<Map<String, String>> match(
            @PathVariable UUID jdId, @RequestBody(required = false) CreateJdMatchRequest request) {
        List<UUID> sourceJdIds = request == null ? List.of() : request.sourceJdIdsOrEmpty();
        MatchJob job = jdMatchService.createMatch(CurrentUser.id(), jdId, sourceJdIds);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(Map.of("jobId", job.getId().toString(), "status", job.getStatus().name()));
    }
}
