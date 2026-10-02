"""Symbolic filters that reject likely false-positive matches.

Two filters are supplied:

* :mod:`skill_extractor.filters.negation` — drops matches preceded by a
  negation pattern (``"no experience with X"``, ``"nu am lucrat cu X"``).
* :mod:`skill_extractor.filters.disambiguation` — drops matches whose
  span is tagged by spaCy NER as ``ORG`` / ``GPE`` / ``LOC`` / ``PERSON``
  outside the ``"skills"`` section, where such overlaps almost always
  indicate the surface form is a proper noun, not a skill.
"""
