"""Explicit source-priority policy for web scheme discovery.

Tier 1 (authoritative, can VERIFY):
    official .gov.in websites, central ministries/departments,
    state government sites, official scheme portals, official myScheme pages.

Tier 2 (supporting official portals):
    government-backed program portals (e.g. CSC, KVIC-adjacent official
    program domains explicitly listed below).

Tier 3 (discovery only):
    reputable secondary sources (press/knowledge). May help DISCOVER a
    scheme but can NEVER by itself mark a scheme VERIFIED.

Everything else (blogs, SEO farms, social, forums, scrapers) is
``untrusted`` and cannot verify.
"""

from __future__ import annotations

from urllib.parse import urlparse

TIER1_SUFFIXES = (
    ".gov.in",
    ".nic.in",
)
TIER1_EXACT = {
    "india.gov.in",
    "myscheme.gov.in",
    "mybharat.gov.in",
}
# Well-known official scheme portals that are not under .gov.in.
TIER1_KEYWORDS = (
    "myscheme",
    "pmkisan.gov",
    "pmfby.gov",
    "nrega.nic",
)

TIER2_DOMAINS = {
    "csc.gov.in",
    "kvic.org.in",
    "nrlm.gov.in",
    "uidai.gov.in",
}

SECONDARY_DOMAINS = {
    "wikipedia.org",
    "pib.gov.in",  # press releases often mirror official notices
    "thehindu.com",
    "indianexpress.com",
    "timesofindia.indiatimes.com",
    "hindustantimes.com",
    "business-standard.com",
    "economictimes.indiatimes.com",
    "moneycontrol.com",
}

UNTRUSTED_KEYWORDS = (
    "blogspot",
    "wordpress",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "reddit.com",
    "quora.com",
    "whatsapp",
    "telegram",
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().strip()
    except Exception:
        return ""


def classify_source(url: str) -> tuple[str, str]:
    """Return (tier, source_type) for a URL.

    source_type is one of: official_government | government_portal |
    secondary | untrusted | unknown
    """
    host = _host(url or "")
    if not host:
        return "untrusted", "unknown"

    low_url = (url or "").lower()
    if any(k in low_url for k in UNTRUSTED_KEYWORDS):
        return "untrusted", "untrusted"

    if host in TIER1_EXACT or host.endswith(TIER1_SUFFIXES) or any(
        k in low_url for k in TIER1_KEYWORDS
    ):
        return "tier1", "official_government"
    if host in TIER2_DOMAINS or host in SECONDARY_DOMAINS and host == "pib.gov.in":
        return "tier2", "government_portal"
    if host in SECONDARY_DOMAINS:
        return "tier3", "secondary"
    if host.endswith(TIER1_SUFFIXES):
        return "tier1", "official_government"
    return "untrusted", "secondary"


def is_authoritative(source_type: str) -> bool:
    return source_type in {"official_government", "government_portal"}


def best_source_type(urls: list[str]) -> tuple[str, str, str | None]:
    """Pick the strongest (tier, source_type, url) from a candidate URL list."""
    rank = {"official_government": 0, "government_portal": 1, "secondary": 2}
    best: tuple[str, str, str | None] = ("untrusted", "secondary", None)
    best_rank = 99
    for url in urls or []:
        _tier, stype = classify_source(url)
        r = rank.get(stype, 50)
        if r < best_rank:
            best_rank = r
            best = (_tier, stype, url)
    if best[2] is None and urls:
        best = ("untrusted", "secondary", urls[0])
    return best
