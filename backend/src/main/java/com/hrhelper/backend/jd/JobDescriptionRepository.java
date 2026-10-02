package com.hrhelper.backend.jd;

import com.hrhelper.backend.dashboard.dto.PositionRow;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface JobDescriptionRepository extends JpaRepository<JobDescription, UUID> {

    Page<JobDescription> findByOwnerId(UUID ownerId, Pageable pageable);

    Optional<JobDescription> findByIdAndOwnerId(UUID id, UUID ownerId);

    /** Resolve a public apply link by its token (REWORK 3 D32). */
    Optional<JobDescription> findByApplyToken(String applyToken);

    long countByOwnerId(UUID ownerId);

    /**
     * Lightweight position rows for the dashboard (D30): selects scalars only, so
     * the EAGER requirements collection is never loaded (no N+1).
     */
    @Query(
            "select j.id as jdId, j.title as title, j.processingStatus as processingStatus,"
                    + " j.createdAt as createdAt from JobDescription j where j.ownerId = :ownerId")
    List<PositionRow> findPositionRows(UUID ownerId);
}
