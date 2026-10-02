package com.hrhelper.backend.dashboard;

import com.hrhelper.backend.dashboard.dto.DashboardResponse;
import com.hrhelper.backend.security.CurrentUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Landing dashboard read model (REWORK 2 D30): {@code GET /api/dashboard}. */
@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    private final DashboardService dashboardService;

    public DashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @GetMapping
    public DashboardResponse get() {
        return dashboardService.load(CurrentUser.id());
    }
}
