package com.hrhelper.backend.apply;

import com.hrhelper.backend.apply.dto.ApplyLinkResponse;
import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.config.AppProperties;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Manages a JD's public apply link (REWORK 3 D33). All operations are owner-scoped
 * (D6): generate/regenerate the token, toggle it on/off, and read its state.
 * Regenerating overwrites the token column, so the previous link instantly stops
 * resolving.
 */
@Service
public class ApplyLinkService {

    private final JobDescriptionRepository jdRepository;
    private final ApplyTokenGenerator tokenGenerator;
    private final AppProperties appProperties;

    public ApplyLinkService(
            JobDescriptionRepository jdRepository,
            ApplyTokenGenerator tokenGenerator,
            AppProperties appProperties) {
        this.jdRepository = jdRepository;
        this.tokenGenerator = tokenGenerator;
        this.appProperties = appProperties;
    }

    /** Generate or regenerate the token and enable the link. */
    @Transactional
    public ApplyLinkResponse generate(UUID ownerId, UUID jdId) {
        JobDescription jd = requireJd(ownerId, jdId);
        jd.setApplyToken(tokenGenerator.generate());
        jd.setApplyLinkEnabled(true);
        jdRepository.save(jd);
        return toResponse(jd);
    }

    /** Enable/disable an existing link. Fails if no token has been generated yet. */
    @Transactional
    public ApplyLinkResponse setEnabled(UUID ownerId, UUID jdId, boolean enabled) {
        JobDescription jd = requireJd(ownerId, jdId);
        if (jd.getApplyToken() == null) {
            throw new BadRequestException(
                    "apply_link_not_generated", "generate an apply link before toggling it");
        }
        jd.setApplyLinkEnabled(enabled);
        jdRepository.save(jd);
        return toResponse(jd);
    }

    @Transactional(readOnly = true)
    public ApplyLinkResponse getState(UUID ownerId, UUID jdId) {
        return toResponse(requireJd(ownerId, jdId));
    }

    private JobDescription requireJd(UUID ownerId, UUID jdId) {
        return jdRepository
                .findByIdAndOwnerId(jdId, ownerId)
                .orElseThrow(() -> new NotFoundException("job description not found"));
    }

    private ApplyLinkResponse toResponse(JobDescription jd) {
        if (jd.getApplyToken() == null) {
            return ApplyLinkResponse.none();
        }
        return ApplyLinkResponse.of(
                jd.isApplyLinkEnabled(), appProperties.applyUrl(jd.getApplyToken()));
    }
}
