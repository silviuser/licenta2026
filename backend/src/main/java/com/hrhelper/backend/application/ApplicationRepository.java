package com.hrhelper.backend.application;

import com.hrhelper.backend.application.dto.JdApplicationCount;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ApplicationRepository extends JpaRepository<Application, UUID> {

    List<Application> findByJdIdAndOwnerIdOrderByCreatedAtAsc(UUID jdId, UUID ownerId);

    /** Applications across the selected source JDs, ordered for deterministic provenance (D27/D29). */
    List<Application> findByOwnerIdAndJdIdInOrderByCreatedAtAsc(
            UUID ownerId, Collection<UUID> jdIds);

    List<Application> findByOwnerId(UUID ownerId);

    /** Distinct CVs that applied to at least one position — dashboard KPI (D30). */
    @Query("select count(distinct a.cvId) from Application a where a.ownerId = :ownerId")
    long countDistinctCvByOwnerId(UUID ownerId);

    /** Per-JD application counts for the dashboard, in one grouped query (D30, no N+1). */
    @Query(
            "select a.jdId as jdId, count(a) as count from Application a"
                    + " where a.ownerId = :ownerId group by a.jdId")
    List<JdApplicationCount> countByJdGrouped(UUID ownerId);

    Optional<Application> findByIdAndOwnerId(UUID id, UUID ownerId);

    boolean existsByCvIdAndJdId(UUID cvId, UUID jdId);

    Optional<Application> findByCvIdAndJdId(UUID cvId, UUID jdId);

    long countByJdId(UUID jdId);

    /** Re-application dedup: an existing candidate application for (jd, email) (REWORK 3 D36). */
    Optional<Application> findByJdIdAndCandidateEmailIgnoreCase(UUID jdId, String candidateEmail);

    /** Remaining references to a CV — drives orphan cleanup on CV replacement (D36). */
    long countByCvId(UUID cvId);

    /** Distinct CVs that applied to a JD — used to find orphan candidates when the JD is deleted. */
    @Query("select distinct a.cvId from Application a where a.jdId = :jdId")
    List<UUID> findDistinctCvIdsByJdId(UUID jdId);
}
