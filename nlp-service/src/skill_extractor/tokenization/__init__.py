"""Text preprocessing utilities for the skill extraction pipeline.

Submodules
----------
* :mod:`skill_extractor.tokenization.slash_segmenter` — splits slash-
  joined skill tokens (``C/C++``, ``HTML/CSS``) into individual tokens
  so the PhraseMatcher can match each side independently. Critical for
  Romanian-style CVs that habitually write enumerations with slashes.
"""
