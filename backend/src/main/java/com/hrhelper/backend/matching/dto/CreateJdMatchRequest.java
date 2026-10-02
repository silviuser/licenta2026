package com.hrhelper.backend.matching.dto;

import java.util.List;
import java.util.UUID;

/**
 * Launch a per-JD match (REWORK 2 D27/D28). {@code sourceJdIds} are the other JDs
 * to pull applications from (selective pooling); a null/empty list means "score
 * only the CVs that applied directly to this JD".
 */
public record CreateJdMatchRequest(List<UUID> sourceJdIds) {

    public List<UUID> sourceJdIdsOrEmpty() {
        return sourceJdIds == null ? List.of() : sourceJdIds;
    }
}
