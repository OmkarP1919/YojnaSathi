"""Deduplication via normalized names, aliases, and official URLs."""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.schemas import Scheme
from services.web_scheme_discovery.schemas import DiscoveredScheme

# Known alias groups (normalized token sets that mean the same scheme).
_ALIAS_GROUPS: List[set[str]] = [
    {"pmkisan", "pmkisan samman nidhi", "pradhan mantri kisan samman nidhi", "pm kisan samman nidhi"},
    {"pmfby", "pm fasal bima", "pradhan mantri fasal bima yojana", "pm fasal bima yojana"},
    {"pmjay", "ayushman bharat", "pm jay", "pradhan mantri jan arogya"},
    {"pmsvanidhi", "pm svanidhi", "pm swanidhi", "svanidhi"},
    {"ladkibahin", "ladki bahin", "majhi ladki bahin", "mukhyamantri majhi ladki bahin"},
    {"mgnrega", "mnrega", "mahatma gandhi nrega", "nrega"},
    {"pmayg", "pmay g", "pm awas gramin", "pmay gramin"},
    {"pmayu", "pmay u", "pm awas urban", "pmay urban"},
]

_ABBREVIATIONS = {
    "pradhan mantri": "pm",
    "mukhyamantri": "cm",
    "mukhya mantri": "cm",
    "yojana": "",
    "scheme": "",
}


def normalize_name(name: str) -> str:
    text = (name or "").lower().strip()
    for full, short in _ABBREVIATIONS.items():
        text = text.replace(full, short)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) < 3:
        return text

    # 1. Exact match in group
    for group in _ALIAS_GROUPS:
        if text in group:
            return sorted(group, key=len)[0]

    # 2. Token-boundary match: check if a legitimate full alias (length >= 4) is present as words in text
    for group in _ALIAS_GROUPS:
        for alias in group:
            if len(alias) >= 4:
                pattern = r"(?:^|\s)" + re.escape(alias) + r"(?:$|\s)"
                if re.search(pattern, text):
                    return sorted(group, key=len)[0]
    return text


def _official_key(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").rstrip("/").lower()
        if host.endswith(".gov.in") or host.endswith(".nic.in") or "myscheme" in host:
            return f"{host}{path}"
    except Exception:
        return ""
    return ""


def deduplicate(candidates: List[DiscoveredScheme]) -> List[DiscoveredScheme]:
    """Merge candidates describing the same scheme; keep strongest source."""
    grouped: Dict[str, DiscoveredScheme] = {}
    for cand in candidates:
        key = normalize_name(cand.scheme_name)
        official = _official_key(cand.source_url)
        # Two candidates share a group if normalized names match OR they
        # share the same official URL key.
        match_key: str | None = None
        if key in grouped:
            match_key = key
        else:
            for existing_key, existing in grouped.items():
                if not key or not existing_key:
                    continue
                if key == existing_key:
                    match_key = existing_key
                    break
                existing_official = _official_key(existing.source_url)
                if official and existing_official and official == existing_official:
                    match_key = existing_key
                    break
        if match_key is None:
            cand.normalized_name = key
            grouped[key or cand.scheme_name] = cand
            continue
        existing = grouped[match_key]
        # Merge URLs / aliases / evidence lists (dedup, preserve order).
        for url in cand.source_urls:
            if url and url not in existing.source_urls:
                existing.source_urls.append(url)
        for alias in [cand.scheme_name, *cand.aliases]:
            if alias and alias not in existing.aliases and alias != existing.scheme_name:
                existing.aliases.append(alias)
        for lst_name in ("benefits", "eligibility", "application_process", "documents_required"):
            merged = list(getattr(existing, lst_name)) + list(getattr(cand, lst_name))
            seen: set[str] = set()
            deduped: List[str] = []
            for entry in merged:
                k = entry.strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    deduped.append(entry)
            setattr(existing, lst_name, deduped[:6])
        # Prefer a candidate that actually has an application URL / description.
        if not existing.application_url and cand.application_url:
            existing.application_url = cand.application_url
            existing.source_url = cand.source_url or existing.source_url
        if (not existing.description and cand.description) or (
            cand.description and existing.description and len(cand.description) > len(existing.description)
        ):
            existing.description = cand.description
        # Keep the more authoritative source_type.
        rank = {"official_government": 0, "government_portal": 1, "secondary": 2, "untrusted": 3, "unknown": 4}
        if rank.get(cand.source_type, 4) < rank.get(existing.source_type, 4):
            existing.source_type = cand.source_type
            existing.source_url = cand.source_url or existing.source_url
        existing.confidence = max(existing.confidence, cand.confidence)
    return list(grouped.values())


def find_duplicate_curated_scheme(
    candidate: DiscoveredScheme,
    curated_schemes: List[Scheme],
) -> Optional[Scheme]:
    """
    Find matching curated scheme for candidate, or None if genuinely new.

    Evaluation hierarchy:
    1. Canonical ID / known aliases match.
    2. Normalized scheme name equality against curated names.
    3. Official application or source URL key equivalence.
    4. Membership in shared alias groups.

    Curated schemes in schemes.json are canonical and authoritative. If a match is
    detected, the matching curated Scheme object is returned.
    """
    cand_raw_name = candidate.scheme_name or ""
    cand_norm_name = normalize_name(cand_raw_name)
    cand_explicit_norm = normalize_name(candidate.normalized_name) if candidate.normalized_name else cand_norm_name
    cand_aliases_norm = {normalize_name(a) for a in candidate.aliases if a}
    all_cand_names = {n for n in {cand_norm_name, cand_explicit_norm, *cand_aliases_norm} if n and len(n) >= 3}

    cand_app_key = _official_key(candidate.application_url)
    cand_src_key = _official_key(candidate.source_url)
    cand_urls_keys = {_official_key(u) for u in candidate.source_urls if u} - {""}
    cand_all_keys = {cand_app_key, cand_src_key, *cand_urls_keys} - {""}

    for curated in curated_schemes:
        curated_id_raw = curated.id.strip().lower()
        curated_id_norm = normalize_name(curated.id)
        curated_id_nodash = curated_id_raw.replace("-", "").replace("_", "")

        # 1. Canonical IDs / known aliases match
        if (
            curated_id_raw in all_cand_names
            or curated_id_norm in all_cand_names
            or curated_id_nodash in all_cand_names
        ):
            return curated

        # Extract curated localized names
        curated_names_raw: List[str] = []
        if isinstance(curated.name, dict):
            curated_names_raw.extend(str(v) for v in curated.name.values() if v)
        elif isinstance(curated.name, str):
            curated_names_raw.append(curated.name)

        curated_names_norm = {normalize_name(n) for n in curated_names_raw} - {""}

        # 2. Normalized scheme names equality
        if any(cn in all_cand_names for cn in curated_names_norm):
            return curated

        # 3. Official application/source URL equivalence
        curated_app_key = _official_key(curated.application_url)
        curated_src_key = _official_key(curated.source_url)
        curated_keys = {curated_app_key, curated_src_key} - {""}

        # Check for matching official host/path keys
        for ck in cand_all_keys:
            if ck and ck in curated_keys:
                return curated

        # 4. Existing alias groups
        for group in _ALIAS_GROUPS:
            curated_in_group = (
                curated_id_norm in group
                or curated_id_nodash in group
                or any(cn in group for cn in curated_names_norm)
            )
            if curated_in_group:
                cand_in_group = any(cn in group for cn in all_cand_names)
                if cand_in_group:
                    return curated

    return None


def is_duplicate_of_curated(
    candidate: DiscoveredScheme,
    curated_schemes: List[Scheme],
) -> bool:
    """Determine if candidate discovered scheme matches an existing curated scheme."""
    return find_duplicate_curated_scheme(candidate, curated_schemes) is not None
