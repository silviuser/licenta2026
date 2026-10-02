"""ESCO category-map loader for hard-negative mining.

This helper consumes two CSV files from the ESCO v1.2.1 bundle:

* ``broaderRelationsSkillPillar_en.csv`` — direct ``(conceptUri,
  broaderUri)`` parent edges, including transitive edges up to the
  ISCED-F roots.
* ``skillsHierarchy_en.csv`` — denormalised view giving every leaf
  skill its Level 0/1/2/3 ancestors. We use this to compute the
  **L2-ancestor** of every leaf URI, which the hard-negative miner
  uses as the "same category" boundary.

Why L2 ancestors specifically
-----------------------------
L0 / L1 are too broad (``"skills"`` covers everything). L3 is often a
single leaf, so siblings would be scarce. L2 corresponds to clusters
like *"computer programming"* or *"databases"* — fine-grained enough
that a sibling is a credible distractor but populous enough that a
sibling almost always exists.

Custom ``CUST:`` concepts (from Module 2's custom overlay) are not in
the ESCO hierarchy. The loader assigns every ``CUST:`` URI to the
synthetic L2 ancestor ``"CUST:__category_root__"``; the miner will
return *any other* ``CUST:`` URI as a sibling. That is rough but it
yields a tighter negative than ``random_in_corpus`` and is the only
viable answer without re-classifying the custom overlay (out of scope
for Step 3).

This module is **stdlib + pydantic only** — no torch, no
sentence-transformers. It is safe to import in unit tests and at CLI
startup.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# CSV file names — kept as constants so the loader stays declarative
# ---------------------------------------------------------------------------

_HIERARCHY_FILE = "skillsHierarchy_en.csv"
_BROADER_FILE = "broaderRelationsSkillPillar_en.csv"

# Sentinel used as the "L2 ancestor" of custom (``CUST:...``) URIs. The
# miner treats every URI with this ancestor as siblings of every other
# such URI — see module docstring for the rationale.
CUSTOM_CATEGORY_ROOT = "CUST:__category_root__"


# ---------------------------------------------------------------------------
# Public model
# ---------------------------------------------------------------------------


class EscoCategoryMap(BaseModel):
    """Bidirectional view of the ESCO category structure.

    Built once at CLI startup; thereafter all lookups are O(1).

    Attributes
    ----------
    uri_to_l2
        Maps every leaf ESCO URI (and every custom ``CUST:`` URI) to
        its L2 ancestor URI. Missing URIs (e.g. an ESCO concept that
        does not appear in the denormalised hierarchy file) map to the
        empty string ``""`` so callers can filter them out without
        special-casing ``None``.
    l2_to_children
        Inverse of :attr:`uri_to_l2`: maps each L2 ancestor URI to a
        sorted list of every leaf URI under it. Sorted for
        determinism: the miner's random sibling pick uses a seeded
        :class:`random.Random` over a deterministic list, not an
        unordered set, so re-runs are reproducible.
    """

    uri_to_l2: dict[str, str] = Field(default_factory=dict)
    l2_to_children: dict[str, list[str]] = Field(default_factory=dict)

    def siblings(self, uri: str) -> list[str]:
        """Return all sibling URIs under the same L2 ancestor.

        The result **excludes** ``uri`` itself but is otherwise a copy
        of :attr:`l2_to_children` for that ancestor. Returns an empty
        list if the URI has no known ancestor or its L2 bucket
        contains only itself.
        """
        ancestor = self.uri_to_l2.get(uri, "")
        if not ancestor:
            return []
        children = self.l2_to_children.get(ancestor, [])
        return [c for c in children if c != uri]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _HierarchyRow:
    """One row from ``skillsHierarchy_en.csv``."""

    level_0_uri: str
    level_1_uri: str
    level_2_uri: str
    level_3_uri: str


def _read_hierarchy(path: Path) -> Iterable[_HierarchyRow]:
    """Stream ``skillsHierarchy_en.csv`` row by row.

    The file is small (~3k rows) so streaming is a stylistic choice
    rather than a memory one; the iterator interface keeps the public
    builder tidy.
    """
    if not path.exists():
        raise FileNotFoundError(f"ESCO hierarchy file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            yield _HierarchyRow(
                level_0_uri=(row.get("Level 0 URI") or "").strip(),
                level_1_uri=(row.get("Level 1 URI") or "").strip(),
                level_2_uri=(row.get("Level 2 URI") or "").strip(),
                level_3_uri=(row.get("Level 3 URI") or "").strip(),
            )


def _read_broader_edges(path: Path) -> dict[str, str]:
    """Read ``broaderRelationsSkillPillar_en.csv`` into a child→parent map.

    The CSV contains one row per direct edge. We collapse to the first
    parent observed for each child — the file does not encode
    multi-parent relationships for SKOS skills (DAG, not a tree, but
    with a single canonical parent per concept in this bundle).
    """
    if not path.exists():
        raise FileNotFoundError(f"ESCO broader-relations file not found: {path}")
    edges: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            child = (row.get("conceptUri") or "").strip()
            parent = (row.get("broaderUri") or "").strip()
            if not child or not parent:
                continue
            # First-write-wins keeps the loader deterministic across runs.
            edges.setdefault(child, parent)
    return edges


def _resolve_l2_ancestor(
    uri: str,
    direct_parent: dict[str, str],
    hierarchy_l2: dict[str, str],
) -> str:
    """Resolve the L2 ancestor URI for a single leaf skill.

    Strategy:

    1. If the URI appears in the denormalised hierarchy as a leaf
       (i.e. it has an explicit ``Level 2 URI`` column), use that.
    2. Otherwise walk up the ``direct_parent`` chain until we land on
       a URI we know is an L2 (i.e. one that appears as a Level 2 URI
       value somewhere in the hierarchy). Bound the walk to 10 steps
       — every ESCO concept reaches the root in ≤6 hops in practice.
    3. If neither path resolves, return ``""``.
    """
    if uri in hierarchy_l2:
        return hierarchy_l2[uri]

    seen: set[str] = set()
    current = uri
    for _ in range(10):
        parent = direct_parent.get(current, "")
        if not parent or parent in seen:
            break
        seen.add(parent)
        # If this parent is itself an L2 (appears as a Level 2 URI in
        # the hierarchy) we are done.
        if parent in hierarchy_l2.values():
            return parent
        current = parent
    return ""


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_category_map(
    esco_dir: Path,
    custom_uris: Iterable[str] = (),
) -> EscoCategoryMap:
    """Build an :class:`EscoCategoryMap` from the ESCO CSV bundle.

    Parameters
    ----------
    esco_dir
        Directory containing ``skillsHierarchy_en.csv`` and
        ``broaderRelationsSkillPillar_en.csv``. This is the same
        directory Module 2's :class:`~skill_extractor.esco.loader
        .EscoLoader` reads from (``SkillExtractorConfig.esco_dir``).
    custom_uris
        Iterable of ``CUST:...`` URIs from Module 2's custom overlay.
        All of them are bucketed under the synthetic ancestor
        :data:`CUSTOM_CATEGORY_ROOT`. Pass an empty iterable to skip
        this if your build excludes the custom overlay.

    Returns
    -------
    EscoCategoryMap
        Built map. Side effect: emits one ``logger.info`` entry with
        coverage counts so the build report can quote them.
    """
    hierarchy_path = esco_dir / _HIERARCHY_FILE
    broader_path = esco_dir / _BROADER_FILE

    # Pass 1 — read the hierarchy file. For every row, the leaf URI is
    # whichever of Level 0/1/2/3 URIs is the rightmost populated one.
    # We map "explicit L2-or-deeper leaves" directly to their L2 ancestor.
    hierarchy_leaf_to_l2: dict[str, str] = {}
    for row in _read_hierarchy(hierarchy_path):
        if row.level_3_uri:
            leaf = row.level_3_uri
        elif row.level_2_uri:
            leaf = row.level_2_uri
        elif row.level_1_uri:
            leaf = row.level_1_uri
        else:
            leaf = row.level_0_uri
        if not leaf:
            continue
        # The "ancestor" for a leaf that lives at Level 2 itself is
        # still itself — we want sibling-finding to work on leaves
        # that sit at the L2 layer too.
        ancestor = row.level_2_uri or row.level_1_uri or row.level_0_uri
        if leaf and ancestor:
            hierarchy_leaf_to_l2.setdefault(leaf, ancestor)

    # Pass 2 — read direct parent edges to back-fill leaves that the
    # denormalised hierarchy file misses (this is rare but happens for
    # very recent concepts).
    direct_parent = _read_broader_edges(broader_path)

    uri_to_l2: dict[str, str] = dict(hierarchy_leaf_to_l2)
    for uri in direct_parent:
        if uri in uri_to_l2:
            continue
        resolved = _resolve_l2_ancestor(uri, direct_parent, hierarchy_leaf_to_l2)
        if resolved:
            uri_to_l2[uri] = resolved

    # Bucket custom URIs under the synthetic root.
    custom_list = sorted(set(custom_uris))
    for cust in custom_list:
        uri_to_l2[cust] = CUSTOM_CATEGORY_ROOT

    # Build the inverse map, sorted for determinism.
    l2_to_children: dict[str, list[str]] = {}
    for uri, ancestor in uri_to_l2.items():
        l2_to_children.setdefault(ancestor, []).append(uri)
    for ancestor in l2_to_children:
        l2_to_children[ancestor].sort()

    logger.info(
        "category_map.built",
        total_leaves=len(uri_to_l2),
        l2_categories=len(l2_to_children),
        custom_count=len(custom_list),
    )

    return EscoCategoryMap(
        uri_to_l2=uri_to_l2,
        l2_to_children=l2_to_children,
    )


__all__ = [
    "CUSTOM_CATEGORY_ROOT",
    "EscoCategoryMap",
    "build_category_map",
]
