package com.hrhelper.backend.apply;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import com.hrhelper.backend.apply.dto.ApplyLinkResponse;
import com.hrhelper.backend.common.BadRequestException;
import com.hrhelper.backend.config.AppProperties;
import com.hrhelper.backend.jd.JobDescription;
import com.hrhelper.backend.jd.JobDescriptionRepository;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ApplyLinkServiceTest {

    @Mock private JobDescriptionRepository jdRepository;

    private ApplyLinkService service;

    private final UUID owner = UUID.randomUUID();
    private final UUID jdId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        AppProperties props = new AppProperties("http://localhost:5173", 60, 10);
        service = new ApplyLinkService(jdRepository, new ApplyTokenGenerator(), props);
    }

    private JobDescription jd() {
        return new JobDescription(jdId, owner, "Backend Engineer", "desc");
    }

    @Test
    void generateSetsTokenEnablesLinkAndBuildsUrl() {
        JobDescription jd = jd();
        when(jdRepository.findByIdAndOwnerId(jdId, owner)).thenReturn(Optional.of(jd));
        when(jdRepository.save(jd)).thenReturn(jd);

        ApplyLinkResponse res = service.generate(owner, jdId);

        assertThat(jd.getApplyToken()).isNotBlank();
        assertThat(jd.isApplyLinkEnabled()).isTrue();
        assertThat(res.exists()).isTrue();
        assertThat(res.enabled()).isTrue();
        assertThat(res.url()).isEqualTo("http://localhost:5173/apply/" + jd.getApplyToken());
    }

    @Test
    void regenerateReplacesTheToken() {
        JobDescription jd = jd();
        when(jdRepository.findByIdAndOwnerId(jdId, owner)).thenReturn(Optional.of(jd));
        when(jdRepository.save(jd)).thenReturn(jd);

        service.generate(owner, jdId);
        String first = jd.getApplyToken();
        service.generate(owner, jdId);
        String second = jd.getApplyToken();

        assertThat(second).isNotEqualTo(first);
    }

    @Test
    void toggleWithoutTokenIsRejected() {
        JobDescription jd = jd(); // no token yet
        when(jdRepository.findByIdAndOwnerId(jdId, owner)).thenReturn(Optional.of(jd));

        assertThatThrownBy(() -> service.setEnabled(owner, jdId, true))
                .isInstanceOf(BadRequestException.class)
                .hasFieldOrPropertyWithValue("errorCode", "apply_link_not_generated");
    }

    @Test
    void stateIsNoneBeforeGeneration() {
        JobDescription jd = jd();
        when(jdRepository.findByIdAndOwnerId(jdId, owner)).thenReturn(Optional.of(jd));

        ApplyLinkResponse res = service.getState(owner, jdId);

        assertThat(res.exists()).isFalse();
        assertThat(res.enabled()).isFalse();
        assertThat(res.url()).isNull();
    }

    @Test
    void disableKeepsTokenButTurnsLinkOff() {
        JobDescription jd = jd();
        when(jdRepository.findByIdAndOwnerId(jdId, owner)).thenReturn(Optional.of(jd));
        when(jdRepository.save(jd)).thenReturn(jd);

        service.generate(owner, jdId);
        ApplyLinkResponse res = service.setEnabled(owner, jdId, false);

        assertThat(jd.getApplyToken()).isNotBlank();
        assertThat(res.exists()).isTrue();
        assertThat(res.enabled()).isFalse();
    }
}
