"""Deduplication via normalized names, aliases, and official URLs."""

from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import urlparse

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
    # Map known alias groups to a canonical key.
    for group in _ALIAS_GROUPS:
        if text in group:
            return sorted(group, key=len)[0]
    for group in _ALIAS_GROUPS:
        for alias in group:
            if alias in text or text in alias:
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
