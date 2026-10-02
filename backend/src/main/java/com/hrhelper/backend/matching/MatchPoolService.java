package com.hrhelper.backend.matching;

import com.hrhelper.backend.application.Application;
import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Builds the deduplicated CV pool for a per-JD match (REWORK 2 D27/D29).
 * Direct applications always come first; CVs applied to the explicitly selected
 * source JDs are appended, tagged with their source position. A candidate enters
 * once — dedup is by SHA-256 content hash (legacy hash-less CVs fall back to id),
 * and a direct application always wins over a pooled one.
 */
@Service
public class MatchPoolService {

    private final ApplicationRepository applicationRepository;
    private final CvRepository cvRepository;
    private final JobDescriptionRepository jdRepository;

    public MatchPoolService(
            ApplicationRepository applicationRepository,
            CvRepository cvRepository,
            JobDescriptionRepository jdRepository) {
        this.applicationRepository = applicationRepository;
        this.cvRepository = cvRepository;
        this.jdRepository = jdRepository;
    }

    @Transactional(readOnly = true)
    public List<PoolEntry> buildPool(UUID ownerId, UUID jdId, List<UUID> sourceJdIds) {
        // Direct applications on this JD, ordered for deterministic provenance. The
        // unique (cv_id, jd_id) constraint means each CV appears at most once here.
        List<Application> directApps =
                applicationRepository.findByJdIdAndOwnerIdOrderByCreatedAtAsc(jdId, ownerId);

        // Pooled applications come only from the explicitly selected source JDs
        // (D27). Each pooled CV is tagged with the first source JD it appears in.
        List<Application> sourceApps =
                (sourceJdIds == null || sourceJdIds.isEmpty())
                        ? List.of()
                        : applicationRepository.findByOwnerIdAndJdIdInOrderByCreatedAtAsc(
                                ownerId, sourceJdIds);

        Map<UUID, String> jdTitles = loadJdTitles(ownerId, sourceJdIds);

        List<UUID> allIds = new ArrayList<>();
        directApps.forEach(a -> allIds.add(a.getCvId()));
        sourceApps.forEach(a -> allIds.add(a.getCvId()));
        Map<UUID, Cv> cvs =
                cvRepository.findAllById(allIds).stream()
                        .collect(Collectors.toMap(Cv::getId, Function.identity()));

        List<PoolEntry> pool = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();

        for (Application app : directApps) {
            Cv cv = cvs.get(app.getCvId());
            if (cv != null && seen.add(dedupKey(cv))) {
                pool.add(PoolEntry.direct(cv, app));
            }
        }
        for (Application app : sourceApps) {
            Cv cv = cvs.get(app.getCvId());
            if (cv != null && seen.add(dedupKey(cv))) {
                UUID sourceJdId = app.getJdId();
                pool.add(PoolEntry.fromOtherJd(cv, sourceJdId, jdTitles.get(sourceJdId), app));
            }
        }
        return pool;
    }

    private Map<UUID, String> loadJdTitles(UUID ownerId, List<UUID> sourceJdIds) {
        if (sourceJdIds == null || sourceJdIds.isEmpty()) {
            return Map.of();
        }
        Map<UUID, String> titles = new LinkedHashMap<>();
        for (JobDescription jd : jdRepository.findAllById(sourceJdIds)) {
            if (jd.getOwnerId().equals(ownerId)) {
                titles.put(jd.getId(), jd.getTitle());
            }
        }
        return titles;
    }

    private String dedupKey(Cv cv) {
        return cv.getContentHash() != null ? cv.getContentHash() : cv.getId().toString();
    }
}
