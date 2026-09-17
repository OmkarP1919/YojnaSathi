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
import re
from typing import List

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
_CATALOG_CACHE_KEY = profile_cache_key({"source": "mahadbt", "catalog": "atoz", "v": 1})

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YojnaSathi/0.4; scheme-discovery)",
    "Accept": "text/html,application/xhtml+xml",
}

_DETAIL_LINK_RE = re.compile(
    r'href="(/SchemeData/SchemeData\?str=[^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def _clean_name(raw: str) -> str:
    """Strip nested markup/entities and collapse whitespace in a scheme name."""
    name = html.unescape(re.sub(r"<[^>]+>", "", raw or ""))
    return re.sub(r"\s+", " ", name).strip()


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

    _catalog_cache.set(_CATALOG_CACHE_KEY, schemes)
    return schemes
