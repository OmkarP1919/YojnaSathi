"""Orchestrating service: DISCOVERY -> EXTRACTION -> VALIDATION -> OUTPUT.

Public interface for the future merger (do NOT implement the merger here):

    discover_web_schemes(profile) -> WebSchemeSearchResponse

Failure policy: Tavily problems degrade to status="partial" with errors
listed; the exception never propagates to the main app.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from services.web_scheme_discovery.cache import get_shared_cache, profile_cache_key
from services.web_scheme_discovery.deduplicator import deduplicate
from services.web_scheme_discovery.exceptions import (
    MissingApiKeyError,
    TavilyAPIError,
    WebDiscoveryError,
)
from services.web_scheme_discovery.extractor import extract_candidates
from services.web_scheme_discovery.schemas import (
    DiscoveredScheme,
    SearchMetadata,
    WebDiscoveryProfile,
    WebSchemeSearchResponse,
)
from services.web_scheme_discovery.tavily_search import (
    TavilyClient,
    build_search_queries,
    get_tavily_defaults,
)
from services.web_scheme_discovery.validator import apply_validation

logger = logging.getLogger("yojnasathi.web_discovery.service")

SAFETY_NOTE = (
    "These web-discovered schemes may be relevant based on published criteria. "
    "Final eligibility is determined solely by the relevant government authority."
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


def get_service_config() -> Dict[str, Any]:
    tavily_defaults = get_tavily_defaults()
    return {
        "max_results_per_query": tavily_defaults["max_results"],
        "search_depth": tavily_defaults["search_depth"],
        "max_candidates": _env_int("WEB_SCHEME_MAX_CANDIDATES", 15),
        "cache_ttl": _env_int("WEB_SCHEME_CACHE_TTL", 3600),
        "validation_timeout": _env_int("WEB_SCHEME_VALIDATION_TIMEOUT", 10),
        "max_queries": 6,
    }


class WebSchemeDiscoveryService:
    def __init__(self, tavily_client: Optional[TavilyClient] = None):
        self.tavily_client = tavily_client or TavilyClient()

    def discover(
        self,
        profile: WebDiscoveryProfile | Dict[str, Any],
        max_candidates: Optional[int] = None,
    ) -> WebSchemeSearchResponse:
        started = time.time()
        if isinstance(profile, dict):
            profile = WebDiscoveryProfile.model_validate(profile)
        config = get_service_config()
        limit = max(1, min(max_candidates or config["max_candidates"], 30))

        cache = get_shared_cache(config["cache_ttl"])
        cache_key = profile_cache_key(profile.model_dump(), str(limit))
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info("Web discovery cache hit")
            if isinstance(cached, WebSchemeSearchResponse):
                cached.metadata.cache_hit = True
                return cached

        queries = build_search_queries(profile)[: config["max_queries"]]
        query_summary = (
            f"Web discovery for {profile.state or 'India'} / "
            f"{profile.specific_need or profile.need or 'welfare'} "
            f"({len(queries)} targeted queries)"
        )
        errors: List[str] = []
        all_items = []
        try:
            for query in queries:
                try:
                    items = self.tavily_client.search(
                        query,
                        max_results=config["max_results_per_query"],
                        search_depth=config["search_depth"],
                    )
                    all_items.extend(items)
                except (MissingApiKeyError, TavilyAPIError) as exc:
                    logger.warning("Tavily query failed: %s", type(exc).__name__)
                    errors.append("Web discovery temporarily unavailable")
                    break
        except WebDiscoveryError as exc:
            errors.append("Web discovery temporarily unavailable")
            logger.warning("Web discovery failed: %s", exc)

        if errors and not all_items:
            metadata = SearchMetadata(
                queries_used=len(queries),
                queries=queries,
                elapsed_seconds=round(time.time() - started, 3),
            )
            return WebSchemeSearchResponse(
                status="partial",
                query_summary=query_summary,
                validated_schemes=[],
                rejected_candidates=[],
                metadata=metadata,
                errors=errors,
            )

        candidates = extract_candidates(all_items)
        candidates = deduplicate(candidates)[:limit]

        validated: List[DiscoveredScheme] = []
        rejected: List[DiscoveredScheme] = []
        for cand in candidates:
            apply_validation(cand)
            # MVP rule: validated list = verified AND active only.
            if cand.validation_status == "verified" and cand.active_status == "active":
                validated.append(cand)
            else:
                rejected.append(cand)

        elapsed = round(time.time() - started, 3)
        status = "success"
        if errors:
            status = "partial"
        elif not validated and not rejected:
            status = "empty"
        metadata = SearchMetadata(
            queries_used=len(queries),
            queries=queries,
            candidates_found=len(candidates),
            candidates_validated=len(validated),
            candidates_rejected=len(rejected),
            elapsed_seconds=elapsed,
        )
        logger.info(
            "Web discovery done: queries=%d candidates=%d validated=%d rejected=%d elapsed=%.2fs",
            len(queries),
            len(candidates),
            len(validated),
            len(rejected),
            elapsed,
        )
        response = WebSchemeSearchResponse(
            status=status,  # type: ignore[arg-type]
            query_summary=f"{query_summary}. {SAFETY_NOTE}",
            validated_schemes=validated,
            rejected_candidates=rejected,
            metadata=metadata,
            errors=errors,
        )
        cache.set(cache_key, response)
        return response


_service_singleton: Optional[WebSchemeDiscoveryService] = None


def get_discovery_service() -> WebSchemeDiscoveryService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = WebSchemeDiscoveryService()
    return _service_singleton


def discover_web_schemes(
    profile: WebDiscoveryProfile | Dict[str, Any],
    max_candidates: Optional[int] = None,
) -> WebSchemeSearchResponse:
    """Clean merger-ready interface (no Tavily knowledge required)."""
    return get_discovery_service().discover(profile, max_candidates=max_candidates)
