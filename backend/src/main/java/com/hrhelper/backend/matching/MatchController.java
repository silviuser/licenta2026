package com.hrhelper.backend.matching;

import com.hrhelper.backend.common.PageResponse;
import com.hrhelper.backend.matching.dto.MatchJobResponse;
import com.hrhelper.backend.security.CurrentUser;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Read side of match jobs (REWORK 1). Creation moved to
 * {@code POST /api/jds/{id}/match} ({@link JdMatchController}); the old ad-hoc
 * {@code POST /api/matches} was removed (decision A3).
 */
@RestController
@RequestMapping("/api/matches")
public class MatchController {

    private final MatchService matchService;

    public MatchController(MatchService matchService) {
        this.matchService = matchService;
    }

    @GetMapping("/{jobId}")
    public MatchJobResponse get(@PathVariable UUID jobId) {
        return matchService.get(CurrentUser.id(), jobId);
    }

    @GetMapping
    public PageResponse<MatchJobResponse> history(
            @RequestParam(required = false) UUID jdId,
            @RequestParam(required = false) JobStatus status,
            Pageable pageable) {
        return PageResponse.from(
                matchService.history(CurrentUser.id(), jdId, status, pageable).map(matchService::toResponse));
    }
}
