package com.hrhelper.backend.jd.dto;

import com.hrhelper.backend.jd.JobDescription;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record JdResponse(
        UUID id,
        String title,
        String descriptionText,
        List<RequirementResponse> requirements,
        String processingStatus,
        String processingError,
        Instant createdAt,
        Instant updatedAt) {

    public static JdResponse from(JobDescription jd) {
        return new JdResponse(
                jd.getId(),
                jd.getTitle(),
                jd.getDescriptionText(),
                jd.getRequirements().stream().map(RequirementResponse::from).toList(),
                jd.getProcessingStatus().name(),
                jd.getProcessingError(),
                jd.getCreatedAt(),
                jd.getUpdatedAt());
    }
}
