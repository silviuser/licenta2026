package com.hrhelper.backend.application;

import com.hrhelper.backend.application.dto.ApplicationResponse;
import com.hrhelper.backend.application.dto.AttachApplicationsResponse;
import com.hrhelper.backend.common.EmailResolution;
import com.hrhelper.backend.common.NotFoundException;
import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** CV ↔ JD application links (REWORK 1 D20). All operations are owner-scoped (D6). */
@Service
public class ApplicationService {

    private final ApplicationRepository applicationRepository;
    private final JobDescriptionRepository jdRepository;
    private final CvRepository cvRepository;

    public ApplicationService(
            ApplicationRepository applicationRepository,
            JobDescriptionRepository jdRepository,
            CvRepository cvRepository) {
        this.applicationRepository = applicationRepository;
        this.jdRepository = jdRepository;
        this.cvRepository = cvRepository;
    }

    /** Attach existing library CVs to a JD; idempotent on the {@code (cv, jd)} pair. */
    @Transactional
    public AttachApplicationsResponse attach(UUID ownerId, UUID jdId, List<UUID> cvIds) {
        requireJd(ownerId, jdId);

        List<ApplicationResponse> created = new ArrayList<>();
        List<UUID> alreadyExisted = new ArrayList<>();
        List<UUID> notFound = new ArrayList<>();

        for (UUID cvId : cvIds.stream().distinct().toList()) {
            Cv cv = cvRepository.findByIdAndOwnerId(cvId, ownerId).orElse(null);
            if (cv == null) {
                notFound.add(cvId);
                continue;
            }
            if (applicationRepository.existsByCvIdAndJdId(cvId, jdId)) {
                alreadyExisted.add(cvId);
                continue;
            }
            Application app =
                    applicationRepository.save(
                            new Application(UUID.randomUUID(), ownerId, cvId, jdId));
            created.add(toResponse(app, cv));
        }
        return new AttachApplicationsResponse(created, alreadyExisted, notFound);
    }

    @Transactional(readOnly = true)
    public List<ApplicationResponse> list(UUID ownerId, UUID jdId) {
        requireJd(ownerId, jdId);
        List<Application> applications =
                applicationRepository.findByJdIdAndOwnerIdOrderByCreatedAtAsc(jdId, ownerId);

        Map<UUID, Cv> cvs = new LinkedHashMap<>();
        cvRepository
                .findAllById(applications.stream().map(Application::getCvId).toList())
                .forEach(cv -> cvs.put(cv.getId(), cv));

        return applications.stream().map(app -> toResponse(app, cvs.get(app.getCvId()))).toList();
    }

    @Transactional
    public void delete(UUID ownerId, UUID jdId, UUID applicationId) {
        requireJd(ownerId, jdId);
        Application app =
                applicationRepository
                        .findByIdAndOwnerId(applicationId, ownerId)
                        .filter(a -> a.getJdId().equals(jdId))
                        .orElseThrow(() -> new NotFoundException("application not found"));
        applicationRepository.delete(app);
    }

    private JobDescription requireJd(UUID ownerId, UUID jdId) {
        return jdRepository
                .findByIdAndOwnerId(jdId, ownerId)
                .orElseThrow(() -> new NotFoundException("job description not found"));
    }

    private ApplicationResponse toResponse(Application app, Cv cv) {
        EmailResolution.Resolved email =
                EmailResolution.resolve(
                        app.getCandidateEmail(),
                        cv != null ? cv.getManualEmail() : null,
                        cv != null ? cv.getExtractedEmail() : null);
        return new ApplicationResponse(
                app.getId(),
                app.getCvId(),
                cv != null ? cv.getOriginalFilename() : null,
                cv != null ? cv.getProcessingStatus().name() : null,
                app.getOrigin().name(),
                app.getCandidateName(),
                app.getCandidateEmail(),
                app.getCandidatePhone(),
                email.email(),
                email.source(),
                app.getAppliedAt(),
                app.getCreatedAt());
    }
}
