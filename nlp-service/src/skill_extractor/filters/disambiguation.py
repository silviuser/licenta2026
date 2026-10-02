"""Drop matches whose surface form is a proper noun in disguise.

The PhraseMatcher will happily match the literal token ``Java`` whether
it refers to the programming language, the Indonesian island, or a
coffee shop named Java. spaCy's NER tags many such occurrences as
``GPE`` (Java the island), ``ORG`` (Java the company name), or
``PERSON`` (rare). When that happens *outside the canonical Skills
section*, the match is overwhelmingly likely to be a false positive
and we drop it.

What this filter *does* do
--------------------------
1. Skip the check entirely inside the ``"skills"`` section. CV skill
   listings are dense, comma-separated and confuse NER models that
   were trained on running prose; trusting NER there hurts more than
   it helps.
2. Otherwise, look up whether the match span overlaps any
   :class:`EntitySpan` with a label in :attr:`DROP_LABELS`. If yes,
   *and* the surface form is not in the curated tech whitelist, drop
   the match.

Decoupling from spaCy
---------------------
Rather than depending directly on :class:`spacy.tokens.Span`, this
module accepts a list of :class:`EntitySpan` dataclasses. The pipeline
extracts entity spans from a real spaCy ``Doc`` and forwards them
here. This lets us unit-test the filter with no spaCy at all and keeps
the dependency graph clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from skill_extractor.models import SectionLabel


@dataclass(slots=True, frozen=True)
class EntitySpan:
    """A NER hit reduced to the fields this filter needs."""

    start_char: int
    end_char: int
    label: str  # Coarse spaCy NER label, e.g. ``"ORG"``, ``"GPE"``, ``"LOC"``


# Curated set of skill surface forms (lower-cased) that NER models
# frequently misclassify as proper nouns. We keep them even when an
# overlapping NER entity says ORG/GPE/LOC/PERSON.
#
# Keep this list focused on cases where the misclassification is
# common AND the surface form is unambiguously a tech skill in CV
# context. When in doubt, leave it out — the cost of a false negative
# (one missed skill) is lower than the cost of a false positive
# (a candidate's name treated as a skill).
_DEFAULT_TECH_WHITELIST: frozenset[str] = frozenset(
    {
        # Programming languages
        "python", "java", "javascript", "typescript", "ruby", "scala",
        "go", "golang", "rust", "swift", "kotlin", "perl", "php",
        "c", "c++", "c#", "r", "dart", "lua", "julia", "elixir",
        "erlang", "clojure", "haskell", "f#", "ocaml", "matlab",
        "sas", "vba", "fortran", "cobol", "abap", "groovy",
        # Frameworks / runtimes
        "django", "flask", "fastapi", "spring", "spring boot",
        ".net", "asp.net", "react", "react native", "angular",
        "vue", "vue.js", "svelte", "ember", "jquery", "bootstrap",
        "tailwind", "tailwind css", "node", "node.js", "nodejs",
        "express", "express.js", "nestjs", "next.js", "nextjs",
        "nuxt", "rails", "ruby on rails", "laravel", "symfony",
        "codeigniter", "hibernate", "struts", "junit", "pytest",
        "mocha", "jest", "cypress", "selenium", "playwright",
        # Databases
        "postgresql", "postgres", "mysql", "mariadb", "mongodb",
        "redis", "cassandra", "elasticsearch", "oracle", "sql server",
        "sqlite", "dynamodb", "neo4j", "couchbase", "firebase",
        "supabase", "bigquery",
        # Cloud / DevOps
        "aws", "amazon web services", "azure", "microsoft azure",
        "gcp", "google cloud", "google cloud platform", "kubernetes",
        "k8s", "docker", "podman", "jenkins", "terraform", "ansible",
        "puppet", "chef", "gitlab", "github", "bitbucket", "circleci",
        "travis", "prometheus", "grafana", "splunk", "datadog",
        "new relic",
        # Data / ML
        "tensorflow", "pytorch", "keras", "scikit-learn", "numpy",
        "pandas", "scipy", "matplotlib", "seaborn", "plotly",
        "jupyter", "airflow", "kafka", "rabbitmq", "spark",
        "apache spark", "hadoop", "hive", "pig", "snowflake",
        "databricks", "power bi", "tableau", "looker", "dbt",
        "fivetran", "kibana", "logstash",
        # Misc tools / OS
        "linux", "ubuntu", "debian", "centos", "fedora", "windows",
        "macos", "android", "ios", "git", "svn", "mercurial",
        "jira", "confluence", "slack", "teams", "intellij",
        "eclipse", "vscode", "visual studio", "pycharm", "vim",
        "emacs", "nginx", "apache", "tomcat",
        # Tech acronyms (commonly NER-tagged as ORG by spaCy)
        "oop", "ood", "mvc", "mvp", "mvvm", "tdd", "bdd", "ddd",
        "crud", "rest", "soap", "grpc", "graphql", "ci/cd",
    }
)


class NerDisambiguationFilter:
    """Drop skill matches that overlap a 'real' proper noun NER entity.

    Parameters
    ----------
    tech_whitelist
        Lower-cased surface forms exempted from the filter. Defaults
        to a curated tech-vocabulary set; extend if domain-specific
        terminology is producing false negatives.
    """

    DROP_LABELS: ClassVar[frozenset[str]] = frozenset(
        {"ORG", "GPE", "LOC", "PERSON", "FAC", "NORP"}
    )

    def __init__(
        self, tech_whitelist: frozenset[str] | None = None
    ) -> None:
        self._whitelist = (
            tech_whitelist
            if tech_whitelist is not None
            else _DEFAULT_TECH_WHITELIST
        )

    @property
    def tech_whitelist(self) -> frozenset[str]:
        return self._whitelist

    def is_misclassified_proper_noun(
        self,
        *,
        text: str,
        entities: list[EntitySpan],
        match_start: int,
        match_end: int,
        section: SectionLabel,
    ) -> bool:
        """Return True if the match should be DROPPED.

        Rules in order:

        1. Inside the ``"skills"`` section — never drop. NER is
           unreliable on dense skill listings.
        2. If the surface form is in the tech whitelist — never drop.
        3. Otherwise, if the match span overlaps any entity with a
           label in :attr:`DROP_LABELS` — drop.

        Note: ``"languages"`` section is treated like any other
        non-skills section. NER tagging language names as ``LOC`` /
        ``GPE`` (``"English"``, ``"French"``) is likely correct in CV
        context but the surface form is a known whitelist member, so
        the language entries get kept anyway via rule 2.
        """
        if section == "skills":
            return False

        surface = text[match_start:match_end].lower().strip()
        if surface in self._whitelist:
            return False

        # Linear scan — at typical CV scale (~50 entities, ~100 matches)
        # this is fine. If we ever benchmark this as a hot spot, sort
        # entities and binary-search.
        for ent in entities:
            if ent.label not in self.DROP_LABELS:
                continue
            # Half-open overlap test.
            if ent.start_char < match_end and ent.end_char > match_start:
                return True
        return False
