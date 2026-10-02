"""Patch-round overlays applied on top of the bare ESCO bundle.

This package contains three independent overlays added in May 2026 to
raise Module 2's recall and precision without touching the underlying
PhraseMatcher implementation:

* :mod:`skill_extractor.overlays.aliases` — extra surface forms attached
  to existing ESCO concepts (``tech_aliases.yaml``).
* :mod:`skill_extractor.overlays.custom` — entirely new "custom"
  concepts not present in ESCO at all (``custom_concepts.json``).
* :mod:`skill_extractor.overlays.suppression` — post-match drop rules
  for known ESCO false-positive families (``suppression_rules.yaml``).

Each overlay is independently toggleable via
:class:`~skill_extractor.config.SkillExtractorConfig` flags so the
validation report can break the delta down per overlay.
"""
