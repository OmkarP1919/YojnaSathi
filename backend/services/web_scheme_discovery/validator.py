"""Evidence-based validator (the most important component).

A scheme is VERIFIED only with authoritative evidence. Confidence can
never override a hard validation failure.
"""

from __future__ import annotations

import logging
import re
from typing import List

from services.web_scheme_discovery.schemas import (
    DiscoveredScheme,
    EvidenceItem,
    ValidationResult,
)
from services.web_scheme_discovery.source_policy import best_source_type, is_authoritative

logger = logging.getLogger("yojnasathi.web_discovery.validator")

_INACTIVE_HINTS = (
    "discontinued", "closed", "expired", "no longer", "subsumed", "merged into",
    "withdrawn", "terminated", " wound up", "dis-continued", "last date was",
    "applications closed permanently",
)
_ACTIVE_HINTS = (
    "applications are open", "applications are invited", "apply online",
    "apply now", "online application", "online registration",
    "registration open", "currently", "being implemented", "under implementation",
    "ongoing", "active", "last date", "portal", "beneficiaries can apply",
    "farmers can apply", "launched",
)
# A recent scheme-year mention on the page signals a current document.
_ACTIVE_YEAR_HINTS = ("2024", "2025", "2026", "2027")


def _snippet(text: str, limit: int = 220) -> str:
    return " ".join((text or "").split())[:limit]


def detect_active_status(candidate: DiscoveredScheme) -> str:
    blob = " ".join([
        candidate.scheme_name or "",
        candidate.description or "",
        " ".join(candidate.benefits),
        " ".join(candidate.application_process),
    ]).lower()
    if any(h in blob for h in _INACTIVE_HINTS):
        return "inactive"
    if any(h in blob for h in _ACTIVE_HINTS):
        return "active"
    if any(y in blob for y in _ACTIVE_YEAR_HINTS):
        return "active"
    return "unknown"


def _evidence(field: str, url: str, text: str) -> EvidenceItem:
    return EvidenceItem(field=field, source_url=url or "", evidence=_snippet(text))


def validate_candidate(candidate: DiscoveredScheme) -> ValidationResult:
    reasons: List[str] = []
    evidence: List[EvidenceItem] = []
    hard_fail = False

    if not (candidate.scheme_name or "").strip() or candidate.scheme_name.strip().lower() == "unknown scheme":
        reasons.append("Scheme name missing or unidentifiable")
        hard_fail = True

    tier, source_type, best_url = best_source_type(candidate.source_urls)
    authoritative = is_authoritative(source_type)
    primary_url = best_url or candidate.source_url or ""

    if authoritative:
        reasons.append("Official government source found")
        evidence.append(_evidence("source", primary_url, f"Authoritative source: {primary_url}"))
    elif source_type == "secondary":
        reasons.append("Only secondary sources found; authoritative evidence missing")
    else:
        reasons.append("No trustworthy source found")
        hard_fail = True

    has_benefits = bool(candidate.benefits) or bool((candidate.description or "").strip())
    has_eligibility = bool(candidate.eligibility)
    if has_benefits:
        reasons.append("Benefits information present")
        first = candidate.benefits[0] if candidate.benefits else (candidate.description or "")
        evidence.append(_evidence("benefits", primary_url, first))
    else:
        reasons.append("Benefits information missing")
    if has_eligibility:
        reasons.append("Eligibility information present")
        evidence.append(_evidence("eligibility", primary_url, candidate.eligibility[0]))
    else:
        reasons.append("Eligibility information missing")

    if candidate.application_url:
        reasons.append("Application information present")
        evidence.append(_evidence("application_url", candidate.application_url, candidate.application_url))
    else:
        reasons.append("Application URL missing")

    active_status = detect_active_status(candidate)
    if active_status == "inactive":
        reasons.append("Source indicates scheme is discontinued/closed/expired")
    elif active_status == "active":
        reasons.append("Source indicates scheme is currently active")
    else:
        reasons.append("Active status unknown from sources")

    # Verdict (confidence never overrides hard failures).
    if hard_fail or not has_benefits or not has_eligibility:
        if hard_fail or (not has_benefits and not has_eligibility):
            status = "rejected"
        else:
            status = "partially_verified"
        if not authoritative and status == "verified":
            status = "partially_verified"
    elif not authoritative:
        status = "partially_verified"
    elif not candidate.application_url:
        status = "partially_verified"
        reasons.append("Verified content but application URL missing; needs official link")
    else:
        status = "verified"

    if active_status == "inactive" and status == "verified":
        status = "partially_verified"
        reasons.append("Inactive schemes cannot be fully verified as current")

    # Confidence from evidence quality only.
    confidence = 0.0
    if authoritative:
        confidence += 0.4
    if source_type == "official_government" and len([u for u in candidate.source_urls if u]) >= 2:
        confidence += 0.2
    elif source_type == "government_portal":
        confidence += 0.1
    if has_eligibility:
        confidence += 0.15
    if has_benefits:
        confidence += 0.15
    if candidate.application_url:
        confidence += 0.05
    if active_status == "active":
        confidence += 0.05
    confidence = round(min(confidence, 1.0), 2)
    if status == "rejected":
        confidence = min(confidence, 0.4)
    if status == "partially_verified":
        confidence = min(confidence, 0.75)

    return ValidationResult(
        validation_status=status,  # type: ignore[arg-type]
        reasons=reasons,
        evidence=evidence,
        active_status=active_status,  # type: ignore[arg-type]
        confidence=confidence,
    )


def apply_validation(candidate: DiscoveredScheme) -> DiscoveredScheme:
    """Mutate a candidate in place with its validation outcome."""
    result = validate_candidate(candidate)
    candidate.validation_status = result.validation_status  # type: ignore[assignment]
    candidate.validation_reasons = result.reasons
    candidate.active_status = result.active_status  # type: ignore[assignment]
    candidate.confidence = result.confidence
    _tier, source_type, best_url = best_source_type(candidate.source_urls)
    # Record the strongest observed source type (never downgrade official evidence).
    order = {"official_government": 0, "government_portal": 1, "secondary": 2}
    if order.get(source_type, 9) < order.get(candidate.source_type, 9):
        candidate.source_type = source_type
    if best_url:
        candidate.source_url = best_url
    if not candidate.last_verified:
        from datetime import datetime, timezone

        candidate.last_verified = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Validated '%s': %s/%s conf=%.2f",
        candidate.scheme_name[:60],
        result.validation_status,
        result.active_status,
        result.confidence,
    )
    return candidate
