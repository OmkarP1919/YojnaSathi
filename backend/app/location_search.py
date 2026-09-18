"""
Location Web Search Service for YojnaSathi.

Discovers and verifies physical and online application options for known government schemes
from official government sources, with multi-source corroboration (Scheme Notice + District Directory)
and safe fallback to the verified local locations catalog.

Source Priority:
1. Official central government scheme/department portal
2. Official state government department portal
3. Official district government portal (*.gov.in / *.nic.in)
4. State portals (e.g. MahaDBT, Aaple Sarkar)
5. Official CSC / Setu information
6. Verified local catalog fallback (locations.json)
"""
from abc import ABC, abstractmethod
from html.parser import HTMLParser
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import httpx

from app.locations import find_locations, load_locations_data
from app.schemas import (
    ApplicationLocation,
    ApplicationOptionsResult,
    OnlineApplication,
    Scheme,
)

logger = logging.getLogger("yojnasathi.location_search")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 YojnaSathi/0.4.0"
)

OFFICIAL_GOV_SUFFIXES = (
    ".gov.in",
    ".nic.in",
    ".mahaonline.gov.in",
    ".digitalindia.gov.in",
    ".csc.gov.in",
)

# Official scheme and department domain directories mapping
OFFICIAL_SCHEME_PORTALS: Dict[str, Dict[str, Any]] = {
    "pm-kisan": {
        "portal_name": "PM-KISAN Central Portal",
        "domain": "pmkisan.gov.in",
        "official_url": "https://pmkisan.gov.in/",
        "directory_url": "https://pmkisan.gov.in/ContactUs.aspx",
        "level": "central",
    },
    "pmfby": {
        "portal_name": "Pradhan Mantri Fasal Bima Yojana Portal",
        "domain": "pmfby.gov.in",
        "official_url": "https://pmfby.gov.in/",
        "directory_url": "https://pmfby.gov.in/",
        "level": "central",
    },
    "pm-jay": {
        "portal_name": "Ayushman Bharat PM-JAY Portal",
        "domain": "pmjay.gov.in",
        "official_url": "https://pmjay.gov.in/",
        "directory_url": "https://nha.gov.in/",
        "level": "central",
    },
    "majhi-ladki-bahin": {
        "portal_name": "Mukhyamantri Majhi Ladki Bahin Yojana Portal",
        "domain": "ladakibahin.maharashtra.gov.in",
        "official_url": "https://ladakibahin.maharashtra.gov.in/",
        "directory_url": "https://ladakibahin.maharashtra.gov.in/",
        "level": "state",
        "state": "maharashtra",
    },
    "mjpjay": {
        "portal_name": "Mahatma Jyotirao Phule Jan Arogya Yojana Portal",
        "domain": "jeevandayee.gov.in",
        "official_url": "https://www.jeevandayee.gov.in/",
        "directory_url": "https://www.jeevandayee.gov.in/",
        "level": "state",
        "state": "maharashtra",
    },
}

OFFICIAL_DISTRICT_PORTALS: Dict[str, str] = {
    "nashik": "https://nashik.gov.in",
    "pune": "https://pune.gov.in",
}

# Maximum wall-clock time (seconds) allowed for ALL live government web lookups
# inside find_application_options() before falling back to locations.json.
# This prevents slow or unresponsive government district portals (e.g. pune.gov.in
# from Render cloud egress) from blocking the request handler beyond the
# frontend's 30-second axios timeout. Kept comfortably below 30s.
LIVE_DISCOVERY_BUDGET_SECONDS: float = 5.0

# Per-request timeout used when probing candidate government web pages.
# Lower than the budget so multiple URLs can be tried within the budget.
LIVE_REQUEST_TIMEOUT_SECONDS: float = 2.0


# ---------------------------------------------------------------------------
# 1. Official Government Domain & URL Verification
# ---------------------------------------------------------------------------

def is_official_gov_domain(url: str) -> bool:
    """
    Validates that a URL belongs strictly to an official Indian government domain
    (*.gov.in, *.nic.in, *.mahaonline.gov.in, *.digitalindia.gov.in, *.csc.gov.in).
    Rejects third-party domains, blogs, news portals, and spoofed subdomains.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return any(
            host == suffix.lstrip(".") or host.endswith(suffix)
            for suffix in OFFICIAL_GOV_SUFFIXES
        )
    except Exception:
        return False


def is_safe_pdf_response(resp: httpx.Response, max_bytes: int = 2_000_000) -> bool:
    """
    Lightweight guard against massive PDF files on government CDNs.
    Skips downloading PDFs larger than max_bytes (default 2 MB).
    """
    content_type = resp.headers.get("content-type", "").lower()
    if "application/pdf" in content_type:
        try:
            content_length = int(resp.headers.get("content-length", 0))
            if content_length > max_bytes:
                logger.info("Skipping large PDF (%s bytes > %s bytes limit): %s", content_length, max_bytes, resp.url)
                return False
        except (ValueError, TypeError):
            pass
    return True


# ---------------------------------------------------------------------------
# 2. Standard District Directory URL Resolver
# ---------------------------------------------------------------------------

def get_standard_district_directory_urls(district: str, state: str = "maharashtra") -> List[str]:
    """
    Resolves official NIC S3WaaS district directory endpoints.
    NIC standardizes district contact directories at /whos-who/ and /en/whos-who/.

    Only the 3 highest-probability canonical paths are returned so that a
    slow or firewalled district portal cannot consume more than
    3 × LIVE_REQUEST_TIMEOUT_SECONDS of the live-discovery budget.
    """
    s_dist = district.strip().lower()
    base = OFFICIAL_DISTRICT_PORTALS.get(s_dist, f"https://{s_dist}.gov.in")
    return [
        f"{base}/en/whos-who/",
        f"{base}/whos-who/",
        f"{base}/directory/",
    ]


# ---------------------------------------------------------------------------
# 3. Authority Extraction & Intent Parser
# ---------------------------------------------------------------------------

class AuthorityExtractionResult:
    """Structured extraction output from official scheme notices."""

    def __init__(
        self,
        is_online_only: bool = False,
        designated_authorities: Optional[Dict[str, str]] = None,
        online_portal_urls: Optional[List[str]] = None,
    ):
        self.is_online_only = is_online_only
        self.designated_authorities = designated_authorities or {}
        self.online_portal_urls = online_portal_urls or []


class AuthorityExtractionParser:
    """
    Parses official government scheme notices/pages to extract designated
    application authorities, action types, and online-only directives.
    """

    ONLINE_ONLY_PATTERNS = [
        r"\bonline\s+only\b",
        r"\bonly\s+online\b",
        r"\bno\s+offline\s+application\b",
        r"\bno\s+physical\s+application\b",
        r"\bapplications?\s+must\s+be\s+submitted\s+online\b",
        r"\bmandatory\s+online\b",
        r"\bapply\s+online\s+only\b",
    ]

    AUTHORITY_KEYWORDS = {
        "tahsil_office": ["tahsil", "tehsil", "tahsildar", "taluka office", "talathi"],
        "citizen_service_center": [
            "setu kendra", "setu", "csc", "common service centre", "common service center",
            "maha e-seva", "maha eseva", "citizen facilitation", "citizen service centre", "citizen service center"
        ],
        "district_agriculture_office": ["agriculture office", "krishi bhavan", "krishi adhikar", "dsao", "district superintending agriculture"],
        "anganwadi_center": ["anganwadi", "cdpo", "child development project", "icds"],
        "civil_hospital": ["civil hospital", "district hospital", "sub-district hospital", "phc", "primary health centre", "primary health center"],
        "collectorate": ["collector", "collectorate", "district magistrate"],
    }

    APPLICATION_ACTION_KEYWORDS = [
        "apply", "submit", "submission", "application", "register", "registration",
        "form", "verification", "enrollment", "arji", "aadhaar seeding", "documents submit"
    ]

    ASSISTANCE_ACTION_KEYWORDS = [
        "contact", "inquiry", "helpline", "grievance", "complaint", "information",
        "guidance", "help", "assistance", "queries"
    ]

    @classmethod
    def parse_text(cls, text: str) -> AuthorityExtractionResult:
        if not text:
            return AuthorityExtractionResult()

        text_lower = text.lower()

        # 1. Check for online-only directive
        is_online_only = any(bool(re.search(pat, text_lower)) for pat in cls.ONLINE_ONLY_PATTERNS)

        designated: Dict[str, str] = {}

        # 2. Check for each authority and context
        for auth_type, keywords in cls.AUTHORITY_KEYWORDS.items():
            for kw in keywords:
                for match in re.finditer(r"\b" + re.escape(kw) + r"\b", text_lower):
                    start = max(0, match.start() - 150)
                    end = min(len(text_lower), match.end() + 150)
                    window = text_lower[start:end]

                    has_app = any(re.search(r"\b" + re.escape(akw) + r"\b", window) for akw in cls.APPLICATION_ACTION_KEYWORDS)
                    has_assist = any(re.search(r"\b" + re.escape(skw) + r"\b", window) for skw in cls.ASSISTANCE_ACTION_KEYWORDS)

                    if has_app:
                        designated[auth_type] = "scheme_designated_application_center"
                        break
                    elif has_assist and auth_type not in designated:
                        designated[auth_type] = "general_government_assistance"

        return AuthorityExtractionResult(
            is_online_only=is_online_only,
            designated_authorities=designated,
        )


# ---------------------------------------------------------------------------
# 4. Query Construction & Location Hierarchy Filtering
# ---------------------------------------------------------------------------

def build_official_search_query(
    scheme_name: str,
    state: str,
    district: Optional[str] = None,
    taluka: Optional[str] = None,
) -> str:
    """
    Constructs a targeted search query for official government application locations.
    Incorporates scheme, state, district, and taluka with official site filtering.
    """
    parts = [scheme_name.strip()]
    if taluka and taluka.strip() and taluka.strip().lower() != "other":
        parts.append(taluka.strip())
    if district and district.strip() and district.strip().lower() != "other":
        parts.append(district.strip())
    if state and state.strip():
        parts.append(state.strip())
    parts.append("application office where to apply site:gov.in")
    return " ".join(parts)


def filter_locations_hierarchy(
    locations: List[ApplicationLocation],
    state: str,
    district: Optional[str] = None,
    taluka: Optional[str] = None,
) -> List[ApplicationLocation]:
    """
    Filter candidate locations according to state -> district -> taluka hierarchy.
    Rules:
    - State: Must match requested state.
    - District: If district is supplied, location must match district (or be a broader
      state-level office if no district specified).
    - Taluka: If taluka is supplied:
      * Locations matching the exact taluka are included.
      * District-level offices (where taluka is None/unspecified) remain valid and
        are included because they legitimately serve the entire district.
      * Locations explicitly belonging to a different taluka are strictly excluded.
    - Never fabricates a taluka or district association.
    """
    s_state = state.strip().lower()
    s_dist = district.strip().lower() if district and district.strip() and district.strip().lower() != "other" else None
    s_tal = taluka.strip().lower() if taluka and taluka.strip() and taluka.strip().lower() != "other" else None

    filtered: List[ApplicationLocation] = []
    for loc in locations:
        loc_state = (loc.state or "").strip().lower()
        if loc_state and loc_state != s_state:
            continue

        loc_dist = (loc.district or "").strip().lower() if loc.district else None
        if s_dist:
            if loc_dist and loc_dist != s_dist:
                continue
        else:
            if loc_dist:
                continue

        loc_tal = (loc.taluka or "").strip().lower() if loc.taluka else None
        if s_tal:
            # Citizen service centers (CSCs) are hyper-local neighborhood centers;
            # they must match the requested taluka strictly and never fall back to taluka=None.
            if loc.office_type == "citizen_service_center" and loc_tal != s_tal:
                continue
            if loc_tal and loc_tal != s_tal:
                continue
        else:
            # Requirement B: When no taluka is supplied, do NOT present citizen service centers
            # as if they were generic district-level offices.
            if loc.office_type == "citizen_service_center":
                continue
            if loc_tal:
                continue

        filtered.append(loc)

    return filtered


# ---------------------------------------------------------------------------
# 5. Enhanced HTML Directory Parser & Location Extractor
# ---------------------------------------------------------------------------

class GovDirectoryHTMLParser(HTMLParser):
    """
    Safely parses directory tables, card blocks, and structured non-table blocks
    from official *.gov.in HTML pages without hallucinating values.
    """

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tr = False
        self.in_td = False
        self.current_row: List[str] = []
        self.current_cell: List[str] = []
        self.rows: List[List[str]] = []

        # Non-table block tracking
        self.in_card = False
        self.card_depth = 0
        self.current_card: List[str] = []
        self.cards: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attrs_dict = dict(attrs)
        class_str = attrs_dict.get("class", "").lower()
        id_str = attrs_dict.get("id", "").lower()

        if tag_lower == "table":
            self.in_table = True
        elif tag_lower == "tr" and self.in_table:
            self.in_tr = True
            self.current_row = []
        elif tag_lower in ("td", "th") and self.in_tr:
            self.in_td = True
            self.current_cell = []

        if not self.in_table:
            is_card_tag = tag_lower in ("div", "article", "section", "li", "p") and (
                any(k in class_str for k in ("card", "officer", "office", "contact", "entry", "item", "box", "block"))
                or any(k in id_str for k in ("office", "contact", "officer"))
            )
            if is_card_tag or self.in_card:
                self.in_card = True
                self.card_depth += 1

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in ("td", "th") and self.in_td:
            self.in_td = False
            cell_text = " ".join("".join(self.current_cell).split())
            self.current_row.append(cell_text)
            self.current_cell = []
        elif tag_lower == "tr" and self.in_tr:
            self.in_tr = False
            if any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = []
        elif tag_lower == "table":
            self.in_table = False

        if self.in_card:
            self.card_depth -= 1
            if self.card_depth <= 0:
                self.in_card = False
                self.card_depth = 0
                card_text = " ".join("".join(self.current_card).split())
                if len(card_text) >= 15:
                    self.cards.append(card_text)
                self.current_card = []

    def handle_data(self, data):
        if self.in_td:
            self.current_cell.append(data)
        if self.in_card:
            self.current_card.append(data)


# ---------------------------------------------------------------------------
# 6. Provider Abstractions
# ---------------------------------------------------------------------------

class LocationSearchProvider(ABC):
    """Abstract base provider for location discovery."""

    @abstractmethod
    def search(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
    ) -> Optional[List[ApplicationLocation]]:
        """
        Search official sources for physical application locations.
        Returns a list of verified locations or None if unverified/unavailable.
        """
        pass


class SearchBackend(ABC):
    """Abstract backend for querying web search engines."""

    @abstractmethod
    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Returns candidate search items:
        [{'title': ..., 'url': ..., 'snippet': ...}]
        """
        pass


_UNSET = object()


class SerperSearchBackend(SearchBackend):
    """
    Search backend for Serper Google Search API (https://google.serper.dev/search).
    Requires SERPER_API_KEY (or LOCATION_SEARCH_API_KEY with provider=serper).
    """

    def __init__(
        self,
        api_key: Any = _UNSET,
        client: Optional[httpx.Client] = None,
        timeout: float = 5.0,
    ):
        if api_key is not _UNSET:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("SERPER_API_KEY") or os.getenv("LOCATION_SEARCH_API_KEY")
        self._client = client
        self._timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not self.is_available():
            logger.debug("Serper API key not configured; skipping Serper search.")
            return []

        try:
            client = self._client or httpx.Client(
                timeout=self._timeout,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
            )
            url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "q": query,
                "num": min(max_results, 10),
                "gl": "in",
            }
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning("Serper API returned status %s for query: %s", resp.status_code, query)
                return []

            data = resp.json()
            organic_results = data.get("organic", [])
            items = []
            for item in organic_results:
                link = item.get("link") or item.get("url")
                if link:
                    items.append({
                        "title": item.get("title", ""),
                        "url": link,
                        "snippet": item.get("snippet", ""),
                    })
            return items
        except Exception as exc:
            logger.warning("Error querying Serper search API: %s", exc)
            return []


class GoogleCSESearchBackend(SearchBackend):
    """
    Search backend for Google Custom Search JSON API.
    Requires LOCATION_SEARCH_API_KEY and LOCATION_SEARCH_ENGINE_ID.
    """

    def __init__(
        self,
        api_key: Any = _UNSET,
        engine_id: Any = _UNSET,
        client: Optional[httpx.Client] = None,
        timeout: float = 5.0,
    ):
        if api_key is not _UNSET:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("LOCATION_SEARCH_API_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
        if engine_id is not _UNSET:
            self.engine_id = engine_id
        else:
            self.engine_id = os.getenv("LOCATION_SEARCH_ENGINE_ID") or os.getenv("GOOGLE_CSE_ID")
        self._client = client
        self._timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key and self.engine_id)

    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not self.is_available():
            logger.debug("Google CSE credentials not configured; skipping Google CSE search.")
            return []

        try:
            client = self._client or httpx.Client(
                timeout=self._timeout,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
            )
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.api_key,
                "cx": self.engine_id,
                "q": query,
                "num": min(max_results, 10),
            }
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("Google CSE API returned status %s for query: %s", resp.status_code, query)
                return []
            data = resp.json()
            items = data.get("items", [])
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in items
                if item.get("link")
            ]
        except Exception as exc:
            logger.warning("Error querying Google CSE API: %s", exc)
            return []


class ExternalSearchAPIProvider(SearchBackend, LocationSearchProvider):
    """
    Unified search provider and backend routing to Serper or Google Custom Search.
    Gracefully unavailable when API credentials are not configured in environment variables.
    """

    def __init__(
        self,
        api_key: Any = _UNSET,
        engine_id: Any = _UNSET,
        provider_name: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 5.0,
    ):
        configured_provider = (
            provider_name
            or os.getenv("LOCATION_SEARCH_PROVIDER")
            or ("serper" if os.getenv("SERPER_API_KEY") else "google_cse")
        ).strip().lower()

        self.provider_name = configured_provider
        if api_key is not _UNSET:
            self.api_key = api_key
        else:
            self.api_key = (
                os.getenv("SERPER_API_KEY") if self.provider_name == "serper" else os.getenv("LOCATION_SEARCH_API_KEY")
            )
        if engine_id is not _UNSET:
            self.engine_id = engine_id
        else:
            self.engine_id = os.getenv("LOCATION_SEARCH_ENGINE_ID")
        self._client = client
        self._timeout = timeout

        if self.provider_name == "serper":
            self._backend: SearchBackend = SerperSearchBackend(
                api_key=self.api_key,
                client=self._client,
                timeout=self._timeout,
            )
        else:
            self._backend = GoogleCSESearchBackend(
                api_key=self.api_key,
                engine_id=self.engine_id,
                client=self._client,
                timeout=self._timeout,
            )

    def is_available(self) -> bool:
        if hasattr(self._backend, "is_available"):
            return self._backend.is_available()
        return bool(self.api_key)

    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        return self._backend.search_candidates(query, max_results=max_results)

    def search(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
    ) -> Optional[List[ApplicationLocation]]:
        if not self.is_available():
            return None
        # Delegates to GovernmentWebSearchProvider using self as backend
        gov_provider = GovernmentWebSearchProvider(backend=self)
        return gov_provider.search(scheme_id, state, district, taluka)


class OfficialPortalLocationProvider(LocationSearchProvider):
    """
    Discovers physical application centers directly from official government
    department, scheme, and district portals (*.gov.in) supporting /whos-who/ and tables.
    """

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        timeout: float = LIVE_REQUEST_TIMEOUT_SECONDS,
    ):
        self._client = client
        self._timeout = timeout

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        )

    def search(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
    ) -> Optional[List[ApplicationLocation]]:
        s_id = scheme_id.strip().lower()
        s_state = state.strip().lower()
        s_dist = district.strip().lower() if district and district.strip() else None
        s_tal = taluka.strip().lower() if taluka and taluka.strip() else None

        client = self._get_client()

        # Check district endpoints first if district supplied
        if s_dist:
            candidate_urls = get_standard_district_directory_urls(s_dist, s_state)
            for target_url in candidate_urls:
                try:
                    resp = client.get(target_url)
                    if resp.status_code != 200:
                        continue
                    if not is_safe_pdf_response(resp):
                        continue

                    content_type = resp.headers.get("content-type", "").lower()
                    if "json" in content_type:
                        locs = self._parse_json_directory(
                            resp.json(),
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=target_url,
                        )
                    else:
                        locs = self._parse_html_directory(
                            resp.text,
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=target_url,
                        )

                    if locs:
                        filtered = filter_locations_hierarchy(locs, state=s_state, district=s_dist, taluka=s_tal)
                        if filtered:
                            return filtered
                except Exception as exc:
                    logger.debug("Error checking official directory %s: %s", target_url, exc)
                    continue

        # Check official scheme portals
        if s_id in OFFICIAL_SCHEME_PORTALS:
            portal_info = OFFICIAL_SCHEME_PORTALS[s_id]
            target_url = portal_info.get("directory_url") or portal_info.get("official_url")
            if target_url:
                try:
                    resp = client.get(target_url)
                    if resp.status_code == 200 and is_safe_pdf_response(resp):
                        content_type = resp.headers.get("content-type", "").lower()
                        if "json" in content_type:
                            locs = self._parse_json_directory(
                                resp.json(),
                                scheme_id=s_id,
                                state=s_state,
                                district=s_dist,
                                taluka=s_tal,
                                source_url=target_url,
                            )
                        else:
                            locs = self._parse_html_directory(
                                resp.text,
                                scheme_id=s_id,
                                state=s_state,
                                district=s_dist,
                                taluka=s_tal,
                                source_url=target_url,
                            )
                        if locs:
                            return filter_locations_hierarchy(locs, state=s_state, district=s_dist, taluka=s_tal)
                except Exception as exc:
                    logger.warning("Error fetching scheme portal %s: %s", target_url, exc)

        return None

    def _classify_office_type(self, text: str) -> Optional[str]:
        t = text.lower()
        if "tahsil" in t or "tehsil" in t:
            return "tahsil_office"
        elif "collector" in t or "collectorate" in t:
            return "collectorate"
        elif "agriculture" in t or "krishi" in t:
            return "district_agriculture_office"
        elif "hospital" in t:
            return "civil_hospital"
        elif any(w in t for w in ("setu", "csc", "seva", "citizen center", "citizen service", "common service")):
            return "citizen_service_center"
        elif "anganwadi" in t or "cdpo" in t or "icds" in t:
            return "anganwadi_center"
        return None

    def _parse_html_directory(
        self,
        html_content: str,
        scheme_id: str,
        state: str,
        district: Optional[str],
        taluka: Optional[str],
        source_url: str,
    ) -> Optional[List[ApplicationLocation]]:
        parser = GovDirectoryHTMLParser()
        try:
            parser.feed(html_content)
        except Exception as exc:
            logger.debug("HTML parse error on official page: %s", exc)
            return None

        locations: List[ApplicationLocation] = []

        # 1. Parse table rows
        for row in parser.rows:
            row_text = " ".join(row)
            office_type = self._classify_office_type(row_text)
            if not office_type or len(row) < 2:
                continue

            phone_match = re.search(r"(\+?91[- ]?)?[0-9]{3,5}[- ]?[0-9]{6,8}", row_text)
            phone = phone_match.group(0).strip() if phone_match else None

            office_name = row[0] if len(row[0]) > 3 else (row[1] if len(row) > 1 else "")

            # Multi-column address extraction (Center Name | VLE Name | Address/Village/Taluka | Mobile)
            address_parts = [
                col.strip() for col in row[1:]
                if col.strip() and col.strip() != office_name and (not phone or phone not in col)
            ]
            raw_address = ", ".join(address_parts) if address_parts else (
                row[1] if len(row) > 1 and row[1] != office_name else ""
            )

            if len(office_name.strip()) < 4 or (not raw_address.strip() and not phone):
                continue

            address = raw_address.strip() or f"{office_name}, {district or state}"

            # Taluka association: associate if requested taluka appears in the row.
            loc_taluka = None
            if taluka and taluka.lower() in row_text.lower():
                loc_taluka = taluka
            elif office_type == "citizen_service_center":
                # For localized citizen service centers, extract the other taluka if present
                other_tal_match = re.search(r"\b(?:taluka|tehsil|taluk)\s*[:\-–]?\s*([a-zA-Z]+)\b", row_text, re.IGNORECASE)
                if not other_tal_match:
                    other_tal_match = re.search(r"\b([a-zA-Z]+)\s+(?:taluka|tehsil|taluk)\b", row_text, re.IGNORECASE)
                if other_tal_match:
                    cand_tal = other_tal_match.group(1).strip().lower()
                    if cand_tal not in ("name", "of", "the", "district", "center"):
                        loc_taluka = cand_tal
                elif taluka:
                    # If a specific taluka was requested, and this local CSC row does not mention it,
                    # mark as other so hierarchy filtering strictly excludes it
                    loc_taluka = "other"

            loc_id = f"live-{state[:3]}-{district or 'st'}-{len(locations)+1}"
            locations.append(
                ApplicationLocation(
                    id=loc_id,
                    scheme_ids=[scheme_id],
                    categories=[],
                    state=state,
                    district=district,
                    taluka=loc_taluka,
                    office_name={"en": office_name.strip()},
                    office_type=office_type,
                    address={"en": address},
                    contact_phone=phone,
                    working_hours={"en": "Mon-Fri: 9:45 AM - 6:15 PM"},
                    source_url=source_url,
                    application_method="scheme_designated_application_center",
                )
            )

        # 2. Parse non-table card blocks
        for card in parser.cards:
            office_type = self._classify_office_type(card)
            if not office_type:
                continue

            phone_match = re.search(r"(\+?91[- ]?)?[0-9]{3,5}[- ]?[0-9]{6,8}", card)
            phone = phone_match.group(0).strip() if phone_match else None

            # Look for address indicator: PIN code or street keywords
            has_pin = bool(re.search(r"\b[1-9][0-9]{2}\s?[0-9]{3}\b", card))
            has_addr_words = any(w in card.lower() for w in ("road", "nagar", "bhavan", "chowk", "near", "bus stand", "address"))

            if not phone and not (has_pin or has_addr_words):
                continue

            # Extract office name from the first segment
            segments = [s.strip() for s in re.split(r"[\n\r|;]|(?=address:)|(?=phone:)", card, flags=re.IGNORECASE) if s.strip()]
            office_name = segments[0] if segments and len(segments[0]) >= 4 else "Government Office"
            address = segments[1] if len(segments) > 1 and len(segments[1]) >= 6 else card[:120]

            loc_taluka = taluka if (taluka and taluka.lower() in card.lower()) else None
            loc_id = f"live-{state[:3]}-{district or 'st'}-{len(locations)+1}"

            locations.append(
                ApplicationLocation(
                    id=loc_id,
                    scheme_ids=[scheme_id],
                    categories=[],
                    state=state,
                    district=district,
                    taluka=loc_taluka,
                    office_name={"en": office_name},
                    office_type=office_type,
                    address={"en": address},
                    contact_phone=phone,
                    working_hours={"en": "Mon-Fri: 9:45 AM - 6:15 PM"},
                    source_url=source_url,
                    application_method="scheme_designated_application_center",
                )
            )

        if not locations:
            return None

        # Deduplicate locations with identical name and address
        seen_keys = set()
        deduped: List[ApplicationLocation] = []
        for loc in locations:
            name_str = loc.office_name.get("en", "") if isinstance(loc.office_name, dict) else str(loc.office_name)
            addr_str = loc.address.get("en", "") if isinstance(loc.address, dict) else str(loc.address)
            k = (name_str.strip().lower(), addr_str.strip().lower())
            if k in seen_keys:
                continue
            seen_keys.add(k)
            deduped.append(loc)

        return deduped if deduped else None

    def _parse_json_directory(
        self,
        data: Any,
        scheme_id: str,
        state: str,
        district: Optional[str],
        taluka: Optional[str],
        source_url: str,
    ) -> Optional[List[ApplicationLocation]]:
        if not isinstance(data, (dict, list)):
            return None

        entries = data if isinstance(data, list) else data.get("offices") or data.get("locations") or []
        if not isinstance(entries, list) or not entries:
            return None

        locations: List[ApplicationLocation] = []
        for idx, item in enumerate(entries):
            if not isinstance(item, dict):
                continue
            name = item.get("office_name") or item.get("name")
            addr = item.get("address")
            if not name or not addr:
                continue

            name_en = name.get("en") if isinstance(name, dict) else str(name)
            addr_en = addr.get("en") if isinstance(addr, dict) else str(addr)

            if len(name_en.strip()) < 4 or len(addr_en.strip()) < 5:
                continue

            locations.append(
                ApplicationLocation(
                    id=f"live-{state[:3]}-{district or 'st'}-{idx+1}",
                    scheme_ids=[scheme_id],
                    categories=[],
                    state=state,
                    district=district,
                    taluka=taluka,
                    office_name={"en": name_en},
                    office_type=item.get("office_type") or "government_office",
                    address={"en": addr_en},
                    contact_phone=item.get("contact_phone") or item.get("phone"),
                    working_hours={"en": "Mon-Fri: 9:45 AM - 6:15 PM"},
                    source_url=source_url,
                    application_method="scheme_designated_application_center",
                )
            )

        return locations if locations else None


# ---------------------------------------------------------------------------
# 6b. Maharashtra Aaple Sarkar Sewa Kendra Directory Provider
# ---------------------------------------------------------------------------

class MaharashtraSewaKendraProvider(LocationSearchProvider):
    """
    Discovers citizen-facing Aaple Sarkar Seva Kendra / Maha e-Seva / Setu Kendra /
    CSC centers from the official Maharashtra Aaple Sarkar Sewa Kendra directory.

    Official source mechanism (aaplesarkar.mahaonline.gov.in):
      1. GET  /en/CommonForm/SewaKendraDetails            -> HTML district dropdown (codes)
      2. GET  /en/CommonForm/GetTalukaDetails?DistrictID= -> JSON taluka list (codes)
      3. POST /en/CommonForm/SewaKendraDetails            -> table of
         VLE Name | Address | Pincode | Mobile | EmailID
         rows already filtered server-side by the selected taluka.

    The provider is exercised only for Maharashtra when the scheme authorizes the
    citizen_service_center channel. It never fabricates centers and never relies on
    search-engine snippets or private/commercial listings.
    """

    BASE_URL = "https://aaplesarkar.mahaonline.gov.in"
    DETAILS_URL = BASE_URL + "/en/CommonForm/SewaKendraDetails"
    TALUKA_API_PATH = "/en/CommonForm/GetTalukaDetails"
    APPROVED_HOST = "aaplesarkar.mahaonline.gov.in"

    PLACE_SUFFIXES = (" taluka", " tehsil", " tahsil", " taluk", " sub-district", " district")
    DISTRICT_ALIASES = {"nasik": "nashik"}

    CACHE_TTL_SECONDS = 6 * 3600.0
    _lookup_cache: Dict[Tuple[str, Any], Tuple[float, Any]] = {}

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
    ):
        self._client = client
        self._timeout = timeout

    # -- public interface ---------------------------------------------------

    def search(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
    ) -> Optional[List[ApplicationLocation]]:
        s_state = self.normalize_place_name(state)
        if s_state != "maharashtra":
            return None
        s_dist = self.normalize_district_name(district) if district and district.strip() else None
        s_tal = self.normalize_place_name(taluka) if taluka and taluka.strip() else None
        if not s_dist or not s_tal or s_tal in ("other", "all"):
            return None

        client = self._get_client()
        try:
            district_id = self._fetch_district_id(client, s_dist)
            if district_id is None:
                logger.info("Maharashtra Sewa Kendra district not found in directory: %s", s_dist)
                return None
            taluka_code, other_talukas = self._fetch_taluka_code_and_others(client, district_id, s_tal)
            if taluka_code is None:
                logger.info("Maharashtra Sewa Kendra taluka not found in directory: %s / %s", s_dist, s_tal)
                return None
            centers = self._fetch_centers(
                client, s_state, s_dist, s_tal, district_id, taluka_code, other_talukas=other_talukas
            )
            if not centers:
                logger.info("No Maharashtra Sewa Kendra centers returned for %s / %s", s_dist, s_tal)
                return None

            deduped = self._deduplicate(centers)
            filtered = filter_locations_hierarchy(
                deduped,
                state=s_state,
                district=s_dist,
                taluka=s_tal,
            )
            return filtered or None
        except Exception as exc:
            logger.warning(
                "Maharashtra Sewa Kendra directory error (%s/%s): %s",
                s_dist, s_tal, exc,
            )
            return None

    # -- HTTP ---------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            verify=True,
        )

    def _is_approved_response_url(self, response: httpx.Response) -> bool:
        """Only accept results still served from the approved government directory domain."""
        try:
            target = response.url
            host = target.host.lower() if isinstance(target, httpx.URL) else ""
        except Exception:
            return False
        return host == self.APPROVED_HOST or host.endswith(".mahaonline.gov.in")

    def _fetch_district_id(self, client: httpx.Client, district: str) -> Optional[str]:
        cache_key: Tuple[str, Any] = ("districts", "")
        options = self._cache_get(cache_key)
        if options is None:
            resp = client.get(self.DETAILS_URL)
            if resp.status_code != 200:
                return None
            if not self._is_approved_response_url(resp):
                logger.warning("Sewa Kendra directory page redirected off the approved domain; rejecting.")
                return None
            options = self._parse_district_options(resp.text)
            self._cache_set(cache_key, options)
            logger.debug("Maharashtra Sewa Kendra district options parsed: %s", len(options))
        for value, label in options:
            if self.normalize_district_name(label) == district:
                return value
        return None

    def _fetch_talukas_list(self, client: httpx.Client, district_id: str) -> List[Tuple[str, str]]:
        cache_key: Tuple[str, Any] = ("talukas", str(district_id))
        talukas = self._cache_get(cache_key)
        if talukas is None:
            resp = client.get(
                self.BASE_URL + self.TALUKA_API_PATH,
                params={"DistrictID": str(district_id)},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if resp.status_code != 200 or not self._is_approved_response_url(resp):
                return []
            talukas = self._parse_taluka_json(resp.text)
            self._cache_set(cache_key, talukas)
            logger.debug("Maharashtra Sewa Kendra talukas parsed for district %s: %s", district_id, len(talukas))
        return talukas or []

    def _fetch_taluka_code(self, client: httpx.Client, district_id, taluka: str) -> Optional[str]:
        code, _ = self._fetch_taluka_code_and_others(client, district_id, taluka)
        return code

    def _fetch_taluka_code_and_others(
        self,
        client: httpx.Client,
        district_id,
        taluka: str,
    ) -> Tuple[Optional[str], List[str]]:
        talukas = self._fetch_talukas_list(client, str(district_id))
        if not talukas:
            return None, []

        norm_target = self.normalize_place_name(taluka)
        matched_code = None

        # Exact match only: do not use substring or approximate matching
        for code, name in talukas:
            if self.normalize_place_name(name) == norm_target:
                matched_code = code
                break

        if not matched_code:
            return None, []

        other_talukas = [
            name for code, name in talukas
            if code != matched_code and self.normalize_place_name(name) != norm_target
        ]
        return matched_code, other_talukas

    @classmethod
    def _is_other_taluka_row(
        cls,
        vle_name: str,
        address: str,
        requested_taluka: str,
        other_talukas: List[str],
    ) -> bool:
        """
        Requirement D: Safely inspect row text and filter out centers that explicitly belong
        to other talukas in the district. Never uses weak substring matching.
        """
        norm_taluka = cls.normalize_place_name(requested_taluka)
        full_text = f"{vle_name} {address}".lower()

        # Check if the text explicitly specifies another taluka in the same district
        for ot in other_talukas:
            norm_ot = cls.normalize_place_name(ot)
            if not norm_ot or norm_ot == norm_taluka:
                continue

            # Check for explicit taluka markers: "tal <other>", "taluka <other>", "tehsil <other>", "ta <other>"
            marker_pattern = (
                r'\b(?:tal|taluka|tehsil|tahsil|ta)\s*[:\.\-–/]?\s*'
                + re.escape(norm_ot)
                + r'\b'
            )
            if re.search(marker_pattern, full_text):
                # Ensure it's not a street/road name inside the requested taluka (e.g. "Nashik Kalwan Road, Dindori")
                road_match = re.search(
                    r'\b' + re.escape(norm_ot) + r'\s+(?:road|rd|highway|marg|naka|doar)\b',
                    full_text,
                )
                if road_match and norm_taluka in full_text:
                    continue
                return True

        # When the requested taluka is not "nashik", filter out centers explicitly located in Nashik city / HQ
        if norm_taluka != "nashik":
            nashik_city_markers = [
                "nashik pune road", "cidco", "panchavati", "dwarka",
                "satpur", "gangapur road", "mhasrul", "untwadi",
            ]
            if any(marker in full_text for marker in nashik_city_markers) and norm_taluka not in full_text:
                return True

        return False

    def _fetch_centers(
        self,
        client: httpx.Client,
        state: str,
        district: str,
        taluka: str,
        district_id,
        taluka_code,
        other_talukas: Optional[List[str]] = None,
    ) -> Optional[List[ApplicationLocation]]:
        resp = client.post(
            self.DETAILS_URL,
            data={
                "Districtcode": str(district_id),
                "SubDistrictcode": str(taluka_code),
                "Command": "Proceed",
            },
        )
        if resp.status_code != 200:
            logger.info("Sewa Kendra directory returned status %s for %s/%s", resp.status_code, district, taluka)
            return None
        if not self._is_approved_response_url(resp):
            logger.warning("Sewa Kendra directory POST redirected off the approved domain; rejecting.")
            return None

        cells_rows = self._parse_center_rows(resp.text)
        if not cells_rows:
            logger.info("No Sewa Kendra rows returned for %s/%s", district, taluka)
            return None

        centers: List[ApplicationLocation] = []
        others = other_talukas or []
        for idx, cells in enumerate(cells_rows):
            if len(cells) >= 2 and self._is_other_taluka_row(cells[0], cells[1], taluka, others):
                continue
            center = self._build_location(cells, idx, scheme_id=None, state=state, district=district, taluka=taluka)
            if center is not None:
                centers.append(center)
        return centers or None

    def _build_location(
        self,
        cells: List[str],
        idx: int,
        state: str,
        district: str,
        taluka: str,
        scheme_id: Optional[str] = None,
    ) -> Optional[ApplicationLocation]:
        if len(cells) < 4:
            return None
        vle_name = re.sub(r"\s+", " ", cells[0]).strip()
        if len(vle_name) < 3:
            return None
        raw_address = re.sub(r"\s+", " ", cells[1]).strip(" ,;:-")
        raw_pincode = cells[2].strip()
        raw_mobile = cells[3].strip()

        pincode_match = re.search(r"\b\d{6}\b", raw_pincode) or re.search(r"\b\d{6}\b", raw_address)
        pincode = pincode_match.group(0) if pincode_match else None

        address_parts = [raw_address]
        if taluka and taluka.lower() not in raw_address.lower():
            address_parts.append(f"{taluka.title()} Taluka")
        if district and district.lower() not in raw_address.lower():
            address_parts.append(f"{district.title()} District")
        address_en = ", ".join(address_parts)
        if pincode and pincode not in address_en:
            address_en = f"{address_en} - {pincode}"

        phone = None
        mobile_match = re.search(r"(?:\+?91[\s-]?)?([6-9]\d{9})", raw_mobile)
        if mobile_match:
            phone = raw_mobile.strip()

        office_title = (
            f"Aaple Sarkar Seva Kendra - {vle_name}"
            if "aaple sarkar" not in vle_name.lower()
            else vle_name
        )

        return ApplicationLocation(
            id=f"msk-{district}-{taluka}-{idx + 1}",
            scheme_ids=[scheme_id] if scheme_id else [],
            categories=[],
            state=state,
            district=district,
            taluka=taluka,
            office_name={"en": office_title},
            office_type="citizen_service_center",
            address={"en": address_en},
            contact_phone=phone,
            working_hours={"en": "Mon-Sat: 10:00 AM - 6:00 PM"},
            source_url=self.DETAILS_URL,
            application_method="scheme_designated_application_center",
        )

    # -- parsing helpers ----------------------------------------------------

    @staticmethod
    def _parse_district_options(html: str) -> List[Tuple[str, str]]:
        select = re.search(
            r'<select[^>]*id=["\']ddlDistrict["\'][^>]*>(.*?)</select>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if not select:
            return []
        return [
            (
                value.strip(),
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip(),
            )
            for value, label in re.findall(
                r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
                select.group(1),
                re.IGNORECASE | re.DOTALL,
            )
        ]

    @staticmethod
    def _parse_taluka_json(body: str) -> List[Tuple[str, str]]:
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return []
        if not isinstance(data, list):
            return []
        results: List[Tuple[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            code = str(item.get("SubDistrictcode") or "").strip()
            name = (item.get("SubDistrictname") or "").strip()
            if code in ("", "0") or name.lower() in ("--select--", "--Select--"):
                continue
            results.append((code, name))
        return results

    @staticmethod
    def _parse_center_rows(html: str) -> List[List[str]]:
        anchor = re.search(
            r"<tr[^>]*>\s*<t[dh][^>]*>\s*VLE\s+Name\s*</t[dh]>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if not anchor:
            return []  # No results table found (e.g. "no records" page)
        head_start = anchor.start()
        after_head = html[head_start:].find("</tr>")
        tail = html[head_start + after_head + len("</tr>"):] if after_head != -1 else ""
        table_end = tail.find("</table>")
        if table_end != -1:
            tail = tail[:table_end]

        rows: List[List[str]] = []
        for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", tail, re.IGNORECASE | re.DOTALL):
            cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
                for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_match.group(1), re.IGNORECASE | re.DOTALL)
            ]
            cells = [c for c in cells if c]
            joined = " ".join(cells).lower()
            if not cells or len(cells) < 4 or "vle name" in joined:
                continue
            rows.append(cells)
            if len(rows) >= 2000:
                break
        return rows

    @staticmethod
    def _deduplicate(locations: List[ApplicationLocation]) -> List[ApplicationLocation]:
        seen = set()
        deduped: List[ApplicationLocation] = []
        for loc in locations:
            name = str(loc.office_name.get("en") or "" if isinstance(loc.office_name, dict) else loc.office_name).strip().lower()
            addr = str(loc.address.get("en") or "" if isinstance(loc.address, dict) else loc.address).strip().lower()
            key = (name, addr)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(loc)
        return deduped

    # -- name normalization -------------------------------------------------

    @classmethod
    def normalize_place_name(cls, name: str) -> str:
        s = re.sub(r"\s+", " ", str(name or "").strip()).lower()
        for suffix in cls.PLACE_SUFFIXES:
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
        return s.strip(" .,-")

    @classmethod
    def normalize_district_name(cls, name: str) -> str:
        norm = cls.normalize_place_name(name)
        return cls.DISTRICT_ALIASES.get(norm, norm)

    # -- small lookup cache (district -> options, district -> talukas) -------

    @classmethod
    def _cache_get(cls, key: Tuple[str, Any]) -> Optional[Any]:
        item = cls._lookup_cache.get(key)
        if item is None:
            return None
        ts, value = item
        if time.time() - ts > cls.CACHE_TTL_SECONDS:
            cls._lookup_cache.pop(key, None)
            return None
        return value

    @classmethod
    def _cache_set(cls, key: Tuple[str, Any], value: Any) -> None:
        cls._lookup_cache[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# 7. Multi-Source Government Web Search Provider
# ---------------------------------------------------------------------------

class GovernmentWebSearchProvider(LocationSearchProvider):
    """
    Multi-source official location discoverer:
    Stage 1: Searches and inspects official scheme pages (Source A) to extract authorized application channels.
    Stage 2: Discovers physical offices from official district directories (Source B).
    Stage 3: Corroborates authority type (A) with physical office (B).
    Stage 4: Applies state -> district -> taluka hierarchy filtering.
    Rejects unsupported, non-government, or unverified results.
    """

    def __init__(
        self,
        backend: Optional[SearchBackend] = None,
        http_client: Optional[httpx.Client] = None,
        timeout: float = LIVE_REQUEST_TIMEOUT_SECONDS,
    ):
        self.backend = backend or ExternalSearchAPIProvider()
        self._client = http_client
        self._timeout = timeout

    def _get_http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        )

    def search(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
        scheme: Optional[Scheme] = None,
    ) -> Optional[List[ApplicationLocation]]:
        s_id = scheme_id.strip().lower()
        s_state = state.strip().lower()
        s_dist = district.strip().lower() if district and district.strip() else None
        s_tal = taluka.strip().lower() if taluka and taluka.strip() else None

        scheme_obj = scheme or _load_scheme_by_id(s_id)
        if not scheme_obj and s_id.startswith("web-"):
            scheme_obj = _load_scheme_by_id(s_id[4:])

        scheme_title = s_id
        if scheme_obj:
            if isinstance(scheme_obj.name, dict):
                scheme_title = scheme_obj.name.get("en") or scheme_obj.name.get("hi") or s_id
            else:
                scheme_title = str(scheme_obj.name)
        elif s_id.startswith("web-"):
            scheme_title = s_id[4:].replace("-", " ")

        scheme_authorities: Dict[str, str] = {}
        scheme_auth_url: Optional[str] = None
        discovered_offices: List[ApplicationLocation] = []

        # 1. Check if the scheme's verified guidance or description directly authorizes channels
        scheme_text_chunks: List[str] = []
        if scheme_obj:
            if scheme_obj.custom_application_guidance and scheme_obj.custom_application_guidance.offline_application:
                off = scheme_obj.custom_application_guidance.offline_application
                if off.instructions:
                    scheme_text_chunks.append(str(off.instructions))
                if off.authorized_channel:
                    scheme_text_chunks.append(str(off.authorized_channel))
            if scheme_obj.description:
                if isinstance(scheme_obj.description, dict):
                    scheme_text_chunks.extend([str(v) for v in scheme_obj.description.values()])
                else:
                    scheme_text_chunks.append(str(scheme_obj.description))
            if scheme_obj.required_information:
                if isinstance(scheme_obj.required_information, dict):
                    for v in scheme_obj.required_information.values():
                        if isinstance(v, list):
                            scheme_text_chunks.extend([str(x) for x in v])
                elif isinstance(scheme_obj.required_information, list):
                    scheme_text_chunks.extend([str(x) for x in scheme_obj.required_information])

        if scheme_text_chunks:
            direct_auth = AuthorityExtractionParser.parse_text(" ".join(scheme_text_chunks))
            if direct_auth.is_online_only:
                logger.info("Scheme %s is online-only; suppressing physical locations.", s_id)
                return None
            if direct_auth.designated_authorities:
                scheme_authorities.update(direct_auth.designated_authorities)
                scheme_auth_url = (scheme_obj.application_url or scheme_obj.source_url) if scheme_obj else None

        # 2. Build official candidate URLs to inspect for Source A
        official_candidates: List[Dict[str, str]] = []
        if scheme_obj and s_id.startswith("web-"):
            if scheme_obj.application_url and is_official_gov_domain(scheme_obj.application_url):
                official_candidates.append({"url": scheme_obj.application_url, "title": scheme_title})
            if scheme_obj.source_url and is_official_gov_domain(scheme_obj.source_url) and scheme_obj.source_url != scheme_obj.application_url:
                official_candidates.append({"url": scheme_obj.source_url, "title": scheme_title})

        query = build_official_search_query(scheme_title, s_state, s_dist, s_tal)
        candidates = self.backend.search_candidates(query, max_results=5)
        if candidates is not None and len(candidates) > 0:
            gov_candidates = [
                item for item in candidates
                if is_official_gov_domain(item.get("url", ""))
            ]
            if not gov_candidates and not scheme_authorities:
                logger.info("Search returned candidates but none from official government domains for query: %s", query)
                return None
            for item in gov_candidates:
                if not any(c["url"] == item.get("url") for c in official_candidates):
                    official_candidates.append(item)
        elif not scheme_authorities:
            logger.info("No candidates returned from search and no direct authorities for query: %s", query)
            return None

        if not official_candidates and not scheme_authorities:
            logger.info("No candidates from official government domains found for query: %s", query)
            return None

        client = self._get_http_client()
        portal_parser = OfficialPortalLocationProvider(client=client)

        # -------------------------------------------------------------
        # Stage 1: Inspect official scheme pages (Source A)
        # -------------------------------------------------------------
        for item in official_candidates:
            url = item["url"]
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                if not is_safe_pdf_response(resp):
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                if "html" in content_type or "text" in content_type:
                    auth_result = AuthorityExtractionParser.parse_text(resp.text)
                    if auth_result.is_online_only:
                        logger.info("Scheme %s is online-only; suppressing physical locations.", s_id)
                        return None
                    if auth_result.designated_authorities:
                        scheme_authorities.update(auth_result.designated_authorities)
                        scheme_auth_url = url

                    # Check if the scheme page directly provides physical offices
                    direct_locs = portal_parser._parse_html_directory(
                        resp.text,
                        scheme_id=s_id,
                        state=s_state,
                        district=s_dist,
                        taluka=s_tal,
                        source_url=url,
                    )
                    if direct_locs:
                        discovered_offices.extend(direct_locs)

            except Exception as exc:
                logger.warning("Failed to fetch/parse official candidate page %s: %s", url, exc)
                continue

        # -------------------------------------------------------------
        # Stage 2: Discover physical offices from district directory (Source B)
        # -------------------------------------------------------------
        if s_dist and not discovered_offices:
            district_urls = get_standard_district_directory_urls(s_dist, s_state)
            for d_url in district_urls:
                try:
                    resp = client.get(d_url)
                    if resp.status_code != 200:
                        continue
                    if not is_safe_pdf_response(resp):
                        continue
                    resp_url = getattr(resp, "url", None)
                    final_url = str(resp_url) if isinstance(resp_url, (str, httpx.URL)) else d_url
                    if not is_official_gov_domain(final_url):
                        continue
                    content_type = resp.headers.get("content-type", "").lower()
                    if "json" in content_type:
                        d_locs = portal_parser._parse_json_directory(
                            resp.json(),
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=final_url,
                        )
                    else:
                        d_locs = portal_parser._parse_html_directory(
                            resp.text,
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=final_url,
                        )
                    if d_locs:
                        discovered_offices.extend(d_locs)
                        if any(loc.office_type in scheme_authorities for loc in d_locs):
                            break
                except Exception as exc:
                    logger.debug("Error checking district directory %s: %s", d_url, exc)
                    continue

        # Targeted service-center search if Source A explicitly authorizes citizen_service_center
        has_csc = any(loc.office_type == "citizen_service_center" for loc in discovered_offices)
        if s_dist and scheme_authorities.get("citizen_service_center"):
            if s_state == "maharashtra":
                if s_tal:
                    # Authoritative Maharashtra Aaple Sarkar Sewa Kendra directory (Step 3C).
                    # Server-side district + taluka filtering; never search-engine snippets.
                    try:
                        sewa_centers = MaharashtraSewaKendraProvider(client=self._client).search(
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Maharashtra Sewa Kendra directory search failed (%s/%s): %s",
                            s_dist, s_tal, exc,
                        )
                        sewa_centers = None
                    if sewa_centers:
                        # Authoritative directory replaces any earlier generic CSC/Setu entries.
                        discovered_offices = [
                            loc for loc in discovered_offices
                            if loc.office_type != "citizen_service_center"
                        ]
                        discovered_offices.extend(sewa_centers)
                    else:
                        # If taluka cannot be resolved or yields no centers, remove any earlier generic CSCs
                        # so we do not fall back to district-wide CSC centers.
                        discovered_offices = [
                            loc for loc in discovered_offices
                            if loc.office_type != "citizen_service_center"
                        ]
                else:
                    # When no taluka is supplied, do NOT query or include citizen service centers as district offices.
                    discovered_offices = [
                        loc for loc in discovered_offices
                        if loc.office_type != "citizen_service_center"
                    ]
            elif s_tal and not has_csc:
                service_query_parts = [f"site:{s_dist}.gov.in"]
                service_query_parts.append('("setu kendra" OR "maha e-seva" OR "common service centre")')
                service_query_parts.append(s_tal)
                service_query = " ".join(service_query_parts)
                try:
                    service_candidates = self.backend.search_candidates(service_query, max_results=3)
                    for cand in service_candidates:
                        cand_url = cand.get("url", "")
                        if not is_official_gov_domain(cand_url):
                            continue
                        try:
                            resp = client.get(cand_url)
                            if resp.status_code != 200 or not is_safe_pdf_response(resp):
                                continue
                            resp_url = getattr(resp, "url", None)
                            final_url = str(resp_url) if isinstance(resp_url, (str, httpx.URL)) else cand_url
                            if not is_official_gov_domain(final_url):
                                continue
                            content_type = resp.headers.get("content-type", "").lower()
                            if "json" in content_type:
                                s_locs = portal_parser._parse_json_directory(
                                    resp.json(),
                                    scheme_id=s_id,
                                    state=s_state,
                                    district=s_dist,
                                    taluka=s_tal,
                                    source_url=final_url,
                                )
                            else:
                                s_locs = portal_parser._parse_html_directory(
                                    resp.text,
                                    scheme_id=s_id,
                                    state=s_state,
                                    district=s_dist,
                                    taluka=s_tal,
                                    source_url=final_url,
                                )
                            if s_locs:
                                discovered_offices.extend(s_locs)
                                break
                        except Exception as exc:
                            logger.debug("Error checking service-center candidate %s: %s", cand_url, exc)
                            continue
                except Exception as exc:
                    logger.warning("Error during service-center search for %s: %s", s_dist, exc)

        if not discovered_offices:
            return None

        # -------------------------------------------------------------
        # Stage 3: Corroborate Authority (Source A) + Office (Source B)
        # -------------------------------------------------------------
        corroborated: List[ApplicationLocation] = []
        for loc in discovered_offices:
            if scheme_authorities:
                if loc.office_type in scheme_authorities:
                    loc.application_method = scheme_authorities[loc.office_type]
                    loc.scheme_authorization_url = scheme_auth_url
                    corroborated.append(loc)
                elif loc.office_type in ("collectorate", "tahsil_office") and "general_government_assistance" in scheme_authorities.values():
                    loc.application_method = "general_government_assistance"
                    loc.scheme_authorization_url = scheme_auth_url
                    corroborated.append(loc)
            else:
                # If Source A did NOT authorize offline channels, do not falsely present
                # a random district office as a scheme-specific application center!
                pass

        if not corroborated:
            return None

        # -------------------------------------------------------------
        # Stage 4: Hierarchy filtering
        # -------------------------------------------------------------
        return filter_locations_hierarchy(
            corroborated,
            state=s_state,
            district=s_dist,
            taluka=s_tal,
        )


# ---------------------------------------------------------------------------
# 8. Deterministic In-Memory Cache
# ---------------------------------------------------------------------------

class SimpleLocationCache:
    """
    Deterministic in-memory bounded cache for location search results.
    Prevents redundant web requests and provides instant responses.
    """

    def __init__(self, max_size: int = 128):
        self.max_size = max_size
        self._cache: Dict[str, ApplicationOptionsResult] = {}
        self._order: List[str] = []

    def _key(self, scheme_id: str, state: str, district: Optional[str], taluka: Optional[str]) -> str:
        s_id = (scheme_id or "").strip().lower()
        s_st = (state or "").strip().lower()
        s_dst = (district or "").strip().lower()
        s_tlk = (taluka or "").strip().lower()
        return f"{s_id}|{s_st}|{s_dst}|{s_tlk}"

    def get(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str] = None,
        taluka: Optional[str] = None,
    ) -> Optional[ApplicationOptionsResult]:
        k = self._key(scheme_id, state, district, taluka)
        return self._cache.get(k)

    def set(
        self,
        scheme_id: str,
        state: str,
        district: Optional[str],
        taluka: Optional[str],
        result: ApplicationOptionsResult,
    ) -> None:
        k = self._key(scheme_id, state, district, taluka)
        if k in self._cache:
            self._cache[k] = result
            return
        if len(self._order) >= self.max_size:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)
        self._order.append(k)
        self._cache[k] = result

    def clear(self) -> None:
        self._cache.clear()
        self._order.clear()


_LOCATION_CACHE = SimpleLocationCache(max_size=128)


def get_location_cache() -> SimpleLocationCache:
    """Returns the global location search cache."""
    return _LOCATION_CACHE


def clear_location_cache() -> None:
    """Clears the location search cache."""
    _LOCATION_CACHE.clear()


# ---------------------------------------------------------------------------
# 9. Scheme Metadata Loader
# ---------------------------------------------------------------------------

def _load_scheme_by_id(scheme_id: str) -> Optional[Scheme]:
    """Helper to retrieve scheme metadata from the central schemes catalog."""
    from app.main import load_schemes_data
    schemes = load_schemes_data()
    target = scheme_id.strip().lower()
    for s in schemes:
        if s.id.strip().lower() == target:
            return s
    if target.startswith("web-"):
        stripped = target[4:]
        for s in schemes:
            if s.id.strip().lower() == stripped:
                return s
    return None


# ---------------------------------------------------------------------------
# 10. Unified Application Options Entrypoint
# ---------------------------------------------------------------------------

def find_application_options(
    scheme_id: str,
    state: str,
    district: Optional[str] = None,
    taluka: Optional[str] = None,
    live_provider: Optional[LocationSearchProvider] = None,
    fallback_pool: Optional[List[ApplicationLocation]] = None,
    use_cache: bool = True,
    scheme: Optional[Scheme] = None,
) -> ApplicationOptionsResult:
    """
    Unified entrypoint for finding both online and physical application options.

    Flow:
    1. Check bounded cache if enabled.
    2. Resolve online portal from verified scheme metadata.
    3. Attempt official live web source search (Direct official portal + Multi-source web search).
    4. If unverified, unavailable, or timing out, fall back to locations.json.
    5. Return structured ApplicationOptionsResult without fabricating data.
    """
    s_id = (scheme_id or "").strip().lower()
    s_state = (state or "").strip().lower()
    s_dist = district.strip().lower() if district and district.strip() and district.strip().lower() != "other" else None
    s_tal = taluka.strip().lower() if taluka and taluka.strip() and taluka.strip().lower() != "other" else None

    # Step 0: Check cache
    if use_cache:
        cached = _LOCATION_CACHE.get(s_id, s_state, s_dist, s_tal)
        if cached is not None:
            return cached

    # Retrieve scheme metadata
    scheme_obj = scheme or (_load_scheme_by_id(s_id) if s_id else None)

    online_app = OnlineApplication(available=False)
    official_source_url = None

    if scheme_obj:
        online_app = scheme_obj.application_guidance.online_application
        official_source_url = scheme_obj.application_url or scheme_obj.source_url

    if not s_id or not s_state:
        result = ApplicationOptionsResult(
            scheme_id=s_id,
            state=s_state,
            district=s_dist,
            taluka=s_tal,
            online_application=online_app,
            physical_locations=[],
            source_type="none",
            official_source_url=official_source_url,
            verification_status="none",
        )
        if use_cache:
            _LOCATION_CACHE.set(s_id, s_state, s_dist, s_tal, result)
        return result

    # -------------------------------------------------------------
    # Step 1: Attempt Live Official Source Search (time-bounded)
    # -------------------------------------------------------------
    # All live provider attempts are guarded by a strict wall-clock budget.
    # If a government portal is slow or unreachable (common on cloud egress),
    # we break out of the loop immediately and fall through to locations.json
    # rather than letting a single request hang for 30+ seconds.
    live_providers: List[LocationSearchProvider] = []
    if live_provider is not None:
        live_providers = [live_provider]
    else:
        live_providers = [
            # GovernmentWebSearchProvider runs first: it corroborates physical offices against
            # scheme-authorization (Source A) and, for Maharashtra CSC-authorized schemes, uses
            # the authoritative Aaple Sarkar Sewa Kendra directory before generic portal offices.
            GovernmentWebSearchProvider(),
            OfficialPortalLocationProvider(),
        ]

    live_deadline = time.monotonic() + LIVE_DISCOVERY_BUDGET_SECONDS
    for provider in live_providers:
        if time.monotonic() >= live_deadline:
            logger.info(
                "Live discovery budget exhausted for %s (%s); skipping remaining providers.",
                s_id, s_state,
            )
            break
        try:
            try:
                live_locations = provider.search(
                    scheme_id=s_id,
                    state=s_state,
                    district=s_dist,
                    taluka=s_tal,
                    scheme=scheme_obj,
                )
            except TypeError:
                live_locations = provider.search(
                    scheme_id=s_id,
                    state=s_state,
                    district=s_dist,
                    taluka=s_tal,
                )
            if live_locations and len(live_locations) > 0:
                result = ApplicationOptionsResult(
                    scheme_id=s_id,
                    state=s_state,
                    district=s_dist,
                    taluka=s_tal,
                    online_application=online_app,
                    physical_locations=live_locations,
                    source_type="live_official_source",
                    official_source_url=live_locations[0].source_url or official_source_url,
                    verification_status="live_verified",
                )
                if use_cache:
                    _LOCATION_CACHE.set(s_id, s_state, s_dist, s_tal, result)
                return result
        except Exception as exc:
            logger.warning(
                "Live location search error via %s for %s (%s): %s",
                type(provider).__name__, s_id, s_state, exc,
            )

    # -------------------------------------------------------------
    # Step 2: Fallback to Local Verified Catalog (locations.json)
    # -------------------------------------------------------------
    fallback_locations = find_locations(
        scheme_id=s_id,
        state=s_state,
        district=s_dist,
        taluka=s_tal,
        locations_pool=fallback_pool,
    )
    if (not fallback_locations) and s_id.startswith("web-"):
        fallback_locations = find_locations(
            scheme_id=s_id[4:],
            state=s_state,
            district=s_dist,
            taluka=s_tal,
            locations_pool=fallback_pool,
        )

    if fallback_locations and len(fallback_locations) > 0:
        result = ApplicationOptionsResult(
            scheme_id=s_id,
            state=s_state,
            district=s_dist,
            taluka=s_tal,
            online_application=online_app,
            physical_locations=fallback_locations,
            source_type="local_catalog_fallback",
            official_source_url=fallback_locations[0].source_url or official_source_url,
            verification_status="catalog_fallback",
        )
        if use_cache:
            _LOCATION_CACHE.set(s_id, s_state, s_dist, s_tal, result)
        return result

    # -------------------------------------------------------------
    # Step 3: No physical locations found
    # -------------------------------------------------------------
    result = ApplicationOptionsResult(
        scheme_id=s_id,
        state=s_state,
        district=s_dist,
        taluka=s_tal,
        online_application=online_app,
        physical_locations=[],
        source_type="none",
        official_source_url=official_source_url,
        verification_status="none",
    )
    if use_cache:
        _LOCATION_CACHE.set(s_id, s_state, s_dist, s_tal, result)
    return result
