"""``GET /v1/info`` — service identity, versions and provenance.

The brief calls out the placeholder-encoder caveat: the API must
surface the loaded encoder identity + a free-text disclaimer about
the Step 5 placeholder so consumers can correlate scores with the
encoder generation that produced them. When the Step 5 redo lands
and the placeholder is replaced, the disclaimer becomes a no-op
(consider replacing it with an empty string at that point — for now
it is informative).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request

import cv_extractor
import skill_extractor
import skill_matcher
from skill_matcher.esco_index import compute_model_sha

from api import __version__ as nlp_service_version
from api.deps import get_skill_matcher
from api.schemas import InfoResponse

router = APIRouter()


_PLACEHOLDER_CAVEAT = (
    "The currently-loaded encoder is the Step 5 placeholder. Numbers "
    "reflect a structurally-complete pipeline at a compressed score "
    "range; re-calibration via scripts/tune_thresholds.py after the "
    "Step 5 redo will shift all thresholds upward and widen the "
    "score distribution. See reports/module3_final_validation_"
    "20260517.md for the operating-point context."
)


def _compute_esco_sha_if_missing(request: Request) -> str:
    """Return the 12-char ESCO SHA from app.state or compute it cold.

    The lifespan startup branch pre-computes the SHA when
    ``warmup_on_startup=True``; this helper covers the lazy path.
    """
    api_state = getattr(request.app.state, "api_state", None)
    cached_raw = getattr(api_state, "esco_sha", None) if api_state else None
    if isinstance(cached_raw, str) and cached_raw:
        return cached_raw

    from skill_matcher.esco_loader import compute_esco_sha, load_esco_concepts

    sha: str = compute_esco_sha(load_esco_concepts())[:12]
    if api_state is not None:
        api_state.esco_sha = sha
    return sha


@router.get(
    "/info",
    response_model=InfoResponse,
    summary="Service identity, versions and provenance",
    description=(
        "Returns the API version, all three module versions, the "
        "loaded encoder identity, the 12-char ESCO SHA, the Step 8 "
        "locked thresholds, and the placeholder-encoder caveat."
    ),
)
def info(
    request: Request,
    matcher: skill_matcher.SkillMatcher = Depends(get_skill_matcher),
) -> InfoResponse:
    """Service identity. Triggers Module 3 lazy-load on first call."""
    # Lazy-load the matcher's encoder + index so we can report the
    # resolved encoder path. Without this, on a cold cache the
    # encoder_path would be ``None`` until the first ``/v1/extract``.
    matcher._ensure_ready()  # noqa: SLF001 — Step 10 known coupling.

    encoder_path = matcher._resolved_model_name or matcher.config.base_model  # noqa: SLF001
    encoder_sha = compute_model_sha(
        model_name=encoder_path,
        finetuned_model_path=(
            Path(matcher.config.finetuned_model_path)
            if matcher.config.finetuned_model_path
            else None
        ),
    )
    esco_sha = _compute_esco_sha_if_missing(request)

    cfg = matcher.config
    locked_thresholds = {
        "drop_threshold": cfg.drop_threshold,
        "keep_threshold": cfg.keep_threshold,
        "expansion_threshold": cfg.expansion_threshold,
        "per_requirement_keep_threshold": cfg.per_requirement_keep_threshold,
        "required_weight": cfg.required_weight,
        "t1_strong_threshold": cfg.t1_strong_threshold,
        "t2_possible_threshold": cfg.t2_possible_threshold,
    }

    return InfoResponse(
        nlp_service_version=nlp_service_version,
        skill_matcher_version=skill_matcher.__version__,
        skill_extractor_version=skill_extractor.__version__,
        cv_extractor_version=cv_extractor.__version__,
        encoder_path=encoder_path,
        encoder_sha=encoder_sha,
        esco_sha=esco_sha,
        locked_thresholds=locked_thresholds,
        placeholder_caveat=_PLACEHOLDER_CAVEAT,
    )


__all__ = ["router"]
