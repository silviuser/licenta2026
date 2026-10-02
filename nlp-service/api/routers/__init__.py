"""API routers — one module per HTTP resource.

Each router is mounted under ``/v1`` from ``api.main.create_app``;
the path inside each module is the resource segment only (e.g.
``/health`` becomes ``/v1/health``).
"""

from api.routers.extract import router as extract_router
from api.routers.extract_jd import router as extract_jd_router
from api.routers.full import router as full_router
from api.routers.health import router as health_router
from api.routers.info import router as info_router
from api.routers.match import router as match_router

__all__ = [
    "extract_jd_router",
    "extract_router",
    "full_router",
    "health_router",
    "info_router",
    "match_router",
]
