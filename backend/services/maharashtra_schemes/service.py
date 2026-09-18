"""Real-time Maharashtra government scheme discovery from official MahaDBT sources.

Fetches the official Maharashtra Direct Benefit Transfer (MahaDBT) A-to-Z scheme
catalogue and maps every entry onto the shared ``DiscoveredScheme`` model, so the
existing web-discovery validation, deduplication and ``match_schemes`` pipeline
consumes it exactly like any other live candidate.

Guarantees
----------
- ``schemes.json`` remains the guaranteed curated baseline; this module only
  *supplements* it.
- Every emitted record points at the official ``mahadbt.maharashtra.gov.in``
  government portal (no secondary/junk sources).
- Any fetch or parse failure degrades to an empty list and can never break
  ``/api/recommend``.
"""

from __future__ import annotations

import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from services.web_scheme_discovery.cache import TTLCache, profile_cache_key
from services.web_scheme_discovery.schemas import DiscoveredScheme

logger = logging.getLogger("yojnasathi.maharashtra_schemes")

MAHADBT_HOST = "mahadbt.maharashtra.gov.in"
MAHADBT_ATOZ_URL = f"https://{MAHADBT_HOST}/SchemeList/SchemeListAtoZ"
MAHADBT_DETAIL_PREFIX = f"https://{MAHADBT_HOST}/SchemeData/SchemeData?str="
MAHADBT_APPLY_URL = f"https://{MAHADBT_HOST}/Login/Login"

# The published catalogue is stable; cache it for six hours to avoid re-fetching
# on every recommendation. Isolated cache instance so Tavily discovery freshness
# is never affected.
_CATALOG_TTL_SECONDS = 6 * 60 * 60
_catalog_cache = TTLCache(ttl_seconds=_CATALOG_TTL_SECONDS)
_CATALOG_CACHE_KEY = profile_cache_key({"source": "mahadbt", "catalog": "atoz", "v": 2})

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YojnaSathi/0.4; scheme-discovery)",
    "Accept": "text/html,application/xhtml+xml",
}

_DETAIL_LINK_RE = re.compile(
    r'href="(/SchemeData/SchemeData\?str=[^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)

_DETAIL_WORKERS = 6
_DETAIL_TIMEOUT_SECONDS = 12.0

# The detail document ends at the first of these H2 sections that follows the
# "About Scheme" section (header names observed on live MahaDBT pages).
_DETAIL_END_SECTIONS = (
    "related documents",
    "user manuals",
    "online registration",
    "guidelines",
    "notice",
    "सूचना",
    "faq",
)

_NOISE_LINE_RE = re.compile(r"^(?:print|back to list|login to apply|download)", re.I)


def _details_enabled() -> bool:
    """Master switch for scheme-detail enrichment (testable via env var)."""
    return os.environ.get("YOJNASATHI_MAHADBT_DETAILS", "1") not in ("0", "false", "False")


def _clean_name(raw: str) -> str:
    """Strip nested markup/entities and collapse whitespace in a scheme name."""
    name = html.unescape(re.sub(r"<[^>]+>", "", raw or ""))
    return re.sub(r"\s+", " ", name).strip()


def _clean_text(raw: str) -> str:
    """Convert an HTML fragment into readable single-space-separated text."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).replace("\u00a0", " ").strip()


def _clean_lines(raw: str) -> List[str]:
    """Split a section body into meaningful points (drop navigation noise)."""
    lines = []
    for part in (raw or "").splitlines():
        line = _clean_text(part)
        if not line or _NOISE_LINE_RE.search(line):
            continue
        lines.append(line)
    return lines


def _extract_detail_sections(page_text: str) -> dict:
    """Pull Overview/Benefits/Eligibility/Documents out of a MahaDBT detail page.

    Layout (verified against live pages): the whole scheme doc lives between the
    ``h2 "About Scheme"`` heading and the next recognised section heading; inside
    that region ``h3`` sub-headings label each subsection.
    """
    if "About Scheme" not in (page_text or ""):
        return {}

    h2 = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", page_text or "", re.I | re.S))
    about_end: Optional[int] = None
    section_start: Optional[int] = None
    for m in h2:
        label = _clean_name(m.group(1)).lower()
        if about_end is None and label.startswith("about scheme"):
            about_end = m.end()
        elif about_end is not None and section_start is None and label in _DETAIL_END_SECTIONS:
            section_start = m.start()

    if about_end is None or section_start is None:
        return {}

    body = page_text[about_end:section_start]
    parts = re.split(r"<h3[^>]*>(.*?)</h3>", body, flags=re.I | re.S)

    out: dict = {"overview": "", "benefits": [], "eligibility": [], "documents": []}
    for i in range(1, len(parts) - 1, 2):
        title = _clean_name(parts[i]).lower()
        lines = _clean_lines(_clean_text(parts[i + 1]).replace(" | ", "\n"))
        if title.startswith("overview"):
            out["overview"] = " ".join(lines)
        elif title.startswith("eligib"):
            out["eligibility"] = lines
        elif title.startswith("benefit"):
            out["benefits"] = lines
        elif title.startswith("document"):
            out["documents"] = lines

    return out


def _enrich_scheme(scheme: DiscoveredScheme) -> DiscoveredScheme:
    """Fetch one scheme's detail page and back-fill its structured sections.

    Fail-soft: any network/parse error keeps the catalogue entry unchanged.
    """
    if not scheme.source_url:
        return scheme

    try:
        import httpx

        with httpx.Client(
            verify=True,
            follow_redirects=True,
            timeout=_DETAIL_TIMEOUT_SECONDS,
            headers=_HEADERS,
        ) as client:
            response = client.get(scheme.source_url)
            response.raise_for_status()
            sections = _extract_detail_sections(response.text)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.debug("MahaDBT detail fetch failed for '%s': %s", scheme.scheme_name, exc)
        return scheme

    if not (sections["benefits"] or sections["eligibility"] or sections["overview"]):
        return scheme

    return scheme.model_copy(
        update={
            "description": sections["overview"] or scheme.description,
            "benefits": sections["benefits"] or scheme.benefits,
            "eligibility": sections["eligibility"] or scheme.eligibility,
            "documents_required": sections["documents"] or scheme.documents_required,
        }
    )


def _enrich_schemes(schemes: List[DiscoveredScheme]) -> List[DiscoveredScheme]:
    """Enrich all catalogue entries with their detail pages (bounded workers)."""
    if not schemes:
        return schemes

    enriched: dict[int, DiscoveredScheme] = {}
    with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as pool:
        futures = {pool.submit(_enrich_scheme, s): idx for idx, s in enumerate(schemes)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                enriched[idx] = future.result()
            except Exception:  # pragma: no cover - defensive
                enriched[idx] = schemes[idx]

    ordered = [enriched[i] for i in range(len(schemes))]
    filled = sum(1 for s in ordered if s.benefits or s.eligibility or s.description)
    logger.info("MahaDBT scheme details enriched: %d/%d", filled, len(ordered))
    return ordered


def _parse_catalog(page_text: str) -> List[DiscoveredScheme]:
    """Map the official MahaDBT A-to-Z listing into DiscoveredScheme records."""
    schemes: List[DiscoveredScheme] = []
    seen_names: set[str] = set()

    for link, raw_name in _DETAIL_LINK_RE.findall(page_text or ""):
        name = _clean_name(raw_name)
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        token = link.split("str=", 1)[-1]
        detail_url = MAHADBT_DETAIL_PREFIX + token
        schemes.append(
            DiscoveredScheme(
                scheme_name=name,
                scheme_type="state",
                government_level="state",
                state="maharashtra",
                description=(
                    "Official scheme published on the Maharashtra Direct Benefit "
                    "Transfer (MahaDBT) government portal."
                ),
                source_type="official_government_portal",
                application_url=MAHADBT_APPLY_URL,
                source_url=detail_url,
                source_urls=[detail_url],
                active_status="active",
                validation_status="verified",
                validation_reasons=[
                    "Listed on the official MahaDBT portal (mahadbt.maharashtra.gov.in)"
                ],
                confidence=0.9,
            )
        )

    return schemes


def _fetch_catalog() -> List[DiscoveredScheme]:
    """Fetch and parse the official MahaDBT A-to-Z catalogue (one HTTP request)."""
    import httpx

    with httpx.Client(
        verify=True,
        follow_redirects=True,
        timeout=25.0,
        headers=_HEADERS,
    ) as client:
        response = client.get(MAHADBT_ATOZ_URL)
        response.raise_for_status()
        page_text = response.text

    schemes = _parse_catalog(page_text)
    logger.info("MahaDBT catalogue parsed: %d official scheme(s)", len(schemes))
    return schemes


def get_maharashtra_schemes() -> List[DiscoveredScheme]:
    """Return validated live Maharashtra schemes, or ``[]`` on any failure.

    Results are cached for the catalogue TTL. Never raises.
    """
    cached = _catalog_cache.get(_CATALOG_CACHE_KEY)
    if isinstance(cached, list) and cached:
        return cached

    try:
        schemes = _fetch_catalog()
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning(
            "MahaDBT catalogue unavailable; curated baseline remains intact: %s", exc
        )
        return []

    if not schemes:
        return []

    if _details_enabled():
        schemes = _enrich_schemes(schemes)

    _catalog_cache.set(_CATALOG_CACHE_KEY, schemes)
    return schemes
