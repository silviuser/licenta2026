package com.hrhelper.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.hrhelper.backend.application.Application;
import com.hrhelper.backend.application.ApplicationRepository;
import com.hrhelper.backend.cv.Cv;
import com.hrhelper.backend.cv.CvRepository;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MatchPoolServiceTest {

    @Mock private ApplicationRepository applicationRepository;
    @Mock private CvRepository cvRepository;
    @Mock private JobDescriptionRepository jdRepository;

    private MatchPoolService service;

    private final UUID owner = UUID.randomUUID();
    private final UUID jd1 = UUID.randomUUID();
    private final UUID jd2 = UUID.randomUUID();

    private final UUID cvA = UUID.randomUUID();
    private final UUID cvB = UUID.randomUUID();
    private final UUID cvC = UUID.randomUUID(); // same hash as cvB (a duplicate file)
    private final UUID cvD = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        service = new MatchPoolService(applicationRepository, cvRepository, jdRepository);
    }

    private Cv cv(UUID id, String hash) {
        return new Cv(id, owner, id + ".pdf", "application/pdf", 3, new byte[] {1}, hash);
    }

    private Application app(UUID cvId, UUID jdId) {
        return new Application(UUID.randomUUID(), owner, cvId, jdId);
    }

    @Test
    void poolWithoutSourcesKeepsOnlyDirect() {
        when(applicationRepository.findByJdIdAndOwnerIdOrderByCreatedAtAsc(jd1, owner))
                .thenReturn(List.of(app(cvA, jd1), app(cvB, jd1)));
        when(cvRepository.findAllById(any()))
                .thenReturn(List.of(cv(cvA, "hashA"), cv(cvB, "hashB")));

        List<PoolEntry> pool = service.buildPool(owner, jd1, List.of());

        assertThat(pool).extracting(e -> e.cv().getId()).containsExactly(cvA, cvB);
        assertThat(pool).allMatch(e -> e.source().equals(PoolEntry.DIRECT));
        assertThat(pool).allMatch(e -> e.sourceJdId() == null && e.sourceJdTitle() == null);
    }

    @Test
    void poolFromSelectedSourceDedupesByHashAndRecordsProvenance() {
        when(applicationRepository.findByJdIdAndOwnerIdOrderByCreatedAtAsc(jd1, owner))
                .thenReturn(List.of(app(cvA, jd1), app(cvB, jd1)));
        when(applicationRepository.findByOwnerIdAndJdIdInOrderByCreatedAtAsc(owner, List.of(jd2)))
                .thenReturn(
                        List.of(
                                app(cvC, jd2), // duplicate of cvB by hash → excluded
                                app(cvD, jd2)));
        when(jdRepository.findAllById(List.of(jd2)))
                .thenReturn(List.of(new JobDescription(jd2, owner, "Role 2", null)));
        when(cvRepository.findAllById(any()))
                .thenReturn(
                        List.of(
                                cv(cvA, "hashA"),
                                cv(cvB, "hashB"),
                                cv(cvC, "hashB"), // same content hash as cvB
                                cv(cvD, "hashD")));

        List<PoolEntry> pool = service.buildPool(owner, jd1, List.of(jd2));

        // cvC (duplicate of cvB) is dropped; cvD enters as OTHER_JD from jd2.
        assertThat(pool).extracting(e -> e.cv().getId()).containsExactly(cvA, cvB, cvD);
        assertThat(pool.get(0).source()).isEqualTo(PoolEntry.DIRECT);
        assertThat(pool.get(1).source()).isEqualTo(PoolEntry.DIRECT);
        PoolEntry pooled = pool.get(2);
        assertThat(pooled.source()).isEqualTo(PoolEntry.OTHER_JD);
        assertThat(pooled.sourceJdId()).isEqualTo(jd2);
        assertThat(pooled.sourceJdTitle()).isEqualTo("Role 2");
    }

    @Test
    void directApplicationTakesPrecedenceOverSource() {
        // cvA is applied to both jd1 (direct) and jd2 (source) — must appear once as DIRECT.
        when(applicationRepository.findByJdIdAndOwnerIdOrderByCreatedAtAsc(jd1, owner))
                .thenReturn(List.of(app(cvA, jd1)));
        when(applicationRepository.findByOwnerIdAndJdIdInOrderByCreatedAtAsc(owner, List.of(jd2)))
                .thenReturn(List.of(app(cvA, jd2)));
        when(jdRepository.findAllById(List.of(jd2)))
                .thenReturn(List.of(new JobDescription(jd2, owner, "Role 2", null)));
        when(cvRepository.findAllById(any())).thenReturn(List.of(cv(cvA, "hashA")));

        List<PoolEntry> pool = service.buildPool(owner, jd1, List.of(jd2));

        assertThat(pool).hasSize(1);
        assertThat(pool.get(0).source()).isEqualTo(PoolEntry.DIRECT);
        assertThat(pool.get(0).sourceJdId()).isNull();
    }
}
