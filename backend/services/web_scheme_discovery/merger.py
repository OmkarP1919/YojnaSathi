"""Merger layer: manages live-first web scheme discovery, caching, and candidate pools.

The canonical matcher (match_schemes) remains authoritative.
Curated schemes take absolute precedence for duplicates and serve as the reliability fallback.
Only validated ('verified') and active ('active') discovered schemes are used.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import ValidationError

from app.schemas import CitizenProfile, Scheme
from services.web_scheme_discovery.adapter import discovered_to_canonical_scheme
from services.web_scheme_discovery.cache import get_shared_cache, profile_cache_key
from services.web_scheme_discovery.deduplicator import (
    find_duplicate_curated_scheme,
    is_duplicate_of_curated,
)
from services.web_scheme_discovery.schemas import (
    DiscoveredScheme,
    DiscoveryMetadata,
    WebDiscoveryProfile,
    WebSchemeSearchResponse,
)
from services.web_scheme_discovery.service import (
    get_discovery_service,
    get_service_config,
)

logger = logging.getLogger("yojnasathi.web_discovery.merger")


def citizen_to_web_profile(
    profile: Union[CitizenProfile, WebDiscoveryProfile, Dict[str, Any]],
    category: Optional[str] = None,
) -> WebDiscoveryProfile:
    """Convert CitizenProfile or dict to standard WebDiscoveryProfile."""
    if isinstance(profile, WebDiscoveryProfile):
        return profile

    if isinstance(profile, dict):
        p_dict = profile
    elif isinstance(profile, CitizenProfile):
        p_dict = profile.model_dump()
    else:
        p_dict = {}

    state = p_dict.get("state")
    district = p_dict.get("district")
    age = p_dict.get("age")
    gender = p_dict.get("gender")
    occupation = p_dict.get("occupation")
    farmer = p_dict.get("farmer") if p_dict.get("farmer") is not None else p_dict.get("is_farmer")
    student = p_dict.get("student") if p_dict.get("student") is not None else p_dict.get("is_student")
    annual_income = p_dict.get("annual_income")
    social_category = p_dict.get("social_category")
    disability = p_dict.get("disability")
    specific_need = p_dict.get("specific_need")

    needs = p_dict.get("needs") or []
    explicit_need = p_dict.get("need")
    raw_need = explicit_need or (needs[0] if needs and isinstance(needs, list) else None) or category
    need = raw_need.replace("_", " ").strip() if raw_need else None
    if specific_need:
        specific_need = specific_need.replace("_", " ").strip()

    return WebDiscoveryProfile(
        state=state,
        district=district,
        age=age,
        gender=gender,
        occupation=occupation,
        farmer=farmer,
        student=student,
        annual_income=annual_income,
        social_category=social_category,
        disability=disability,
        need=need,
        specific_need=specific_need,
    )


def _build_web_profiles_to_check(
    profile: Union[CitizenProfile, WebDiscoveryProfile, Dict[str, Any]],
    category: Optional[str] = None,
) -> List[WebDiscoveryProfile]:
    """Generate candidate WebDiscoveryProfiles to query the shared cache."""
    if isinstance(profile, WebDiscoveryProfile):
        return [profile]

    primary = citizen_to_web_profile(profile, category=category)

    if isinstance(profile, dict):
        p_dict = profile
    elif isinstance(profile, CitizenProfile):
        p_dict = profile.model_dump()
    else:
        p_dict = {}

    needs = p_dict.get("needs") or []
    explicit_need = p_dict.get("need")

    need_candidates = [primary.need, explicit_need]
    if needs and isinstance(needs, list) and needs[0] not in need_candidates:
        need_candidates.append(needs[0])
    if category and category not in need_candidates:
        need_candidates.append(category)

    profiles: List[WebDiscoveryProfile] = []
    seen_hashes: Set[str] = set()

    for cand_need in need_candidates:
        wp = WebDiscoveryProfile(
            state=primary.state,
            district=primary.district,
            age=primary.age,
            gender=primary.gender,
            occupation=primary.occupation,
            farmer=primary.farmer,
            student=primary.student,
            annual_income=primary.annual_income,
            social_category=primary.social_category,
            disability=primary.disability,
            need=cand_need,
            specific_need=primary.specific_need,
        )
        h = str(wp.model_dump())
        if h not in seen_hashes:
            seen_hashes.add(h)
            profiles.append(wp)

    return profiles


def get_cached_web_schemes(
    profile: Union[CitizenProfile, WebDiscoveryProfile, Dict[str, Any]],
    category: Optional[str] = None,
) -> List[DiscoveredScheme]:
    """Retrieve already-discovered, validated web schemes from the shared cache.

    Does NOT invoke Tavily search. Returns an empty list if no discovery response
    has been cached for this profile.
    """
    cache = get_shared_cache()
    config = get_service_config()
    default_limit = config.get("max_candidates", 15)
    limits_to_check = [str(default_limit), "15", "10", "20", "30", ""]

    web_profiles = _build_web_profiles_to_check(profile, category=category)

    for wp in web_profiles:
        dump = wp.model_dump()
        for lim in limits_to_check:
            key = profile_cache_key(dump, lim)
            cached = cache.get(key)
            if cached is not None:
                if isinstance(cached, WebSchemeSearchResponse):
                    return cached.validated_schemes
                if isinstance(cached, list):
                    return cached
                if isinstance(cached, dict) and "validated_schemes" in cached:
                    try:
                        return [
                            DiscoveredScheme.model_validate(x)
                            for x in cached["validated_schemes"]
                        ]
                    except Exception:
                        pass

    # Also check raw dict representation if profile was passed as CitizenProfile or dict
    if isinstance(profile, (CitizenProfile, dict)):
        raw_dump = profile.model_dump() if isinstance(profile, CitizenProfile) else profile
        for lim in limits_to_check:
            key = profile_cache_key(raw_dump, lim)
            cached = cache.get(key)
            if cached is not None:
                if isinstance(cached, WebSchemeSearchResponse):
                    return cached.validated_schemes
                if isinstance(cached, list):
                    return cached

    return []


def perform_live_discovery(
    profile: Union[CitizenProfile, WebDiscoveryProfile, Dict[str, Any]],
    category: Optional[str] = None,
    max_queries: int = 3,
    max_candidates: int = 15,
) -> List[DiscoveredScheme]:
    """Perform a bounded live Tavily discovery for profile and return validated schemes.

    - Checks shared cache first to prevent duplicate external calls.
    - If cache miss, performs ONE bounded WebSchemeDiscoveryService.discover() call.
    - Automatically caches the result in the shared cache.
    - Returns only validated + active schemes.
    - Gracefully returns empty list on expected API/network failures.
    """
    cached = get_cached_web_schemes(profile, category=category)
    if cached:
        logger.info("Found cached web schemes for profile; bypassing live discovery")
        return cached

    web_profile = citizen_to_web_profile(profile, category=category)
    service = get_discovery_service()

    try:
        response = service.discover(
            web_profile,
            max_candidates=max_candidates,
            max_queries=max_queries,
        )
        return response.validated_schemes or []
    except Exception as exc:
        logger.warning("Live web scheme discovery execution error: %s", exc)
        return []


def build_live_scheme_pool(
    curated_schemes: List[Scheme],
    discovered_schemes: List[DiscoveredScheme],
    fallback_category: Optional[str] = None,
) -> Tuple[List[Scheme], Dict[str, DiscoveryMetadata]]:
    """Build candidate pool for match_schemes().

    Product Rule:
    - Curated schemes.json catalogue remains the baseline recommendation pool.
    - Live validated schemes SUPPLEMENT the curated catalogue, not replace it.
    - For a duplicate live scheme, prefer the curated canonical version (already in baseline).
    - For a genuinely new validated live scheme, include it with discovery metadata.
    - For live discovery failure, timeout, zero validated schemes, or junk results,
      curated schemes must still be available.
    - Never duplicate curated schemes.
    - Returns (pool, discovery_meta).
    """
    pool: List[Scheme] = list(curated_schemes)
    discovery_meta: Dict[str, DiscoveryMetadata] = {}
    seen_ids: Set[str] = {s.id.lower() for s in curated_schemes}

    if not discovered_schemes:
        return pool, {}

    for cand in discovered_schemes:
        # 1. Accept ONLY candidates that are validated and active
        if (
            getattr(cand, "validation_status", None) != "verified"
            or getattr(cand, "active_status", None) != "active"
        ):
            logger.debug(
                "Skipping discovered candidate '%s': status=(%s, %s)",
                getattr(cand, "scheme_name", ""),
                getattr(cand, "validation_status", None),
                getattr(cand, "active_status", None),
            )
            continue

        # 2. Curated-first deduplication: prefer curated canonical version (already in pool)
        curated_duplicate = find_duplicate_curated_scheme(cand, curated_schemes)
        if curated_duplicate is not None:
            logger.info(
                "Discovered scheme '%s' matched curated '%s'; curated canonical version preserved",
                getattr(cand, "scheme_name", ""),
                curated_duplicate.id,
            )
            continue

        # 3. Adapt genuinely new candidate to canonical Scheme
        try:
            canonical_scheme = discovered_to_canonical_scheme(
                cand, fallback_category=fallback_category
            )
        except (ValueError, TypeError, ValidationError) as exc:
            logger.warning(
                "Skipping malformed discovered candidate '%s': %s",
                getattr(cand, "scheme_name", ""),
                exc,
            )
            continue

        # 4. Intra-discovery collision check
        sid = canonical_scheme.id.lower()
        if sid in seen_ids:
            continue

        seen_ids.add(sid)
        pool.append(canonical_scheme)
        discovery_meta[canonical_scheme.id] = DiscoveryMetadata(
            is_web_discovered=True,
            confidence=cand.confidence,
            source_type=cand.source_type,
            validation_reasons=list(cand.validation_reasons),
            source_url=cand.source_url or (cand.source_urls[0] if cand.source_urls else None),
        )

    return pool, discovery_meta


def merge_validated_web_schemes(
    curated_schemes: List[Scheme],
    discovered_schemes: List[DiscoveredScheme],
    fallback_category: Optional[str] = None,
) -> Tuple[List[Scheme], Dict[str, DiscoveryMetadata]]:
    """Merge validated web schemes onto full curated list (fallback / auxiliary helper)."""
    if not discovered_schemes:
        return list(curated_schemes), {}

    combined: List[Scheme] = list(curated_schemes)
    metadata_map: Dict[str, DiscoveryMetadata] = {}
    seen_ids: Set[str] = {s.id.lower() for s in curated_schemes}

    for cand in discovered_schemes:
        if (
            getattr(cand, "validation_status", None) != "verified"
            or getattr(cand, "active_status", None) != "active"
        ):
            continue

        if is_duplicate_of_curated(cand, curated_schemes):
            continue

        try:
            canonical_scheme = discovered_to_canonical_scheme(
                cand, fallback_category=fallback_category
            )
        except (ValueError, TypeError, ValidationError) as exc:
            logger.warning("Skipping malformed candidate: %s", exc)
            continue

        sid = canonical_scheme.id.lower()
        if sid in seen_ids:
            continue

        seen_ids.add(sid)
        combined.append(canonical_scheme)
        metadata_map[canonical_scheme.id] = DiscoveryMetadata(
            is_web_discovered=True,
            confidence=cand.confidence,
            source_type=cand.source_type,
            validation_reasons=list(cand.validation_reasons),
            source_url=cand.source_url or (cand.source_urls[0] if cand.source_urls else None),
        )

    return combined, metadata_map
