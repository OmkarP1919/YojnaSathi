"""Deterministic heuristic extractor: Tavily results -> candidate schemes.

No LLM calls here (keeps tests offline and guarantees no invented facts).
Each Tavily result becomes one candidate; the deduplicator later merges
candidates describing the same scheme. Every factual field is copied from
source content or left empty/None.
"""

from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urlparse

from services.web_scheme_discovery.deduplicator import normalize_name
from services.web_scheme_discovery.schemas import DiscoveredScheme, TavilyResultItem
from services.web_scheme_discovery.source_policy import best_source_type

logger = logging.getLogger("yojnasathi.web_discovery.extractor")

_BENEFIT_HINTS = (
    "benefit", "rs", "₹", "lakh", "subsidy", "assistance", "pension",
    "scholarship", "insurance", "loan", "amount", "per year", "per month",
)
_ELIGIBILITY_HINTS = (
    "eligib", "criteria", "must be", "should be", "required", "condition",
    "age", "income", "resident", "domicile", "category", "farmer", "student",
)
_PROCESS_HINTS = ("apply", "application", "portal", "form", "submit", "register", "csc", "online", "offline")
_DOC_HINTS = ("aadhaar", "document", "certificate", "passbook", "ration card", "7/12", "land record", "bank", "income proof")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str, limit: int = 12) -> List[str]:
    parts = [p.strip(" -•\t") for p in _SENT_SPLIT.split(text or "") if p and p.strip()]
    return parts[:limit]


def _pick_sentences(content: str, hints: tuple[str, ...], limit: int = 4) -> List[str]:
    found: List[str] = []
    for sent in _sentences(content):
        low = sent.lower()
        if any(h in low for h in hints) and len(sent) > 20:
            cleaned = " ".join(sent.split())
            if cleaned not in found:
                found.append(cleaned)
        if len(found) >= limit:
            break
    return found


def _guess_application_url(item: TavilyResultItem) -> str | None:
    url = (item.url or "").strip()
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    # Only trust the source URL itself as application URL when it looks official.
    if host.endswith(".gov.in") or host.endswith(".nic.in") or "myscheme" in host:
        return url
    # Otherwise look for an explicit .gov.in link inside the content.
    m = re.search(r"https?://[^\s\"']*\.gov\.in[^\s\"']*", item.content or "")
    if m:
        return m.group(0).rstrip(".,)")
    return None


def _guess_levels(item: TavilyResultItem) -> tuple[str | None, str | None, str | None]:
    text = f"{item.title} {item.content}".lower()
    scheme_type: str | None = None
    state: str | None = None
    for st in ("maharashtra", "gujarat", "bihar", "rajasthan", "karnataka",
               "tamil nadu", "telangana", "punjab", "haryana", "uttar pradesh",
               "madhya pradesh", "west bengal", "odisha", "kerala", "assam"):
        if st in text:
            scheme_type = "state"
            state = st.title() if st != "tamil nadu" else "Tamil Nadu"
            break
    if any(k in text for k in ("central government", "centre ", "pradhan mantri", " pm-", "pm ", "all-india", "all india", "nationwide")):
        if scheme_type is None:
            scheme_type = "central"
    if scheme_type is None and ("state government" in text or "mukhyamantri" in text or "mukhya mantri" in text):
        scheme_type = "state"
    return scheme_type, scheme_type, state


_GENERIC_TITLES = {
    "schemes", "scheme", "government schemes", "govt schemes", "various govt schemes",
    "various government schemes", "all schemes", "state schemes", "welfare schemes",
    "central schemes", "home", "welcome", "dashboard", "services", "citizen services",
    "schemes and programmes", "schemes programmes", "public services", "welfare",
    "schemes directory", "government portal", "official portal",
    "schemes for welfare of women", "schemes for welfare", "schemes for women",
    "women welfare schemes", "welfare of women", "women and child welfare schemes",
}

# Titles that are catalogue/landing-page descriptions rather than a specific
# scheme name. These must never surface as live schemes.
_GENERIC_TITLE_PREFIXES = (
    "list of schemes", "all government schemes", "websites of various", "websites of",
    "directory of", "schemes for", "scheme for", "schemes on", "scheme on",
    "schemes related", "scheme related", "schemes regarding", "schemes under",
    "schemes about", "government schemes", "govt schemes", "state schemes",
    "central schemes", "various schemes", "welfare schemes", "public schemes",
    "beneficiary schemes", "schemes available", "scheme available",
)

_GENERIC_TITLE_RE = re.compile(
    r"^(?:the\s+)?(?:various|all|different|government|govt|state|central|public|"
    r"welfare|social welfare|maharashtra)?\s*schemes?"
    r"(?:\s+(?:for|on|to|of|related to|regarding|under|about)\b.*)?$"
)


def _is_generic_title(title: str) -> bool:
    clean = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    clean = " ".join(clean.split()).strip()
    if not clean:
        return True
    if clean in _GENERIC_TITLES:
        return True
    if clean.startswith(_GENERIC_TITLE_PREFIXES):
        return True
    if _GENERIC_TITLE_RE.match(clean):
        return True
    return False


def _extract_heading_scheme_name(content: str) -> str | None:
    """Attempt to extract a prominent scheme name from markdown headings or content."""
    if not content:
        return None

    # 1. Markdown headings: #, ##, ###
    for m in re.finditer(r"^#{1,3}\s+([^\n\r]+)", content, re.MULTILINE):
        heading = m.group(1).strip()
        heading_clean = re.sub(r"[\*\_#]", "", heading).strip()
        heading_clean = re.split(r"\s+[|\-–]\s+", heading_clean)[0].strip()
        if len(heading_clean) >= 4 and not _is_generic_title(heading_clean):
            return heading_clean[:200]

    # 2. Scheme name patterns: Mukhyamantri/CM/PM ... Yojana/Scheme/Abhiyan
    scheme_pat = re.search(
        r"\b((?:mukhyamantri|mukhya mantri|cm|pradhan mantri|pm)\s+[a-zA-Z\s\-–]{3,60}(?:yojana|scheme|abhiyan|mission|kendra))\b",
        content,
        re.IGNORECASE,
    )
    if scheme_pat:
        matched = " ".join(scheme_pat.group(1).split())
        if len(matched) >= 4 and not _is_generic_title(matched):
            return matched[:200]

    return None


def extract_candidates(results: List[TavilyResultItem]) -> List[DiscoveredScheme]:
    """Convert raw Tavily results into structured (unvalidated) candidates."""
    candidates: List[DiscoveredScheme] = []
    for item in results:
        if not isinstance(item, TavilyResultItem):
            continue
        url = (item.url or "").strip()
        title = (item.title or "").strip()
        content = (item.content or "").strip()
        if not url and not title and not content:
            continue  # malformed/empty result -> skip, never crash
        name = title or url or "Unknown scheme"
        # Trim obvious suffixes ("... | MyScheme", "- Apply Online").
        name = re.split(r"\s+[|\-–]\s+", name)[0].strip()[:200] or "Unknown scheme"
        if _is_generic_title(name):
            extracted_heading = _extract_heading_scheme_name(content)
            if extracted_heading:
                name = extracted_heading
        scheme_type, gov_level, state = _guess_levels(item)
        _tier, source_type, _best = best_source_type([url] if url else [])
        candidates.append(
            DiscoveredScheme(
                scheme_name=name,
                normalized_name=normalize_name(name),
                aliases=[],
                scheme_type=scheme_type,  # type: ignore[arg-type]
                government_level=gov_level,  # type: ignore[arg-type]
                state=state,
                description=" ".join(content.split())[:800] or None,
                benefits=_pick_sentences(content, _BENEFIT_HINTS),
                eligibility=_pick_sentences(content, _ELIGIBILITY_HINTS),
                exclusions=[],
                application_process=_pick_sentences(content, _PROCESS_HINTS, limit=3),
                documents_required=_pick_sentences(content, _DOC_HINTS, limit=4),
                application_url=_guess_application_url(item),
                source_url=url or None,
                source_urls=[url] if url else [],
                source_type=source_type,
                active_status="unknown",
                validation_status="rejected",
                validation_reasons=[],
                confidence=0.0,
            )
        )
    logger.info("Extractor produced %d candidates from %d results", len(candidates), len(results))
    return candidates
