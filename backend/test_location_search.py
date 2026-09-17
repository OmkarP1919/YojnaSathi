"""
Targeted tests for Location Web Search Service (app.location_search).
Covers all 16 required test scenarios:
1. Search query construction includes scheme + state + district + taluka.
2. Official government-domain filtering.
3. Candidate page parsing.
4. Unverified/non-government candidate rejection.
5. Correct state filtering.
6. Correct district filtering.
7. Correct taluka filtering.
8. District-level office remains valid when taluka is supplied.
9. No fabricated location when page lacks address/contact information.
10. Live provider unavailable -> locations.json fallback.
11. Live provider timeout -> fallback.
12. Live provider returns unverified results -> fallback.
13. Online portal remains available when no physical location is found.
14. Deterministic in-memory cache behavior.
15. Existing locations.py behavior unaffected.
16. API endpoint GET /api/application-options works as expected.
"""
import pytest
from typing import List, Optional
from unittest.mock import MagicMock
import httpx
from fastapi.testclient import TestClient

from app.location_search import (
    GovDirectoryHTMLParser,
    LocationSearchProvider,
    SearchBackend,
    OfficialPortalLocationProvider,
    ExternalSearchAPIProvider,
    SerperSearchBackend,
    GoogleCSESearchBackend,
    GovernmentWebSearchProvider,
    AuthorityExtractionParser,
    AuthorityExtractionResult,
    get_standard_district_directory_urls,
    is_safe_pdf_response,
    build_official_search_query,
    is_official_gov_domain,
    filter_locations_hierarchy,
    find_application_options,
    clear_location_cache,
)
from app.locations import find_locations, load_locations_data
from app.main import app
from app.schemas import (
    ApplicationLocation,
    ApplicationOptionsResult,
    OnlineApplication,
)


@pytest.fixture(autouse=True)
def clean_cache_before_each_test():
    """Ensure cache isolation across all unit tests."""
    clear_location_cache()
    yield
    clear_location_cache()


@pytest.fixture
def client():
    return TestClient(app)


SAMPLE_GOV_HTML_DIRECTORY = """
<!DOCTYPE html>
<html>
<head><title>District Directory - Nashik</title></head>
<body>
<h1>Public Services Directory</h1>
<table class="directory-table">
    <thead>
        <tr>
            <th>Office Name</th>
            <th>Address</th>
            <th>Contact</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Tahsil Office Dindori</td>
            <td>Main Road, Dindori, Nashik, Maharashtra 422202</td>
            <td>02557-221234</td>
        </tr>
        <tr>
            <td>District Agriculture Office</td>
            <td>Krishi Bhavan, Old Agra Road, Nashik 422002</td>
            <td>0253-2591234</td>
        </tr>
        <tr>
            <td>Civil Hospital Nashik</td>
            <td>Trimbak Road, Nashik 422001</td>
            <td>0253-2572345</td>
        </tr>
    </tbody>
</table>
</body>
</html>
"""

SAMPLE_GOV_JSON_DIRECTORY = {
    "offices": [
        {
            "office_name": {"en": "Taluka Krishi Adhikari Dindori"},
            "office_type": "district_agriculture_office",
            "address": {"en": "Taluka Krishi Office, Near Bus Stand, Dindori 422202"},
            "phone": "02557-221999",
        }
    ]
}


# ---------------------------------------------------------------------------
# 1. Search Query Construction
# ---------------------------------------------------------------------------

def test_search_query_construction_includes_all_levels():
    query = build_official_search_query(
        scheme_name="PM Kisan Samman Nidhi",
        state="Maharashtra",
        district="Nashik",
        taluka="Dindori",
    )
    assert "PM Kisan Samman Nidhi" in query
    assert "Dindori" in query
    assert "Nashik" in query
    assert "Maharashtra" in query
    assert "site:gov.in" in query


def test_search_query_construction_without_taluka():
    query = build_official_search_query(
        scheme_name="Majhi Ladki Bahin",
        state="Maharashtra",
        district="Pune",
        taluka=None,
    )
    assert "Majhi Ladki Bahin" in query
    assert "Pune" in query
    assert "Maharashtra" in query
    assert "Dindori" not in query
    assert "site:gov.in" in query


# ---------------------------------------------------------------------------
# 2. Official Government Domain Filtering
# ---------------------------------------------------------------------------

def test_official_government_domain_filtering():
    # Valid official domains
    assert is_official_gov_domain("https://nashik.gov.in/directory/") is True
    assert is_official_gov_domain("https://pune.nic.in/departments/") is True
    assert is_official_gov_domain("https://pmkisan.gov.in/ContactUs.aspx") is True
    assert is_official_gov_domain("https://aaplesarkar.mahaonline.gov.in/en") is True
    assert is_official_gov_domain("https://digitalseva.csc.gov.in/") is True

    # Invalid non-government domains
    assert is_official_gov_domain("https://randomnews.indiatimes.com/scheme") is False
    assert is_official_gov_domain("https://pmkisan.blogspot.com/apply") is False
    assert is_official_gov_domain("https://facebook.com/groups/schemes") is False
    assert is_official_gov_domain("https://fakegov.in.attacker.org/apply") is False
    assert is_official_gov_domain("https://not-gov.in") is False
    assert is_official_gov_domain("") is False
    assert is_official_gov_domain(None) is False


# ---------------------------------------------------------------------------
# 3. Candidate Page Parsing
# ---------------------------------------------------------------------------

def test_candidate_page_parsing_html_table():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = SAMPLE_GOV_HTML_DIRECTORY
    mock_client.get.return_value = mock_resp

    provider = OfficialPortalLocationProvider(client=mock_client)
    results = provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert results is not None
    assert len(results) >= 1
    dindori_loc = [l for l in results if l.taluka == "dindori"][0]
    assert "Dindori" in dindori_loc.office_name["en"]
    assert dindori_loc.office_type == "tahsil_office"
    assert "422202" in dindori_loc.address["en"]
    assert dindori_loc.contact_phone == "02557-221234"


def test_candidate_page_parsing_json_directory():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = SAMPLE_GOV_JSON_DIRECTORY
    mock_client.get.return_value = mock_resp

    provider = OfficialPortalLocationProvider(client=mock_client)
    results = provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert results is not None
    assert len(results) == 1
    assert "Taluka Krishi Adhikari" in results[0].office_name["en"]
    assert results[0].contact_phone == "02557-221999"


# ---------------------------------------------------------------------------
# 4. Unverified / Non-Government Candidate Rejection
# ---------------------------------------------------------------------------

def test_unverified_non_government_candidate_rejection():
    class MockThirdPartySearchBackend(SearchBackend):
        def search_candidates(self, query: str, max_results: int = 5):
            return [
                {
                    "title": "Apply for PM Kisan on Blogspot",
                    "url": "https://pmkisan.blogspot.com/where-to-apply",
                    "snippet": "Tahsil Office Dindori address...",
                },
                {
                    "title": "News Article about Yojana Centers",
                    "url": "https://dailyupdates.com/yojana-centers",
                    "snippet": "Apply at collector office...",
                },
            ]

    gov_provider = GovernmentWebSearchProvider(backend=MockThirdPartySearchBackend())
    results = gov_provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    # Must reject all non-gov candidates and return None
    assert results is None


# ---------------------------------------------------------------------------
# 5, 6, 7. Hierarchy Filtering: State, District, Taluka
# ---------------------------------------------------------------------------

def test_hierarchy_state_filtering():
    locs = [
        ApplicationLocation(
            id="loc-mah",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka="dindori",
            office_name={"en": "Office Mah"},
            office_type="tahsil_office",
            address={"en": "Dindori Road"},
        ),
        ApplicationLocation(
            id="loc-guj",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="gujarat",
            district="surat",
            taluka="surat",
            office_name={"en": "Office Guj"},
            office_type="tahsil_office",
            address={"en": "Surat Road"},
        ),
    ]

    filtered = filter_locations_hierarchy(locs, state="maharashtra", district="nashik", taluka="dindori")
    assert len(filtered) == 1
    assert filtered[0].id == "loc-mah"


def test_hierarchy_district_filtering():
    locs = [
        ApplicationLocation(
            id="loc-nashik",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka=None,
            office_name={"en": "DSAO Nashik"},
            office_type="district_agriculture_office",
            address={"en": "Nashik City"},
        ),
        ApplicationLocation(
            id="loc-pune",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="maharashtra",
            district="pune",
            taluka=None,
            office_name={"en": "DSAO Pune"},
            office_type="district_agriculture_office",
            address={"en": "Pune City"},
        ),
    ]

    filtered = filter_locations_hierarchy(locs, state="maharashtra", district="nashik")
    assert len(filtered) == 1
    assert filtered[0].id == "loc-nashik"


def test_hierarchy_taluka_filtering_rejects_other_talukas():
    locs = [
        ApplicationLocation(
            id="loc-dindori",
            scheme_ids=["majhi-ladki-bahin"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka="dindori",
            office_name={"en": "Dindori Tahsil Office"},
            office_type="tahsil_office",
            address={"en": "Dindori"},
        ),
        ApplicationLocation(
            id="loc-niphad",
            scheme_ids=["majhi-ladki-bahin"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka="niphad",
            office_name={"en": "Niphad Tahsil Office"},
            office_type="tahsil_office",
            address={"en": "Niphad"},
        ),
    ]

    filtered = filter_locations_hierarchy(locs, state="maharashtra", district="nashik", taluka="dindori")
    assert len(filtered) == 1
    assert filtered[0].id == "loc-dindori"


# ---------------------------------------------------------------------------
# 8. District-Level Office Remains Valid When Taluka Is Supplied
# ---------------------------------------------------------------------------

def test_district_level_office_remains_valid_with_taluka():
    locs = [
        ApplicationLocation(
            id="loc-dsao",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka=None,  # District-level office serving whole district
            office_name={"en": "District Superintending Agriculture Office"},
            office_type="district_agriculture_office",
            address={"en": "Shingada Talav, Nashik"},
        ),
        ApplicationLocation(
            id="loc-other-taluka",
            scheme_ids=["pm-kisan"],
            categories=[],
            state="maharashtra",
            district="nashik",
            taluka="niphad",  # Different taluka
            office_name={"en": "Niphad Office"},
            office_type="tahsil_office",
            address={"en": "Niphad"},
        ),
    ]

    filtered = filter_locations_hierarchy(locs, state="maharashtra", district="nashik", taluka="dindori")
    # District-level office is valid; Niphad is excluded
    assert len(filtered) == 1
    assert filtered[0].id == "loc-dsao"
    assert filtered[0].taluka is None


# ---------------------------------------------------------------------------
# 9. No Fabricated Location When Page Lacks Address/Contact
# ---------------------------------------------------------------------------

def test_no_fabricated_location_when_missing_address_contact():
    html_without_address = """
    <html><body>
    <table>
        <tr><th>Heading</th></tr>
        <tr><td>Some Notice Text</td></tr>
    </table>
    </body></html>
    """
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.text = html_without_address
    mock_client.get.return_value = mock_resp

    provider = OfficialPortalLocationProvider(client=mock_client)
    res = provider.search("pm-kisan", "maharashtra", "nashik", "dindori")
    assert res is None


# ---------------------------------------------------------------------------
# 10. Live Provider Unavailable -> Fallback to locations.json
# ---------------------------------------------------------------------------

def test_live_provider_unavailable_falls_back_to_catalog():
    provider = ExternalSearchAPIProvider(api_key=None)
    assert provider.is_available() is False

    result = find_application_options(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=provider,
    )
    assert result.source_type == "local_catalog_fallback"
    assert result.verification_status == "catalog_fallback"
    assert len(result.physical_locations) == 1
    assert result.physical_locations[0].id == "mah-nsk-dindori-tahsil"


# ---------------------------------------------------------------------------
# 11. Live Provider Timeout -> Fallback to locations.json
# ---------------------------------------------------------------------------

def test_live_provider_timeout_falls_back_to_catalog():
    class TimeoutProvider(LocationSearchProvider):
        def search(self, scheme_id, state, district=None, taluka=None):
            raise httpx.TimeoutException("Connection timed out after 5.0s")

    result = find_application_options(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=TimeoutProvider(),
    )
    assert result.source_type == "local_catalog_fallback"
    assert len(result.physical_locations) >= 1
    assert result.online_application.available is True


# ---------------------------------------------------------------------------
# 12. Live Provider Returns Unverified Results -> Fallback
# ---------------------------------------------------------------------------

def test_live_provider_unverified_results_falls_back_to_catalog():
    class EmptyUnverifiedProvider(LocationSearchProvider):
        def search(self, scheme_id, state, district=None, taluka=None):
            return None

    result = find_application_options(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=EmptyUnverifiedProvider(),
    )
    assert result.source_type == "local_catalog_fallback"
    assert len(result.physical_locations) >= 1


# ---------------------------------------------------------------------------
# 13. Online Portal Remains Available When No Physical Location Is Found
# ---------------------------------------------------------------------------

def test_online_portal_remains_available_when_no_physical_location():
    class NoLocationProvider(LocationSearchProvider):
        def search(self, scheme_id, state, district=None, taluka=None):
            return None

    result = find_application_options(
        scheme_id="pm-kisan",
        state="karnataka",
        district="mysuru",
        taluka="mysuru",
        live_provider=NoLocationProvider(),
        fallback_pool=[],  # No local fallback for mysuru
    )
    assert result.source_type == "none"
    assert result.physical_locations == []
    assert result.online_application.available is True
    assert "pmkisan.gov.in" in result.online_application.portal_url


# ---------------------------------------------------------------------------
# 14. Deterministic In-Memory Cache Behavior
# ---------------------------------------------------------------------------

def test_in_memory_cache_behavior():
    call_count = 0

    class CountingLiveProvider(LocationSearchProvider):
        def search(self, scheme_id, state, district=None, taluka=None):
            nonlocal call_count
            call_count += 1
            return [
                ApplicationLocation(
                    id="loc-cached-1",
                    scheme_ids=[scheme_id],
                    categories=[],
                    state=state,
                    district=district,
                    taluka=taluka,
                    office_name={"en": "Cached Office"},
                    office_type="government_office",
                    address={"en": "Cached Address 123"},
                )
            ]

    provider = CountingLiveProvider()

    # First call - cache miss
    res1 = find_application_options("pm-kisan", "maharashtra", "nashik", "dindori", live_provider=provider, use_cache=True)
    assert call_count == 1
    assert res1.physical_locations[0].id == "loc-cached-1"

    # Second call - cache hit, provider not called again
    res2 = find_application_options("pm-kisan", "maharashtra", "nashik", "dindori", live_provider=provider, use_cache=True)
    assert call_count == 1
    assert res2.physical_locations[0].id == "loc-cached-1"


# ---------------------------------------------------------------------------
# 15. Existing locations.py Behavior Unaffected
# ---------------------------------------------------------------------------

def test_locations_py_find_locations_remains_intact():
    locs = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert len(locs) == 1
    assert locs[0].id == "mah-nsk-dindori-tahsil"
    assert locs[0].taluka == "dindori"


def test_locations_py_load_locations_data_intact():
    catalog = load_locations_data()
    assert len(catalog) >= 6
    assert all(isinstance(l, ApplicationLocation) for l in catalog)


# ---------------------------------------------------------------------------
# 16. API Endpoint Verification: GET /api/application-options
# ---------------------------------------------------------------------------

def test_api_application_options_endpoint(client):
    response = client.get(
        "/api/application-options",
        params={
            "scheme_id": "pm-kisan",
            "state": "maharashtra",
            "district": "nashik",
            "taluka": "dindori",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scheme_id"] == "pm-kisan"
    assert data["state"] == "maharashtra"
    assert data["district"] == "nashik"
    assert data["taluka"] == "dindori"
    assert data["online_application"]["available"] is True
    assert "pmkisan.gov.in" in data["online_application"]["portal_url"]
    assert len(data["physical_locations"]) >= 1
    assert data["source_type"] in ("live_official_source", "local_catalog_fallback")


# ---------------------------------------------------------------------------
# 17. Serper Search Backend: Request Construction & Parsing
# ---------------------------------------------------------------------------

def test_serper_request_construction():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "organic": [
            {
                "title": "District Directory - Nashik",
                "link": "https://nashik.gov.in/directory/",
                "snippet": "Public offices in Nashik district.",
            }
        ]
    }
    mock_client.post.return_value = mock_resp

    backend = SerperSearchBackend(api_key="test_serper_secret_key", client=mock_client)
    assert backend.is_available() is True

    results = backend.search_candidates("pm-kisan nashik dindori site:gov.in", max_results=5)

    # Verify request method and URL
    mock_client.post.assert_called_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert call_args[0] == "https://google.serper.dev/search"

    # Verify headers
    headers = call_kwargs.get("headers", {})
    assert headers.get("X-API-KEY") == "test_serper_secret_key"
    assert headers.get("Content-Type") == "application/json"

    # Verify payload
    payload = call_kwargs.get("json", {})
    assert payload.get("q") == "pm-kisan nashik dindori site:gov.in"
    assert payload.get("num") == 5
    assert payload.get("gl") == "in"

    # Verify result parsing
    assert len(results) == 1
    assert results[0]["title"] == "District Directory - Nashik"
    assert results[0]["url"] == "https://nashik.gov.in/directory/"
    assert results[0]["snippet"] == "Public offices in Nashik district."


def test_serper_response_parsing_empty_organic():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"organic": []}
    mock_client.post.return_value = mock_resp

    backend = SerperSearchBackend(api_key="test_serper_key", client=mock_client)
    results = backend.search_candidates("non-existent-scheme query")
    assert results == []


# ---------------------------------------------------------------------------
# 18. Serper Official Result Filtering & Page Fetching
# ---------------------------------------------------------------------------

def test_serper_official_result_filtering_and_page_fetch():
    mock_http_client = MagicMock(spec=httpx.Client)

    # 1. Search call returns 1 official and 1 non-gov link
    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": [
            {
                "title": "Blog Article with fake info",
                "link": "https://randomblog.com/how-to-apply",
                "snippet": "Apply here...",
            },
            {
                "title": "Official Nashik Directory",
                "link": "https://nashik.gov.in/directory/",
                "snippet": "Directory of government offices in Nashik.",
            },
        ]
    }

    # 2. Page fetch response for official page
    mock_page_resp = MagicMock(spec=httpx.Response)
    mock_page_resp.status_code = 200
    mock_page_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_page_resp.text = SAMPLE_GOV_HTML_DIRECTORY

    def mock_get(url, *args, **kwargs):
        if "nashik.gov.in" in url:
            return mock_page_resp
        return MagicMock(status_code=404)

    mock_http_client.post.return_value = mock_search_resp
    mock_http_client.get.side_effect = mock_get

    backend = SerperSearchBackend(api_key="test_serper_key", client=mock_http_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=mock_http_client)

    results = gov_provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )

    assert results is not None
    assert len(results) >= 1
    # Check that Dindori tahsil office was extracted from the official page
    assert any(loc.taluka == "dindori" for loc in results)
    assert any(loc.source_url == "https://nashik.gov.in/directory/" for loc in results)


def test_serper_rejects_non_government_domains():
    mock_http_client = MagicMock(spec=httpx.Client)
    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": [
            {
                "title": "News Site Advice",
                "link": "https://news.indiatimes.com/pmkisan",
                "snippet": "Offices everywhere...",
            },
            {
                "title": "Fake Gov Site",
                "link": "https://fake-gov.in.com/pmkisan",
                "snippet": "Apply at fake center...",
            },
        ]
    }
    mock_http_client.post.return_value = mock_search_resp

    backend = SerperSearchBackend(api_key="test_serper_key", client=mock_http_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=mock_http_client)

    results = gov_provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    # Rejects all non-government links; GET never called for pages
    assert results is None
    mock_http_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# 19. Serper Failure Modes & Fallback to locations.json
# ---------------------------------------------------------------------------

def test_serper_no_credentials_graceful_unavailable():
    backend = SerperSearchBackend(api_key=None)
    assert backend.is_available() is False
    assert backend.search_candidates("pm-kisan query") == []

    # Using through find_application_options falls back to locations.json
    result = find_application_options(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=GovernmentWebSearchProvider(backend=backend),
    )
    assert result.source_type == "local_catalog_fallback"
    assert len(result.physical_locations) == 1
    assert result.physical_locations[0].id == "mah-nsk-dindori-tahsil"


def test_serper_timeout_fallback_to_locations_json():
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.TimeoutException("Serper API timed out after 5s")

    backend = SerperSearchBackend(api_key="test_key", client=mock_client)
    assert backend.search_candidates("test query") == []

    result = find_application_options(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=GovernmentWebSearchProvider(backend=backend),
    )
    assert result.source_type == "local_catalog_fallback"
    assert len(result.physical_locations) >= 1


def test_serper_api_error_fallback_to_locations_json():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_client.post.return_value = mock_resp

    backend = SerperSearchBackend(api_key="invalid_or_expired_key", client=mock_client)
    assert backend.search_candidates("test query") == []

    result = find_application_options(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=GovernmentWebSearchProvider(backend=backend),
    )
    assert result.source_type == "local_catalog_fallback"
    assert len(result.physical_locations) >= 1


# ---------------------------------------------------------------------------
# 20. Google CSE Backward Compatibility & Provider Routing
# ---------------------------------------------------------------------------

def test_google_cse_backward_compatibility():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "title": "Google CSE Result",
                "link": "https://nashik.gov.in/directory/",
                "snippet": "Official directory via Google CSE.",
            }
        ]
    }
    mock_client.get.return_value = mock_resp

    backend = GoogleCSESearchBackend(
        api_key="test_google_key",
        engine_id="test_engine_id",
        client=mock_client,
    )
    assert backend.is_available() is True
    results = backend.search_candidates("pm-kisan query")
    assert len(results) == 1
    assert results[0]["url"] == "https://nashik.gov.in/directory/"


def test_external_search_api_provider_routing():
    # Serper routing
    provider_serper = ExternalSearchAPIProvider(
        api_key="serper_test_key",
        provider_name="serper",
    )
    assert provider_serper.provider_name == "serper"
    assert isinstance(provider_serper._backend, SerperSearchBackend)
    assert provider_serper.is_available() is True

    # Google CSE routing
    provider_cse = ExternalSearchAPIProvider(
        api_key="cse_test_key",
        engine_id="cse_test_engine",
        provider_name="google_cse",
    )
    assert provider_cse.provider_name == "google_cse"
    assert isinstance(provider_cse._backend, GoogleCSESearchBackend)
    assert provider_cse.is_available() is True


# ---------------------------------------------------------------------------
# 21. Step 3C: AuthorityExtractionParser Tests
# ---------------------------------------------------------------------------

def test_authority_extraction_parser_recognizes_tahsil_office():
    text = "Beneficiaries may submit offline application forms at the nearest Tahsil Office or Taluka Office."
    res = AuthorityExtractionParser.parse_text(text)
    assert res.is_online_only is False
    assert "tahsil_office" in res.designated_authorities
    assert res.designated_authorities["tahsil_office"] == "scheme_designated_application_center"


def test_authority_extraction_parser_recognizes_setu_kendra_and_csc():
    text = "Citizens can apply and submit documents at any authorized Setu Kendra or CSC center in Maharashtra."
    res = AuthorityExtractionParser.parse_text(text)
    assert "citizen_service_center" in res.designated_authorities
    assert res.designated_authorities["citizen_service_center"] == "scheme_designated_application_center"


def test_authority_extraction_parser_recognizes_agriculture_authority():
    text = "Submit crop insurance registration at the District Superintending Agriculture Office (DSAO) or Krishi Bhavan."
    res = AuthorityExtractionParser.parse_text(text)
    assert "district_agriculture_office" in res.designated_authorities
    assert res.designated_authorities["district_agriculture_office"] == "scheme_designated_application_center"


def test_authority_extraction_parser_does_not_classify_generic_contact_as_application_center():
    text = "For general information, inquiries, or grievance redressal, please contact the Collectorate helpline."
    res = AuthorityExtractionParser.parse_text(text)
    assert res.designated_authorities.get("collectorate") == "general_government_assistance"
    assert "scheme_designated_application_center" not in res.designated_authorities.values()


def test_authority_extraction_parser_detects_online_only_instruction():
    text = "Applications must be submitted online only at https://mahadbt.gov.in. No offline applications will be accepted at any government office."
    res = AuthorityExtractionParser.parse_text(text)
    assert res.is_online_only is True


# ---------------------------------------------------------------------------
# 22. Step 3C: Standard District Directory Resolver & Whos-Who
# ---------------------------------------------------------------------------

def test_standard_district_directory_resolver_attempts_whos_who():
    urls = get_standard_district_directory_urls("nashik")
    assert any("whos-who" in u for u in urls)
    assert any("/en/whos-who/" in u for u in urls)
    assert any("directory" in u for u in urls)


def test_official_portal_location_provider_supports_en_whos_who():
    mock_client = MagicMock(spec=httpx.Client)

    def mock_get(url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        if "/en/whos-who/" in url:
            resp.status_code = 200
            resp.text = SAMPLE_GOV_HTML_DIRECTORY
        else:
            resp.status_code = 404
            resp.text = "Not Found"
        return resp

    mock_client.get.side_effect = mock_get

    provider = OfficialPortalLocationProvider(client=mock_client)
    results = provider.search(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert results is not None
    assert len(results) >= 1
    assert any(loc.taluka == "dindori" for loc in results)


# ---------------------------------------------------------------------------
# 23. Step 3C: Enhanced Non-Table Office Card Parsing
# ---------------------------------------------------------------------------

SAMPLE_NON_TABLE_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="officer-card card">
    <h3>Tahsil Office Dindori</h3>
    <p class="address">Address: Main Road, Near Bus Stand, Dindori 422202</p>
    <p class="phone">Phone: 02557-221234</p>
</div>
<div class="notice-card card">
    <p>General public notice without any address or telephone number.</p>
</div>
</body>
</html>
"""

def test_non_table_office_card_parsing():
    provider = OfficialPortalLocationProvider()
    locs = provider._parse_html_directory(
        SAMPLE_NON_TABLE_HTML,
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        source_url="https://nashik.gov.in/en/about-district/administrative-setup/tehsil/",
    )
    assert locs is not None
    assert len(locs) == 1
    first = locs[0]
    assert "tahsil" in first.office_type
    assert "dindori" in first.office_name["en"].lower()
    assert first.contact_phone == "02557-221234"
    assert "422202" in first.address["en"]


# ---------------------------------------------------------------------------
# 24. Step 3C: Multi-Source Corroboration (Source A + Source B)
# ---------------------------------------------------------------------------

def test_scheme_source_a_plus_directory_source_b_corroboration():
    mock_http_client = MagicMock(spec=httpx.Client)

    # 1. Search backend returns Source A (scheme notice)
    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": [
            {
                "title": "Scheme Notice - Majhi Ladki Bahin",
                "link": "https://nashik.gov.in/en/notice/ladki-bahin-form/",
                "snippet": "Apply at Tahsil Office.",
            }
        ]
    }
    mock_http_client.post.return_value = mock_search_resp

    # 2. HTTP GET responses: Source A establishes authority, Source B gives office
    def mock_get(url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        if "notice/ladki-bahin-form" in url:
            resp.status_code = 200
            resp.text = "<html><body><p>Beneficiaries may submit offline applications at the Tahsil Office.</p></body></html>"
        elif "whos-who" in url or "tehsil" in url:
            resp.status_code = 200
            resp.text = SAMPLE_NON_TABLE_HTML
        else:
            resp.status_code = 404
        return resp

    mock_http_client.get.side_effect = mock_get

    backend = SerperSearchBackend(api_key="test_key", client=mock_http_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=mock_http_client)

    results = gov_provider.search(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )

    assert results is not None
    assert len(results) >= 1
    first = results[0]
    # Check corroboration
    assert first.office_type == "tahsil_office"
    assert first.application_method == "scheme_designated_application_center"
    assert first.scheme_authorization_url == "https://nashik.gov.in/en/notice/ladki-bahin-form/"
    assert "nashik.gov.in" in first.source_url


def test_missing_source_a_authorization_does_not_falsely_present_office():
    mock_http_client = MagicMock(spec=httpx.Client)

    # Search returns page that has NO offline application authorization
    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": [
            {
                "title": "General Scheme Overview",
                "link": "https://nashik.gov.in/en/overview/",
                "snippet": "General overview.",
            }
        ]
    }
    mock_http_client.post.return_value = mock_search_resp

    def mock_get(url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        if "overview" in url:
            resp.status_code = 200
            resp.text = "<html><body><p>This is a scheme overview. No offline submission mentioned.</p></body></html>"
        elif "whos-who" in url:
            resp.status_code = 200
            resp.text = SAMPLE_NON_TABLE_HTML
        else:
            resp.status_code = 404
        return resp

    mock_http_client.get.side_effect = mock_get

    backend = SerperSearchBackend(api_key="test_key", client=mock_http_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=mock_http_client)

    results = gov_provider.search(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    # Must reject false claims of application center
    assert results is None


def test_missing_source_b_office_verification_returns_clean_fallback():
    mock_http_client = MagicMock(spec=httpx.Client)

    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": [
            {
                "title": "Scheme Notice",
                "link": "https://nashik.gov.in/notice/form/",
                "snippet": "Apply at Tahsil Office.",
            }
        ]
    }
    mock_http_client.post.return_value = mock_search_resp

    # Source A succeeds, but Source B directories all return 404
    def mock_get(url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html"}
        if "notice/form" in url:
            resp.status_code = 200
            resp.text = "<p>Submit application at Tahsil Office.</p>"
        else:
            resp.status_code = 404
        return resp

    mock_http_client.get.side_effect = mock_get

    backend = SerperSearchBackend(api_key="test_key", client=mock_http_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=mock_http_client)

    results = gov_provider.search(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    # No fabricated physical office
    assert results is None


def test_large_pdf_safely_skipped():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.headers = {
        "content-type": "application/pdf",
        "content-length": "5242880",  # 5 MB
    }
    mock_resp.url = "https://cdnbbsr.s3waas.gov.in/large_circular.pdf"

    assert is_safe_pdf_response(mock_resp, max_bytes=2_000_000) is False

    # Small PDF is allowed
    mock_resp.headers["content-length"] = "500000"  # 500 KB
    assert is_safe_pdf_response(mock_resp, max_bytes=2_000_000) is True
