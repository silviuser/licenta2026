package com.hrhelper.backend.matching;

import com.hrhelper.backend.dashboard.dto.MatchSummaryRow;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;

public interface MatchJobRepository
        extends JpaRepository<MatchJob, UUID>, JpaSpecificationExecutor<MatchJob> {

    Optional<MatchJob> findByIdAndOwnerId(UUID id, UUID ownerId);

    Page<MatchJob> findByOwnerId(UUID ownerId, Pageable pageable);

    /**
     * Match summaries (newest first) for the dashboard (D30): the service reduces
     * these to the latest match per JD and the latest succeeded match overall — one
     * query, scalars only, no result_json parsing.
     */
    @Query(
            "select m.id as jobId, m.jdId as jdId, m.status as status, m.topScore as topScore,"
                    + " m.finishedAt as finishedAt, m.createdAt as createdAt from MatchJob m"
                    + " where m.ownerId = :ownerId order by m.createdAt desc")
    List<MatchSummaryRow> findMatchSummaries(UUID ownerId);

    /** Remaining match jobs still pointing at a CV — guards orphan-CV cleanup against silent ON DELETE CASCADE wipes. */
    long countByCvId(UUID cvId);
}
