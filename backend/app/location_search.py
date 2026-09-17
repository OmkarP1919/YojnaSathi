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
from typing import Any, Dict, List, Optional
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
    """
    s_dist = district.strip().lower()
    base = OFFICIAL_DISTRICT_PORTALS.get(s_dist, f"https://{s_dist}.gov.in")
    return [
        f"{base}/en/whos-who/",
        f"{base}/whos-who/",
        f"{base}/en/about-district/administrative-setup/tehsil/",
        f"{base}/about-district/administrative-setup/tehsil/",
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
        "citizen_service_center": ["setu kendra", "setu", "csc", "common service centre", "common service center", "maha e-seva", "maha eseva", "citizen facilitation"],
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
            if loc_tal and loc_tal != s_tal:
                continue
        else:
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
        timeout: float = 5.0,
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
        elif "setu" in t or "csc" in t or "seva" in t or "citizen center" in t:
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
            raw_address = row[1] if len(row) > 2 else (row[1] if len(row) == 2 and row[1] != office_name else "")

            if len(office_name.strip()) < 4 or (not raw_address.strip() and not phone):
                continue

            address = raw_address.strip() or f"{office_name}, {district or state}"
            loc_taluka = taluka if (taluka and taluka.lower() in row_text.lower()) else None

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

        return locations if locations else None

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
        timeout: float = 5.0,
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
    ) -> Optional[List[ApplicationLocation]]:
        s_id = scheme_id.strip().lower()
        s_state = state.strip().lower()
        s_dist = district.strip().lower() if district and district.strip() else None
        s_tal = taluka.strip().lower() if taluka and taluka.strip() else None

        scheme = _load_scheme_by_id(s_id)
        scheme_title = s_id
        if scheme:
            if isinstance(scheme.name, dict):
                scheme_title = scheme.name.get("en") or s_id
            else:
                scheme_title = str(scheme.name)

        query = build_official_search_query(scheme_title, s_state, s_dist, s_tal)

        candidates = self.backend.search_candidates(query, max_results=5)
        if not candidates:
            return None

        # Filter strictly to official government domains (*.gov.in, *.nic.in)
        official_candidates = [
            item for item in candidates
            if is_official_gov_domain(item.get("url", ""))
        ]
        if not official_candidates:
            logger.info("No candidates from official government domains found for query: %s", query)
            return None

        client = self._get_http_client()
        portal_parser = OfficialPortalLocationProvider(client=client)

        scheme_authorities: Dict[str, str] = {}
        scheme_auth_url: Optional[str] = None
        discovered_offices: List[ApplicationLocation] = []

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
                    content_type = resp.headers.get("content-type", "").lower()
                    if "json" in content_type:
                        d_locs = portal_parser._parse_json_directory(
                            resp.json(),
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=d_url,
                        )
                    else:
                        d_locs = portal_parser._parse_html_directory(
                            resp.text,
                            scheme_id=s_id,
                            state=s_state,
                            district=s_dist,
                            taluka=s_tal,
                            source_url=d_url,
                        )
                    if d_locs:
                        discovered_offices.extend(d_locs)
                        break
                except Exception as exc:
                    logger.debug("Error checking district directory %s: %s", d_url, exc)
                    continue

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
    scheme = _load_scheme_by_id(s_id) if s_id else None

    online_app = OnlineApplication(available=False)
    official_source_url = None

    if scheme:
        online_app = scheme.application_guidance.online_application
        official_source_url = scheme.application_url or scheme.source_url

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
    # Step 1: Attempt Live Official Source Search
    # -------------------------------------------------------------
    live_providers: List[LocationSearchProvider] = []
    if live_provider is not None:
        live_providers = [live_provider]
    else:
        live_providers = [
            OfficialPortalLocationProvider(),
            GovernmentWebSearchProvider(),
        ]

    for provider in live_providers:
        try:
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
            logger.warning("Live location search error via %s for %s (%s): %s", type(provider).__name__, s_id, s_state, exc)

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
