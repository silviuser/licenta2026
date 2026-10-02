package com.hrhelper.backend.dashboard;

import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.application.dto.JdApplicationCount;
import com.hrhelper.backend.common.ProcessingStatus;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.dashboard.dto.DashboardKpis;
import com.hrhelper.backend.dashboard.dto.DashboardResponse;
import com.hrhelper.backend.dashboard.dto.LastMatchKpi;
import com.hrhelper.backend.dashboard.dto.MatchSummaryRow;
import com.hrhelper.backend.dashboard.dto.PositionLastMatch;
import com.hrhelper.backend.dashboard.dto.PositionRow;
import com.hrhelper.backend.dashboard.dto.PositionSummary;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import com.hrhelper.backend.matching.JobStatus;
import com.hrhelper.backend.matching.MatchJobRepository;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Read model for the landing dashboard (REWORK 2 D30). Assembles all KPIs and the
 * position list from a fixed set of aggregate queries (counts + group-by +
 * projections) — no per-position queries and no entity/collection loading.
 */
@Service
public class DashboardService {

    private static final List<ProcessingStatus> PROCESSING_STATES =
            List.of(ProcessingStatus.PENDING, ProcessingStatus.PROCESSING);

    private final JobDescriptionRepository jdRepository;
    private final ApplicationRepository applicationRepository;
    private final CvRepository cvRepository;
    private final MatchJobRepository matchJobRepository;

    public DashboardService(
            JobDescriptionRepository jdRepository,
            ApplicationRepository applicationRepository,
            CvRepository cvRepository,
            MatchJobRepository matchJobRepository) {
        this.jdRepository = jdRepository;
        this.applicationRepository = applicationRepository;
        this.cvRepository = cvRepository;
        this.matchJobRepository = matchJobRepository;
    }

    @Transactional(readOnly = true)
    public DashboardResponse load(UUID ownerId) {
        long openPositions = jdRepository.countByOwnerId(ownerId);
        long uniqueCandidates = applicationRepository.countDistinctCvByOwnerId(ownerId);
        long cvsProcessing =
                cvRepository.countByOwnerIdAndProcessingStatusIn(ownerId, PROCESSING_STATES);

        List<PositionRow> positionRows = jdRepository.findPositionRows(ownerId);

        Map<UUID, Long> appCounts =
                applicationRepository.countByJdGrouped(ownerId).stream()
                        .collect(
                                Collectors.toMap(
                                        JdApplicationCount::getJdId, JdApplicationCount::getCount));

        // Rows are newest-first: the first row seen per JD is its latest match.
        List<MatchSummaryRow> matchRows = matchJobRepository.findMatchSummaries(ownerId);
        Map<UUID, MatchSummaryRow> latestPerJd = new HashMap<>();
        MatchSummaryRow lastSucceeded = null;
        for (MatchSummaryRow row : matchRows) {
            latestPerJd.putIfAbsent(row.getJdId(), row);
            if (row.getStatus() == JobStatus.SUCCEEDED && row.getFinishedAt() != null) {
                if (lastSucceeded == null
                        || row.getFinishedAt().isAfter(lastSucceeded.getFinishedAt())) {
                    lastSucceeded = row;
                }
            }
        }

        Map<UUID, String> titles =
                positionRows.stream()
                        .collect(Collectors.toMap(PositionRow::getJdId, PositionRow::getTitle));

        List<PositionSummary> positions =
                positionRows.stream()
                        .map(row -> toPositionSummary(row, appCounts, latestPerJd))
                        .sorted(Comparator.comparing(PositionSummary::createdAt).reversed())
                        .toList();

        LastMatchKpi lastMatchKpi = toLastMatchKpi(lastSucceeded, titles);
        DashboardKpis kpis =
                new DashboardKpis(openPositions, uniqueCandidates, cvsProcessing, lastMatchKpi);
        return new DashboardResponse(kpis, positions);
    }

    private PositionSummary toPositionSummary(
            PositionRow row, Map<UUID, Long> appCounts, Map<UUID, MatchSummaryRow> latestPerJd) {
        MatchSummaryRow latest = latestPerJd.get(row.getJdId());
        PositionLastMatch lastMatch =
                latest == null
                        ? null
                        : new PositionLastMatch(
                                latest.getJobId(),
                                latest.getStatus().name(),
                                latest.getTopScore(),
                                latest.getFinishedAt());
        return new PositionSummary(
                row.getJdId(),
                row.getTitle(),
                row.getProcessingStatus().name(),
                appCounts.getOrDefault(row.getJdId(), 0L),
                row.getCreatedAt(),
                lastMatch);
    }

    private LastMatchKpi toLastMatchKpi(MatchSummaryRow lastSucceeded, Map<UUID, String> titles) {
        if (lastSucceeded == null) {
            return null;
        }
        return new LastMatchKpi(
                lastSucceeded.getJobId(),
                lastSucceeded.getJdId(),
                titles.get(lastSucceeded.getJdId()),
                lastSucceeded.getFinishedAt(),
                lastSucceeded.getTopScore());
    }
}
