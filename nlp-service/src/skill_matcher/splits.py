"""Pure split / stratification helpers shared by the build script and tests.

These functions deliberately live outside :mod:`scripts.build_training_dataset`
so the fast unit-test layer can exercise them without pulling in
Module 1 (``cv_extractor``) and Module 2 (``skill_extractor``) — the
heavy NLP imports the build script does at module load time.

Both functions are deterministic given a seeded :class:`random.Random`
instance.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict


def stratified_split(
    cv_ids: list[str],
    cv_to_category: dict[str, str],
    val_fraction: float,
    rng: random.Random,
) -> tuple[set[str], set[str]]:
    """Stratified train/val partition of ``cv_ids`` by category.

    Within each category, the input list is sorted (for determinism)
    then shuffled with the supplied seeded ``rng`` and split into a
    ``val_fraction``-sized validation slice and a complementary
    training slice.

    Categories with fewer than 2 CVs are placed entirely in the
    training set: we cannot afford to strip away the only positive
    sample from a thinly-represented category.

    Parameters
    ----------
    cv_ids
        Identifiers of every CV that should be partitioned.
    cv_to_category
        Maps each CV id to its stratification key (typically the
        dominant ESCO L2 category for that CV). CVs missing from the
        map are bucketed under ``"__no_skills__"``.
    val_fraction
        Target fraction of validation samples per category. Clamped
        to at least one CV per ≥2-CV category.
    rng
        Pre-seeded :class:`random.Random`. The function does not
        re-seed it — share one ``Random(seed)`` across the whole
        build for determinism.

    Returns
    -------
    tuple[set[str], set[str]]
        ``(train_ids, val_ids)``. Disjoint; their union equals
        ``set(cv_ids)``.
    """
    by_category: dict[str, list[str]] = defaultdict(list)
    for cv_id in cv_ids:
        by_category[cv_to_category.get(cv_id, "__no_skills__")].append(cv_id)

    train: set[str] = set()
    val: set[str] = set()

    for category in sorted(by_category):
        members = sorted(by_category[category])
        rng.shuffle(members)
        if len(members) < 2:
            train.update(members)
            continue
        n_val = max(1, int(len(members) * val_fraction))
        val.update(members[:n_val])
        train.update(members[n_val:])

    return train, val


def dominant_category(
    skill_uris: list[str],
    uri_to_category: dict[str, str],
    fallback: str = "__no_skills__",
) -> str:
    """Return the category with the most matches across ``skill_uris``.

    Used by the build script to assign a stratification key to every
    surviving CV. Pulled out of the build script so the test layer
    can exercise it without importing Module 1/2.

    Ties are broken by lexicographic order so the answer is
    deterministic.

    Parameters
    ----------
    skill_uris
        List of ESCO/``CUST:`` URIs (one per Module-2 ``SkillMatch``).
    uri_to_category
        Maps each URI to its broader category (typically the L2
        ancestor produced by :func:`skill_matcher.data.category_map
        .build_category_map`).
    fallback
        Returned when no URI in ``skill_uris`` has a mapped category.
        Defaults to ``"__no_skills__"``.
    """
    counts: Counter[str] = Counter()
    for uri in skill_uris:
        ancestor = uri_to_category.get(uri, "")
        if ancestor:
            counts[ancestor] += 1
    if not counts:
        return fallback
    return min(counts.most_common(), key=lambda kv: (-kv[1], kv[0]))[0]


__all__ = ["dominant_category", "stratified_split"]
