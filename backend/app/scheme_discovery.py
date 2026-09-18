import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.matching import match_schemes
from app.schemas import CitizenProfile, Scheme, SchemeMatchResult

logger = logging.getLogger("yojnasathi.discovery")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"


def load_curated_schemes() -> List[Scheme]:
    """Load and parse curated schemes baseline from schemes.json."""
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw_schemes = json.load(f)
    return [Scheme(**item) for item in raw_schemes]


def _merge_scheme_pools(primary: List[Scheme], secondary: List[Scheme]) -> List[Scheme]:
    """Union two candidate pools by scheme id, preserving primary order first."""
    merged = list(primary)
    seen_ids = {s.id.lower() for s in merged}
    for scheme in secondary:
        if scheme.id.lower() in seen_ids:
            continue
        seen_ids.add(scheme.id.lower())
        merged.append(scheme)
    return merged


def get_candidate_schemes_pool(
    profile: CitizenProfile,
    category: Optional[str] = None,
    curated_schemes: Optional[List[Scheme]] = None,
) -> Tuple[List[Scheme], Dict[str, Any]]:
    """
    Build the unified candidate scheme pool for a citizen profile:
    curated catalogue baseline + live MahaDBT discovery (for Maharashtra citizens)
    + validated web discovery (Tavily cache/live).

    Guarded so that any live discovery failure falls back safely to curated schemes.
    """
    if curated_schemes is None:
        curated_schemes = load_curated_schemes()

    candidate_schemes: List[Scheme] = list(curated_schemes)
    discovery_meta: Dict[str, Any] = {}

    # 1. Validated Web Scheme Discovery (Tavily)
    try:
        from services.web_scheme_discovery.merger import (
            build_live_scheme_pool,
            get_cached_web_schemes,
            perform_live_discovery,
        )

        cached = get_cached_web_schemes(profile, category=category)
        if cached:
            usable_discoveries = cached
        else:
            usable_discoveries = perform_live_discovery(profile, category=category)

        if usable_discoveries:
            live_pool, live_meta = build_live_scheme_pool(
                curated_schemes=curated_schemes,
                discovered_schemes=usable_discoveries,
                fallback_category=category,
            )
            if live_pool:
                candidate_schemes = live_pool
                discovery_meta = dict(live_meta)
            else:
                logger.info("Live discovery returned no active schemes; using curated baseline")
    except Exception as exc:
        logger.warning("Web scheme discovery/merger failed, falling back to curated: %s", exc)

    # 2. Real-time Maharashtra government scheme discovery from official MahaDBT portal
    if profile.state and str(profile.state).strip().lower() == "maharashtra":
        try:
            from services.maharashtra_schemes.service import get_maharashtra_schemes
            from services.web_scheme_discovery.merger import build_live_scheme_pool

            maharashtra_discovered = get_maharashtra_schemes()
            if maharashtra_discovered:
                maharashtra_pool, maharashtra_meta = build_live_scheme_pool(
                    curated_schemes=curated_schemes,
                    discovered_schemes=maharashtra_discovered,
                    fallback_category=category,
                )
                if maharashtra_pool:
                    candidate_schemes = _merge_scheme_pools(candidate_schemes, maharashtra_pool)
                    discovery_meta.update(maharashtra_meta)
        except Exception as exc:
            logger.warning("Maharashtra scheme discovery failed, using curated baseline: %s", exc)

    return candidate_schemes, discovery_meta


def discover_and_match_schemes(
    profile: CitizenProfile,
    category: Optional[str] = None,
    curated_schemes: Optional[List[Scheme]] = None,
) -> Tuple[List[SchemeMatchResult], List[Scheme], Dict[str, Any]]:
    """
    Unified scheme discovery and deterministic matching pipeline.
    Used by both /api/recommend and VoiceAgent.
    """
    candidate_schemes, discovery_meta = get_candidate_schemes_pool(
        profile=profile,
        category=category,
        curated_schemes=curated_schemes,
    )

    results = match_schemes(profile, candidate_schemes, category=category)

    # Attach discovery provenance metadata to web-discovered match results
    if discovery_meta:
        for result in results:
            meta = discovery_meta.get(result.scheme.id)
            if meta:
                result.is_web_discovered = True
                result.discovery_confidence = getattr(meta, "confidence", None)
                result.discovery_source_type = getattr(meta, "source_type", None)
                result.validation_reasons = getattr(meta, "validation_reasons", [])

    return results, candidate_schemes, discovery_meta
