"""Separate FastAPI router for web scheme discovery.

Mounted independently as /api/web-schemes — never touches /api/recommend.
All failures degrade to status="partial"; the router never raises 500 for
Tavily outages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.web_scheme_discovery.schemas import (
    WebDiscoveryProfile,
    WebSchemeSearchResponse,
)
from services.web_scheme_discovery.service import get_discovery_service

logger = logging.getLogger("yojnasathi.web_discovery.routes")

web_scheme_router = APIRouter(prefix="/api/web-schemes", tags=["Web Scheme Discovery"])


class WebSchemeSearchBody(BaseModel):
    model_config = {"extra": "ignore"}

    profile: WebDiscoveryProfile = Field(default_factory=WebDiscoveryProfile)
    max_candidates: int | None = None


@web_scheme_router.post("/search", response_model=WebSchemeSearchResponse)
def web_scheme_search_endpoint(body: WebSchemeSearchBody) -> WebSchemeSearchResponse:
    """Discover candidate government schemes on the web for a profile."""
    service = get_discovery_service()
    try:
        return service.discover(body.profile, max_candidates=body.max_candidates)
    except Exception as exc:  # pragma: no cover - absolute guard
        logger.exception("Unexpected web discovery failure")
        from services.web_scheme_discovery.schemas import SearchMetadata

        return WebSchemeSearchResponse(
            status="partial",
            query_summary="Web discovery temporarily unavailable.",
            validated_schemes=[],
            rejected_candidates=[],
            metadata=SearchMetadata(),
            errors=["Web discovery temporarily unavailable"],
        )


@web_scheme_router.get("/health")
def web_scheme_health() -> Dict[str, Any]:
    """Liveness probe that never requires an API key."""
    import os

    return {
        "status": "ok",
        "service": "web-scheme-discovery",
        "tavily_configured": bool((os.environ.get("TAVILY_API_KEY") or "").strip()),
    }
