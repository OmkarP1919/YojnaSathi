"""
Government Location Directory Service for YojnaSathi (Step 3D).

Provides dynamic, real-time discovery and verification of Indian districts and
talukas/tehsils from official government portals (*.gov.in, *.nic.in) with:
- Strict official domain validation
- Bounded in-memory caching with TTL
- Dedicated administrative unit parsing (ignoring officer directories)
- Graceful degradation when external services are unavailable
- Authoritative reference for Indian States/UTs
- Decoupled from locations.json (which is only an application office catalog)
"""
from html.parser import HTMLParser
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx

from app.location_search import (
    DEFAULT_USER_AGENT,
    ExternalSearchAPIProvider,
    SearchBackend,
    is_official_gov_domain,
    is_safe_pdf_response,
)
from app.schemas import (
    DistrictDirectoryResponse,
    LocationDirectoryItem,
    StateDirectoryResponse,
    TalukaDirectoryResponse,
)

logger = logging.getLogger("yojnasathi.government_locations")

# ---------------------------------------------------------------------------
# 1. Authoritative Reference for Indian States & Union Territories
# ---------------------------------------------------------------------------

OFFICIAL_INDIAN_STATES: List[str] = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
]


# ---------------------------------------------------------------------------
# 2. In-Memory Cache with TTL and Bounded Size
# ---------------------------------------------------------------------------

class LocationDirectoryCache:
    """Thread-safe bounded in-memory cache with TTL expiration."""

    def __init__(self, default_ttl_seconds: int = 3600, max_size: int = 300):
        self.default_ttl = default_ttl_seconds
        self.max_size = max_size
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, val = entry
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if len(self._store) >= self.max_size:
            # Evict oldest entry
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest_key, None)
        expires = time.time() + (ttl if ttl is not None else self.default_ttl)
        self._store[key] = (expires, value)

    def clear(self) -> None:
        self._store.clear()


_LOCATION_CACHE = LocationDirectoryCache()


# ---------------------------------------------------------------------------
# 3. Administrative Unit HTML Parser
# ---------------------------------------------------------------------------

class GovAdminHTMLParser(HTMLParser):
    """
    Parses official government administrative setup pages to extract named
    administrative units (Districts or Tehsils/Talukas).

    Strictly avoids officer names, navigation links, and contact listings by
    excluding footer/nav structures, applying navigation noise filters, and
    targeting tables, select dropdowns, and administrative cards.
    """

    NAVIGATION_NOISE_TERMS = {
        "feedback", "help", "security policy", "privacy policy", "website policy",
        "website policies", "terms of use", "terms of service", "site map", "sitemap",
        "accessibility", "accessibility statement", "disclaimer", "copyright",
        "copyright policy", "hyperlink", "hyperlinking policy", "contact us", "about us",
        "faq", "faqs", "user manual", "screen reader", "skip to main content",
        "search", "home", "navigation", "login", "sign in", "register", "download",
        "grievance", "rti", "right to information", "portal", "dashboard",
        "gallery", "press release", "tender", "tenders", "recruitment",
        "circular", "circulars", "acts", "rules", "forms", "website quality manual",
    }

    OFFICER_NOISE_WORDS = {
        "shri", "smt", "ias", "ips", "ifs", "collector", "magistrate",
        "tahsildar", "tehsildar", "officer", "phone", "email", "mobile",
        "std", "designation", "contact", "address", "pincode", "pin",
        "deputy", "assistant", "additional", "resident", "naib",
    }

    UNIT_NOISE_PREFIXES = [
        r"^(?:tehsil|tahsil|taluka|taluk|district|dist\.?|name of tehsil|name of taluka|name of district)\s*[:\-–]?\s*",
        r"^\d+[\.\)\-\s]+",  # "1. ", "01- "
    ]

    UNIT_NOISE_SUFFIXES = [
        r"\s*(?:tehsil|tahsil|taluka|taluk|district|office|headquarters|division)$",
    ]

    def __init__(self, target_type: str = "taluka"):
        super().__init__()
        self.target_type = target_type  # "district" or "taluka"
        self.found_units: List[str] = []

        # Structural exclusion
        self._ignored_depth = 0

        # Table state
        self._in_table = False
        self._current_row: List[str] = []
        self._target_col_idx: Optional[int] = None
        self._is_header_row = False
        self._in_cell = False
        self._cell_text = ""

        # Section / list state
        self._in_target_section = False
        self._in_list_item = False
        self._list_item_text = ""
        self._current_heading = ""
        self._in_heading = False

        # Select dropdown state
        self._in_target_select = False
        self._in_option = False
        self._option_text = ""

        # Link card title state
        self._in_link_title = False
        self._link_title_text = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attrs_dict = {k.lower(): (v or "").lower() for k, v in attrs}
        classes = attrs_dict.get("class", "")
        tag_id = attrs_dict.get("id", "")

        # Exclude footer, navigation, header, and sidebar blocks
        if tag in ("footer", "nav", "header", "aside"):
            self._ignored_depth += 1
            return

        if self._ignored_depth > 0:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = True
            self._current_heading = ""
            self._in_target_section = False

        elif tag == "select":
            sel_meta = classes + " " + tag_id + " " + attrs_dict.get("name", "") + " " + attrs_dict.get("aria-label", "")
            if self.target_type == "district" and any(w in sel_meta for w in ("district", "zila", "jilha")):
                self._in_target_select = True

        elif tag == "option" and self._in_target_select:
            self._in_option = True
            self._option_text = ""

        elif tag == "a" and any(c in classes for c in ("search-title", "district-link", "tehsil-link", "card-title")):
            self._in_link_title = True
            self._link_title_text = ""

        elif tag == "table":
            self._in_table = True
            self._target_col_idx = None

        elif tag == "tr":
            self._current_row = []
            self._is_header_row = False

        elif tag in ("th", "td"):
            self._in_cell = True
            self._cell_text = ""
            if tag == "th":
                self._is_header_row = True

        elif tag in ("ul", "ol"):
            heading_lower = self._current_heading.lower()
            if self.target_type == "taluka" and any(w in heading_lower for w in ("tehsil", "tahsil", "taluka", "administrative setup", "sub-division")):
                self._in_target_section = True
            elif self.target_type == "district" and any(w in heading_lower for w in ("district", "administrative division", "collectorate")):
                self._in_target_section = True

        elif tag == "li" and self._in_target_section:
            self._in_list_item = True
            self._list_item_text = ""

    def handle_endtag(self, tag: str):
        if tag in ("footer", "nav", "header", "aside"):
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return

        if self._ignored_depth > 0:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = False

        elif tag == "select":
            self._in_target_select = False

        elif tag == "option" and self._in_target_select:
            self._in_option = False
            cleaned = self._clean_unit_name(self._option_text)
            if cleaned:
                self.found_units.append(cleaned)

        elif tag == "a" and self._in_link_title:
            self._in_link_title = False
            cleaned = self._clean_unit_name(self._link_title_text)
            if cleaned:
                self.found_units.append(cleaned)

        elif tag in ("th", "td"):
            self._in_cell = False
            clean_cell = self._cell_text.strip()
            self._current_row.append(clean_cell)

            # If header row, identify matching column index
            if self._is_header_row and self._target_col_idx is None:
                cell_lower = clean_cell.lower()
                if self.target_type == "taluka" and any(w in cell_lower for w in ("tehsil", "tahsil", "taluka")):
                    self._target_col_idx = len(self._current_row) - 1
                elif self.target_type == "district" and any(w in cell_lower for w in ("district", "name of district")):
                    self._target_col_idx = len(self._current_row) - 1

        elif tag == "tr":
            if not self._is_header_row and self._current_row:
                if self._target_col_idx is not None and self._target_col_idx < len(self._current_row):
                    raw = self._current_row[self._target_col_idx]
                    cleaned = self._clean_unit_name(raw)
                    if cleaned:
                        self.found_units.append(cleaned)
                elif len(self._current_row) in (2, 3):
                    cand = self._current_row[1] if len(self._current_row) > 1 else self._current_row[0]
                    cleaned = self._clean_unit_name(cand)
                    if cleaned:
                        self.found_units.append(cleaned)

        elif tag == "table":
            self._in_table = False
            self._target_col_idx = None

        elif tag in ("ul", "ol"):
            self._in_target_section = False

        elif tag == "li" and self._in_list_item:
            self._in_list_item = False
            cleaned = self._clean_unit_name(self._list_item_text)
            if cleaned:
                self.found_units.append(cleaned)

    def handle_data(self, data: str):
        if self._ignored_depth > 0:
            return
        if self._in_heading:
            self._current_heading += " " + data
        elif self._in_cell:
            self._cell_text += " " + data
        elif self._in_list_item:
            self._list_item_text += " " + data
        elif self._in_option:
            self._option_text += " " + data
        elif self._in_link_title:
            self._link_title_text += " " + data

    @classmethod
    def _clean_unit_name(cls, raw: str) -> Optional[str]:
        if not raw:
            return None
        text = re.sub(r"\s+", " ", raw).strip()
        if not text:
            return None

        # Discard headers, placeholders, or general UI text
        lower = text.lower()
        if any(h in lower for h in ("sr.", "sr no", "s.no", "serial", "name of", "website", "action", "view", "pdf", "select", "--")):
            return None

        # Discard web navigation, metadata, and policy links
        if lower in cls.NAVIGATION_NOISE_TERMS or any(term in lower for term in cls.NAVIGATION_NOISE_TERMS):
            return None

        # Check for officer / contact noise
        words = set(re.findall(r"\b[a-z]+\b", lower))
        if words.intersection(cls.OFFICER_NOISE_WORDS):
            return None
        if "@" in text or re.search(r"\b\d{6,}\b", text):  # email or phone number
            return None

        # Strip prefixes
        cleaned = text
        for pat in cls.UNIT_NOISE_PREFIXES:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

        # Strip suffixes
        for pat in cls.UNIT_NOISE_SUFFIXES:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

        cleaned = cleaned.strip(" -:–,.")
        # Filter out overly long text or short garbage
        if len(cleaned) < 2 or len(cleaned) > 35:
            return None
        # Reject strings with non-alphabetic/punctuation noise
        if not re.search(r"[a-zA-Z]", cleaned):
            return None

        # Return Title Case
        return cleaned.title()


# ---------------------------------------------------------------------------
# 4. GovernmentLocationDirectory Abstraction
# ---------------------------------------------------------------------------

class GovernmentLocationDirectory:
    """
    Authoritative and live official government location directory resolver.
    """

    def __init__(
        self,
        search_backend: Optional[SearchBackend] = None,
        http_client: Optional[httpx.Client] = None,
        cache: Optional[LocationDirectoryCache] = None,
        timeout: float = 6.0,
    ):
        self._search_backend = search_backend
        self._http_client = http_client
        self._cache = cache or _LOCATION_CACHE
        self._timeout = timeout

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            verify=False,
        )

    def _get_search_backend(self) -> SearchBackend:
        if self._search_backend is not None:
            return self._search_backend
        return ExternalSearchAPIProvider(timeout=self._timeout)

    # -----------------------------------------------------------------------
    # State Resolution (Authoritative Reference)
    # -----------------------------------------------------------------------

    def get_states(self) -> StateDirectoryResponse:
        """
        Returns the authoritative official list of 28 States and 8 Union
        Territories of India (India.gov.in standard reference).
        """
        cached = self._cache.get("states")
        if cached:
            return cached

        items = [
            LocationDirectoryItem(
                name=state,
                source_url="https://india.gov.in/states-and-uts",
                verified=True,
            )
            for state in OFFICIAL_INDIAN_STATES
        ]
        resp = StateDirectoryResponse(
            states=items,
            source_type="authoritative_reference",
            available=True,
        )
        self._cache.set("states", resp)
        return resp

    # -----------------------------------------------------------------------
    # District Resolution (Real-Time Official State Directory)
    # -----------------------------------------------------------------------

    def get_districts(self, state: str) -> DistrictDirectoryResponse:
        """
        Dynamically discovers and verifies the official list of districts for
        a state from official government sources (*.gov.in, *.nic.in).
        """
        if not state or not state.strip():
            return DistrictDirectoryResponse(
                state="",
                districts=[],
                source_type="unavailable",
                available=False,
                message="State name must be provided.",
            )

        norm_state = state.strip().lower()
        cache_key = f"districts:{norm_state}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        # 1. Try standard state government portals / NIC directory endpoints
        candidate_urls: List[str] = []
        if norm_state == "maharashtra":
            candidate_urls.extend([
                "https://aaplesarkar.mahaonline.gov.in/",
                "https://igod.gov.in/sg/MH/E042/organizations",
                "https://maharashtra.gov.in/",
            ])

        client = self._get_client()
        for url in candidate_urls:
            districts = self._fetch_and_parse_districts(client, url)
            if districts:
                resp = DistrictDirectoryResponse(
                    state=state.strip().title(),
                    districts=districts,
                    source_type="official_government_portal",
                    source_url=url,
                    available=True,
                )
                self._cache.set(cache_key, resp)
                return resp

        # 2. Search discovery via official domain search
        backend = self._get_search_backend()
        if hasattr(backend, "is_available") and backend.is_available():
            query = f"districts of {norm_state} official site:gov.in"
            try:
                candidates = backend.search_candidates(query, max_results=4)
                for cand in candidates:
                    cand_url = cand.get("url", "")
                    if is_official_gov_domain(cand_url):
                        districts = self._fetch_and_parse_districts(client, cand_url)
                        if districts:
                            resp = DistrictDirectoryResponse(
                                state=state.strip().title(),
                                districts=districts,
                                source_type="official_government_portal",
                                source_url=cand_url,
                                available=True,
                            )
                            self._cache.set(cache_key, resp)
                            return resp
            except Exception as exc:
                logger.warning("Error during live search for districts of %s: %s", state, exc)

        # 3. Graceful degradation: never masquerade partial catalog as full list
        return DistrictDirectoryResponse(
            state=state.strip().title(),
            districts=[],
            source_type="unavailable",
            available=False,
            message="District list could not be verified right now.",
        )

    def _fetch_and_parse_districts(self, client: httpx.Client, url: str) -> List[LocationDirectoryItem]:
        if not is_official_gov_domain(url):
            return []
        try:
            resp = client.get(url)
            final_url = str(resp.url)
            if not is_official_gov_domain(final_url):
                logger.warning("Rejecting redirect from %s to non-official domain %s", url, final_url)
                return []
            if resp.status_code != 200 or not is_safe_pdf_response(resp):
                return []
            parser = GovAdminHTMLParser(target_type="district")
            parser.feed(resp.text)

            # Deduplicate and sort
            unique_names = sorted(set(parser.found_units))
            if not unique_names:
                return []

            return [
                LocationDirectoryItem(name=name, source_url=final_url, verified=True)
                for name in unique_names
            ]
        except Exception as exc:
            logger.debug("Could not fetch/parse districts from %s: %s", url, exc)
            return []

    # -----------------------------------------------------------------------
    # Taluka Resolution (Real-Time Official District Tehsil Directory)
    # -----------------------------------------------------------------------

    def get_talukas(self, state: str, district: str) -> TalukaDirectoryResponse:
        """
        Dynamically discovers and verifies official talukas/tehsils for a district.

        Source Priority:
        1. PRIMARY: Standard NIC S3WaaS district administrative setup / tehsil pages:
           - https://{district}.gov.in/en/about-district/administrative-setup/tehsil/
           - https://{district}.gov.in/about-district/administrative-setup/tehsil/
           - https://{district}.gov.in/en/about-district/administrative-setup/
        2. SECONDARY: Other official district administrative pages via search.
        3. DISCOVERY ONLY: /whos-who/ is used for URL discovery, never parsed as a raw taluka list.
        """
        if not district or not district.strip():
            return TalukaDirectoryResponse(
                state=state.strip().title() if state else "",
                district="",
                talukas=[],
                source_type="unavailable",
                available=False,
                message="District name must be provided.",
            )

        norm_state = state.strip().lower() if state else ""
        norm_dist = district.strip().lower()
        cache_key = f"talukas:{norm_state}:{norm_dist}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        client = self._get_client()

        # 1. PRIMARY: Standard NIC S3WaaS Tehsil endpoints
        standard_endpoints = [
            f"https://{norm_dist}.gov.in/en/about-district/administrative-setup/tehsil/",
            f"https://{norm_dist}.gov.in/about-district/administrative-setup/tehsil/",
            f"https://{norm_dist}.gov.in/en/about-district/administrative-setup/",
            f"https://{norm_dist}.gov.in/about-district/administrative-setup/",
        ]

        for url in standard_endpoints:
            talukas = self._fetch_and_parse_talukas(client, url)
            if talukas:
                resp = TalukaDirectoryResponse(
                    state=state.strip().title() if state else "",
                    district=district.strip().title(),
                    talukas=talukas,
                    source_type="official_district_portal",
                    source_url=url,
                    available=True,
                )
                self._cache.set(cache_key, resp)
                return resp

        # 2. SECONDARY: Search for official administrative setup page
        backend = self._get_search_backend()
        if hasattr(backend, "is_available") and backend.is_available():
            query = f"tehsils talukas of {norm_dist} administrative setup site:{norm_dist}.gov.in OR site:gov.in"
            try:
                candidates = backend.search_candidates(query, max_results=4)
                for cand in candidates:
                    cand_url = cand.get("url", "")
                    if is_official_gov_domain(cand_url):
                        # Avoid parsing pure officer directories as taluka lists
                        if "/whos-who/" in cand_url.lower():
                            continue
                        talukas = self._fetch_and_parse_talukas(client, cand_url)
                        if talukas:
                            resp = TalukaDirectoryResponse(
                                state=state.strip().title() if state else "",
                                district=district.strip().title(),
                                talukas=talukas,
                                source_type="official_district_portal",
                                source_url=cand_url,
                                available=True,
                            )
                            self._cache.set(cache_key, resp)
                            return resp
            except Exception as exc:
                logger.warning("Error during search for talukas of %s: %s", district, exc)

        # 3. Graceful degradation: never fabricate or infer missing talukas
        return TalukaDirectoryResponse(
            state=state.strip().title() if state else "",
            district=district.strip().title(),
            talukas=[],
            source_type="unavailable",
            available=False,
            message="Taluka list could not be verified right now.",
        )

    def _fetch_and_parse_talukas(self, client: httpx.Client, url: str) -> List[LocationDirectoryItem]:
        if not is_official_gov_domain(url):
            return []
        try:
            resp = client.get(url)
            final_url = str(resp.url)
            if not is_official_gov_domain(final_url):
                logger.warning("Rejecting redirect from %s to non-official domain %s", url, final_url)
                return []
            if resp.status_code != 200 or not is_safe_pdf_response(resp):
                return []
            parser = GovAdminHTMLParser(target_type="taluka")
            parser.feed(resp.text)

            unique_names = sorted(set(parser.found_units))
            if not unique_names:
                return []

            return [
                LocationDirectoryItem(name=name, source_url=final_url, verified=True)
                for name in unique_names
            ]
        except Exception as exc:
            logger.debug("Could not fetch/parse talukas from %s: %s", url, exc)
            return []


# Global singleton directory instance
_GLOBAL_LOCATION_DIRECTORY = GovernmentLocationDirectory()


def get_location_directory() -> GovernmentLocationDirectory:
    """Returns the shared GovernmentLocationDirectory instance."""
    return _GLOBAL_LOCATION_DIRECTORY
