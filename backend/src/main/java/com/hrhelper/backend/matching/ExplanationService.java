package com.hrhelper.backend.matching;

import com.hrhelper.backend.matching.dto.MatchedSkill;
import com.hrhelper.backend.matching.dto.MissingSkills;
import com.hrhelper.backend.nlp.dto.MatchResponse;
import com.hrhelper.backend.nlp.dto.MatchedRequirementDto;
import com.hrhelper.backend.nlp.dto.RequirementDto;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;

/**
 * Deterministic, LLM-free derivation of the per-candidate report from an NLP
 * {@link MatchResponse} (REWORK 1 D25). Pure functions — fully unit-testable.
 */
@Service
public class ExplanationService {

    private static final int TOP_STRENGTHS = 3;

    /**
     * Non-informative CV/JD section sentinels. {@code other} is the catch-all
     * bucket assigned to free-text JD prose; {@code unknown} is the
     * expansion-candidate fallback. Neither is shown to recruiters.
     */
    private static final Set<String> SENTINEL_SECTIONS = Set.of("other", "unknown");

    /** Matches a trailing " (other)" / " (unknown)" tag (case-insensitive). */
    private static final Pattern SENTINEL_SECTION_SUFFIX =
            Pattern.compile("\\s*\\((?:other|unknown)\\)\\s*$", Pattern.CASE_INSENSITIVE);

    /** Flatten matched required + nice-to-have into the report's skill list. */
    public List<MatchedSkill> matchedSkills(MatchResponse mr) {
        return Stream.concat(mr.matchedRequired().stream(), mr.matchedNiceToHave().stream())
                .map(
                        m ->
                                new MatchedSkill(
                                        cleanLabel(m.requirement().text()),
                                        m.requirement().importance(),
                                        m.cvCandidate() != null ? cleanLabel(m.cvCandidate().surfaceForm()) : null,
                                        m.cvCandidate() != null ? cleanSection(m.cvCandidate().section()) : null,
                                        m.matchScore()))
                .toList();
    }

    /** Unmet requirements split by importance. */
    public MissingSkills missingSkills(MatchResponse mr) {
        return new MissingSkills(
                mr.unmatchedRequired().stream().map(r -> cleanLabel(r.text())).toList(),
                mr.unmatchedNiceToHave().stream().map(r -> cleanLabel(r.text())).toList());
    }

    /**
     * One-line, data-derived ranking rationale: required coverage X/Y, the top-3
     * strengths by match score, and the unmet hard requirements.
     */
    public String explain(MatchResponse mr) {
        int requiredCovered = mr.matchedRequired().size();
        int requiredTotal = requiredCovered + mr.unmatchedRequired().size();

        StringBuilder sb = new StringBuilder();
        sb.append("Covers ").append(requiredCovered).append("/").append(requiredTotal)
                .append(" required.");

        List<String> strengths = topStrengths(mr);
        if (!strengths.isEmpty()) {
            sb.append(" Strengths: ").append(String.join(", ", strengths)).append(".");
        }

        List<String> missingCritical =
                mr.unmatchedRequired().stream().map(r -> cleanLabel(r.text())).toList();
        if (!missingCritical.isEmpty()) {
            sb.append(" Missing critical: ").append(String.join(", ", missingCritical)).append(".");
        }
        return sb.toString();
    }

    private List<String> topStrengths(MatchResponse mr) {
        List<MatchedRequirementDto> all = new ArrayList<>();
        all.addAll(mr.matchedRequired());
        all.addAll(mr.matchedNiceToHave());
        return all.stream()
                .sorted(Comparator.comparingDouble(MatchedRequirementDto::matchScore).reversed())
                .limit(TOP_STRENGTHS)
                .map(m -> label(m) + " (" + String.format(Locale.US, "%.2f", m.matchScore()) + ")")
                .toList();
    }

    private String label(MatchedRequirementDto m) {
        RequirementDto req = m.requirement();
        if (req.skillLabel() != null && !req.skillLabel().isBlank()) {
            return cleanLabel(req.skillLabel());
        }
        return cleanLabel(req.text());
    }

    /**
     * Strip a trailing non-informative section tag ("(other)" / "(unknown)")
     * from a display label. Real, meaningful parentheticals — ESCO
     * disambiguators like "Java (computer programming)" and real sections like
     * "(skills)" — are preserved.
     */
    private static String cleanLabel(String label) {
        if (label == null) {
            return null;
        }
        return SENTINEL_SECTION_SUFFIX.matcher(label).replaceAll("").strip();
    }

    /**
     * Map a non-informative section sentinel ({@code other} / {@code unknown})
     * or a blank value to {@code null} so the UI omits it entirely. Real
     * sections ({@code skills}, {@code experience}, …) pass through unchanged.
     */
    private static String cleanSection(String section) {
        if (section == null) {
            return null;
        }
        String trimmed = section.strip();
        if (trimmed.isEmpty() || SENTINEL_SECTIONS.contains(trimmed.toLowerCase(Locale.US))) {
            return null;
        }
        return trimmed;
    }
}
