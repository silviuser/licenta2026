package com.hrhelper.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;

import com.hrhelper.backend.matching.dto.MissingSkills;
import com.hrhelper.backend.nlp.dto.CandidateDto;
import com.hrhelper.backend.nlp.dto.MatchResponse;
import com.hrhelper.backend.nlp.dto.MatchedRequirementDto;
import com.hrhelper.backend.nlp.dto.RequirementDto;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class ExplanationServiceTest {

    private final ExplanationService service = new ExplanationService();

    private MatchedRequirementDto matched(
            String text, String importance, String surface, String section, double score) {
        return new MatchedRequirementDto(
                new RequirementDto(text, null, null, importance, 0.9),
                new CandidateDto("uri:" + text, text, surface, section, "lexical_kept", 0.8, 0.7),
                score);
    }

    private RequirementDto req(String text, String importance) {
        return new RequirementDto(text, null, null, importance, 0.9);
    }

    private MatchResponse response() {
        return new MatchResponse(
                "cv",
                "jd",
                0.5,
                "possible",
                0.5,
                0.5,
                List.of(matched("Java", "required", "Java 17", "experience", 0.90)),
                List.of(
                        matched("Docker", "nice_to_have", "Docker", "skills", 0.80),
                        matched("AWS", "nice_to_have", "AWS", "skills", 0.85)),
                List.of(req("Kubernetes", "required")),
                List.of(req("GraphQL", "nice_to_have")),
                OffsetDateTime.parse("2026-06-06T12:00:00Z"),
                "pv@1");
    }

    @Test
    void explainReportsCoverageStrengthsAndMissingCritical() {
        String explanation = service.explain(response());

        assertThat(explanation)
                .isEqualTo(
                        "Covers 1/2 required. Strengths: Java (0.90), AWS (0.85), Docker (0.80)."
                                + " Missing critical: Kubernetes.");
    }

    @Test
    void explainHandlesNoRequirements() {
        MatchResponse mr =
                new MatchResponse(
                        "cv", "jd", 0.0, "no", 0.0, 0.0,
                        List.of(), List.of(), List.of(), List.of(),
                        OffsetDateTime.parse("2026-06-06T12:00:00Z"), "pv@1");

        assertThat(service.explain(mr)).isEqualTo("Covers 0/0 required.");
    }

    @Test
    void matchedSkillsFlattensRequiredAndNiceToHaveWithEvidence() {
        var skills = service.matchedSkills(response());

        assertThat(skills).hasSize(3);
        assertThat(skills.get(0).requirementText()).isEqualTo("Java");
        assertThat(skills.get(0).importance()).isEqualTo("required");
        assertThat(skills.get(0).evidenceSurfaceForm()).isEqualTo("Java 17");
        assertThat(skills.get(0).evidenceSection()).isEqualTo("experience");
        assertThat(skills.get(0).matchScore()).isEqualTo(0.90);
    }

    @Test
    void missingSkillsSplitByImportance() {
        MissingSkills missing = service.missingSkills(response());

        assertThat(missing.required()).containsExactly("Kubernetes");
        assertThat(missing.niceToHave()).containsExactly("GraphQL");
    }

    @Test
    void matchedSkillsStripsSentinelSectionsButKeepsRealOnes() {
        MatchResponse mr =
                new MatchResponse(
                        "cv", "jd", 0.5, "possible", 0.5, 0.5,
                        List.of(
                                matched(
                                        "microservices (other)",
                                        "required",
                                        "microservices (skills)",
                                        "unknown",
                                        0.79)),
                        List.of(), List.of(), List.of(),
                        OffsetDateTime.parse("2026-06-06T12:00:00Z"),
                        "pv@1");

        var skill = service.matchedSkills(mr).get(0);

        // "(other)" sentinel stripped from the requirement label.
        assertThat(skill.requirementText()).isEqualTo("microservices");
        // Real "(skills)" section kept inside the surface form.
        assertThat(skill.evidenceSurfaceForm()).isEqualTo("microservices (skills)");
        // Hardcoded "unknown" section field nulled out so the UI omits it.
        assertThat(skill.evidenceSection()).isNull();
    }

    @Test
    void matchedSkillsPreservesEscoDisambiguatorAndRealSection() {
        MatchResponse mr =
                new MatchResponse(
                        "cv", "jd", 0.5, "possible", 0.5, 0.5,
                        List.of(
                                matched(
                                        "Java (computer programming)",
                                        "required",
                                        "Java 17",
                                        "experience",
                                        1.0)),
                        List.of(), List.of(), List.of(),
                        OffsetDateTime.parse("2026-06-06T12:00:00Z"),
                        "pv@1");

        var skill = service.matchedSkills(mr).get(0);

        // ESCO disambiguator "(computer programming)" is not a sentinel — kept.
        assertThat(skill.requirementText()).isEqualTo("Java (computer programming)");
        assertThat(skill.evidenceSurfaceForm()).isEqualTo("Java 17");
        assertThat(skill.evidenceSection()).isEqualTo("experience");
    }

    @Test
    void missingSkillsAndExplainStripSentinelSections() {
        MatchResponse mr =
                new MatchResponse(
                        "cv", "jd", 0.0, "no", 0.0, 0.0,
                        List.of(),
                        List.of(),
                        List.of(
                                req("MongoDB (other)", "required"),
                                req("web services (other)", "required")),
                        List.of(),
                        OffsetDateTime.parse("2026-06-06T12:00:00Z"),
                        "pv@1");

        assertThat(service.missingSkills(mr).required())
                .containsExactly("MongoDB", "web services");

        assertThat(service.explain(mr))
                .isEqualTo("Covers 0/2 required. Missing critical: MongoDB, web services.");
    }
}
