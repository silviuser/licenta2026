package com.hrhelper.backend.cv;

import com.hrhelper.backend.common.ProcessingStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CvRepository extends JpaRepository<Cv, UUID> {

    Page<Cv> findByOwnerId(UUID ownerId, Pageable pageable);

    Optional<Cv> findByIdAndOwnerId(UUID id, UUID ownerId);

    Optional<Cv> findByOwnerIdAndContentHash(UUID ownerId, String contentHash);

    /** CVs still being processed — dashboard KPI (D30). */
    long countByOwnerIdAndProcessingStatusIn(UUID ownerId, Collection<ProcessingStatus> statuses);

    /**
     * Ids of READY CVs that have no email from any source — the startup backfill
     * set (REWORK 4 D46). Only ids are loaded so the (potentially large) PDF bytes
     * are fetched one CV at a time during processing.
     */
    @Query(
            "select c.id from Cv c where c.processingStatus = :status"
                    + " and c.extractedEmail is null and c.manualEmail is null")
    List<UUID> findIdsForEmailBackfill(@Param("status") ProcessingStatus status);

    /**
     * Ids of CVs still awaiting (or stuck mid-) extraction — the startup recovery set
     * ({@link CvRecoveryRunner}). Extraction is dispatched only once, at upload, onto an
     * in-memory executor queue; CVs left PENDING by a saturated pool, queued tasks lost
     * to a restart, or rows orphaned in PROCESSING by a crash would otherwise never
     * resolve. Only ids are loaded so the PDF bytes are fetched one CV at a time.
     */
    @Query("select c.id from Cv c where c.processingStatus in :statuses")
    List<UUID> findIdsByProcessingStatusIn(
            @Param("statuses") Collection<ProcessingStatus> statuses);
}
