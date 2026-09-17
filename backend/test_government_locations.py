"""
Unit tests for GovernmentLocationDirectory service (Step 3D).

All external HTTP calls and Serper calls are strictly mocked.
Tests:
1. Dynamic state list from authoritative official reference.
2. District list from official state government portal table.
3. Taluka list from official NIC S3WaaS Tehsil page.
4. Duplicate normalization, title-casing, noise-prefix removal.
5. Non-official source rejection (*.gov.in / *.nic.in enforced).
6. Search result snippet without verified HTML content is rejected.
7. Cache hit avoids repeated HTTP calls.
8. Cache TTL expiry properly invalidates expired entries.
9. External search failure returns graceful unavailable state (available=False).
10. locations.json is NOT used to fake a district list.
11. Officer names on /whos-who/ are NOT parsed as talukas.
12. API endpoints:
    - GET /api/locations/states
    - GET /api/locations/districts
    - GET /api/locations/talukas
"""
import time
from typing import Dict, List, Optional
import httpx
import pytest
from fastapi.testclient import TestClient

from app.government_locations import (
    GovAdminHTMLParser,
    GovernmentLocationDirectory,
    LocationDirectoryCache,
    OFFICIAL_INDIAN_STATES,
)
from app.location_search import SearchBackend
from app.main import app
from app.schemas import (
    DistrictDirectoryResponse,
    StateDirectoryResponse,
    TalukaDirectoryResponse,
)


class MockSearchBackend(SearchBackend):
    def __init__(self, candidates: Optional[List[Dict[str, str]]] = None, available: bool = True):
        self.candidates = candidates or []
        self._available = available
        self.call_count = 0

    def is_available(self) -> bool:
        return self._available

    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        self.call_count += 1
        return self.candidates


def make_mock_client(url_to_response: Dict[str, httpx.Response]):
    call_counts: Dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        call_counts[url_str] = call_counts.get(url_str, 0) + 1
        for pattern, resp in url_to_response.items():
            if pattern in url_str:
                return resp
        return httpx.Response(status_code=404, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return client, call_counts


# ---------------------------------------------------------------------------
# 1. State List Tests
# ---------------------------------------------------------------------------

def test_states_authoritative_list():
    directory = GovernmentLocationDirectory(cache=LocationDirectoryCache())
    resp = directory.get_states()
    assert resp.available is True
    assert resp.source_type == "authoritative_reference"
    assert len(resp.states) == 36
    names = [s.name for s in resp.states]
    assert "Maharashtra" in names
    assert "Delhi" in names
    assert "Gujarat" in names
    assert all(s.verified for s in resp.states)


# ---------------------------------------------------------------------------
# 2. District List Tests
# ---------------------------------------------------------------------------

def test_districts_from_official_portal_table():
    html = """
    <html>
      <body>
        <h1>Districts of Maharashtra</h1>
        <table>
          <thead>
            <tr><th>Sr.No</th><th>District Name</th><th>Division</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>Nashik</td><td>Nashik</td></tr>
            <tr><td>2</td><td>Pune</td><td>Pune</td></tr>
            <tr><td>3</td><td>Thane</td><td>Konkan</td></tr>
            <tr><td>4</td><td>Ahmednagar</td><td>Nashik</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    mock_resp = httpx.Response(200, text=html, headers={"content-type": "text/html"})
    client, calls = make_mock_client({"maharashtra.gov.in": mock_resp})

    directory = GovernmentLocationDirectory(
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_districts("maharashtra")

    assert resp.available is True
    assert resp.source_type == "official_government_portal"
    names = [d.name for d in resp.districts]
    assert "Nashik" in names
    assert "Pune" in names
    assert "Thane" in names
    assert "Ahmednagar" in names
    assert all(d.verified for d in resp.districts)


def test_maharashtra_official_district_source_resolution_mocked_html():
    """Verify Aaple Sarkar official portal is resolved and parsed via <select> dropdown."""
    html = """
    <!DOCTYPE html>
    <html>
      <head><title>Aaple Sarkar - Government of Maharashtra</title></head>
      <body>
        <form>
          <label for="district">District</label>
          <select id="district" name="district" class="form-control">
            <option value="">-- Select District --</option>
            <option value="1">Ahmednagar</option>
            <option value="2">Akola</option>
            <option value="3">Amravati</option>
            <option value="4">Beed</option>
            <option value="5">Bhandara</option>
            <option value="6">Kolhapur</option>
            <option value="7">Mumbai City</option>
            <option value="8">Mumbai Suburban</option>
            <option value="9">Nashik</option>
            <option value="10">Pune</option>
          </select>
        </form>
      </body>
    </html>
    """
    mock_resp = httpx.Response(200, text=html, headers={"content-type": "text/html"})
    client, calls = make_mock_client({"aaplesarkar.mahaonline.gov.in": mock_resp})

    directory = GovernmentLocationDirectory(
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_districts("maharashtra")

    assert resp.available is True
    assert resp.source_type == "official_government_portal"
    assert "aaplesarkar.mahaonline.gov.in" in resp.source_url
    names = [d.name for d in resp.districts]
    assert "Ahmednagar" in names
    assert "Beed" in names
    assert "Kolhapur" in names
    assert "Nashik" in names
    assert "Pune" in names
    assert "-- Select District --" not in names
    assert all(d.verified for d in resp.districts)


def test_rejection_of_non_official_district_sources():
    """Ensure search candidate sources not on official gov domains (*.gov.in, *.nic.in) are rejected."""
    backend = MockSearchBackend(
        candidates=[
            {"title": "List of districts of Maharashtra - Wikipedia", "url": "https://en.wikipedia.org/wiki/List_of_districts_of_Maharashtra", "snippet": "Districts include Pune, Nashik, Beed"},
            {"title": "Maharashtra Tourism Guide", "url": "https://maharashtratourism.net/districts", "snippet": "Explore 36 districts of Maharashtra"},
            {"title": "Commercial Portal", "url": "https://indiadistricts.com/maharashtra", "snippet": "District Directory"},
        ]
    )
    # The client has HTML for the unofficial domains, but the directory MUST NOT query or accept them
    wiki_resp = httpx.Response(200, text="<table><tr><td>Pune</td></tr></table>", headers={"content-type": "text/html"})
    client, calls = make_mock_client({"wikipedia.org": wiki_resp})

    directory = GovernmentLocationDirectory(
        search_backend=backend,
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_districts("rajasthan")

    assert resp.available is False
    assert resp.source_type == "unavailable"
    assert resp.districts == []
    # Verify no call was made to unofficial domains
    assert "wikipedia.org" not in calls


# ---------------------------------------------------------------------------
# 3. Taluka List Tests
# ---------------------------------------------------------------------------

def test_talukas_from_official_nic_s3waas_tehsil_page():
    html = """
    <html>
      <body>
        <h1>Administrative Setup - Tehsils</h1>
        <table>
          <thead>
            <tr><th>Sr. No.</th><th>Tehsil</th><th>Sub-Division</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>Baglan</td><td>Satana</td></tr>
            <tr><td>2</td><td>Chandwad</td><td>Chandwad</td></tr>
            <tr><td>3</td><td>Deola</td><td>Kalwan</td></tr>
            <tr><td>4</td><td>Dindori</td><td>Dindori</td></tr>
            <tr><td>5</td><td>Igatpuri</td><td>Nashik</td></tr>
            <tr><td>6</td><td>Nashik</td><td>Nashik</td></tr>
            <tr><td>7</td><td>Sinnar</td><td>Niphad</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    mock_resp = httpx.Response(200, text=html, headers={"content-type": "text/html"})
    client, calls = make_mock_client({"nashik.gov.in": mock_resp})

    directory = GovernmentLocationDirectory(
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_talukas("maharashtra", "nashik")

    assert resp.available is True
    assert resp.source_type == "official_district_portal"
    assert "nashik.gov.in" in resp.source_url
    names = [t.name for t in resp.talukas]
    assert "Dindori" in names
    assert "Nashik" in names
    assert "Sinnar" in names
    assert "Baglan" in names


def test_footer_and_navigation_filtering():
    """Verify structural blocks (footer, nav, header, aside) and navigation noise terms are ignored."""
    html = """
    <html>
      <header>
        <nav>
          <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/about">About Us</a></li>
            <li><a href="/login">Login</a></li>
          </ul>
        </nav>
      </header>
      <main>
        <h2>Administrative Setup - Tehsils</h2>
        <table>
          <thead>
            <tr><th>Sr.No</th><th>Tehsil Name</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>Beed</td></tr>
            <tr><td>2</td><td>Georai</td></tr>
            <tr><td>3</td><td>Majalgaon</td></tr>
          </tbody>
        </table>
      </main>
      <footer>
        <div class="footer-links">
          <a href="/feedback">Feedback</a>
          <a href="/help">Help</a>
          <a href="/security-policy">Security Policy</a>
          <a href="/privacy-policy">Privacy Policy</a>
          <a href="/website-policies">Website Policies</a>
          <a href="/terms-of-use">Terms of Use</a>
          <a href="/sitemap">Site Map</a>
          <a href="/accessibility">Accessibility Statement</a>
          <a href="/disclaimer">Disclaimer</a>
          <a href="/contact-us">Contact Us</a>
        </div>
      </footer>
    </html>
    """
    parser = GovAdminHTMLParser(target_type="taluka")
    parser.feed(html)
    units = parser.found_units

    # Legitimate tehsils must be present
    assert "Beed" in units
    assert "Georai" in units
    assert "Majalgaon" in units

    # Footer and navigation noise MUST be filtered out
    noise_items = [
        "Feedback", "Help", "Security Policy", "Privacy Policy",
        "Website Policies", "Terms Of Use", "Site Map", "Accessibility Statement",
        "Disclaimer", "Contact Us", "Home", "About Us", "Login"
    ]
    for noise in noise_items:
        assert noise not in units, f"Noise item '{noise}' should not be in parsed units: {units}"


def test_beed_style_tehsil_extraction_with_footer_content():
    """Verify Beed district tehsil extraction filters out NIC S3WaaS footer items."""
    beed_html = """
    <!DOCTYPE html>
    <html lang="en">
      <head><title>Tehsils | District Beed | India</title></head>
      <body>
        <div id="content">
          <h1>Tehsils</h1>
          <div class="row">
            <table>
              <thead>
                <tr><th>Sr. No.</th><th>Tehsil</th><th>Sub Division</th></tr>
              </thead>
              <tbody>
                <tr><td>1</td><td>Ambajogai</td><td>Ambajogai</td></tr>
                <tr><td>2</td><td>Ashti</td><td>Ashti</td></tr>
                <tr><td>3</td><td>Beed</td><td>Beed</td></tr>
                <tr><td>4</td><td>Dharur</td><td>Dharur</td></tr>
                <tr><td>5</td><td>Georai</td><td>Georai</td></tr>
                <tr><td>6</td><td>Kaij</td><td>Kaij</td></tr>
                <tr><td>7</td><td>Majalgaon</td><td>Majalgaon</td></tr>
                <tr><td>8</td><td>Parli</td><td>Parli</td></tr>
                <tr><td>9</td><td>Patoda</td><td>Patoda</td></tr>
                <tr><td>10</td><td>Shirur Kasar</td><td>Shirur Kasar</td></tr>
                <tr><td>11</td><td>Wadwani</td><td>Wadwani</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <footer>
          <div class="region-footer">
            <ul>
              <li><a href="https://beed.gov.in/feedback/">Feedback</a></li>
              <li><a href="https://beed.gov.in/help/">Help</a></li>
              <li><a href="https://beed.gov.in/security-policy/">Security Policy</a></li>
              <li><a href="https://beed.gov.in/website-policies/">Website Policies</a></li>
            </ul>
          </div>
        </footer>
      </body>
    </html>
    """
    mock_resp = httpx.Response(200, text=beed_html, headers={"content-type": "text/html"})
    client, _ = make_mock_client({"beed.gov.in": mock_resp})

    directory = GovernmentLocationDirectory(
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_talukas("maharashtra", "beed")

    assert resp.available is True
    assert resp.source_type == "official_district_portal"
    assert "beed.gov.in" in resp.source_url

    tehsil_names = [t.name for t in resp.talukas]
    expected_tehsils = [
        "Ambajogai", "Ashti", "Beed", "Dharur", "Georai",
        "Kaij", "Majalgaon", "Parli", "Patoda", "Shirur Kasar", "Wadwani"
    ]
    for expected in expected_tehsils:
        assert expected in tehsil_names, f"Expected tehsil '{expected}' not found in {tehsil_names}"

    assert len(resp.talukas) == 11
    assert "Feedback" not in tehsil_names
    assert "Help" not in tehsil_names
    assert "Security Policy" not in tehsil_names
    assert "Website Policies" not in tehsil_names


def test_existing_parser_extraction_tables_lists_cards():
    """Verify parser successfully extracts from tables, heading-scoped lists, and card links."""
    # Test 1: Heading-scoped unordered list
    list_html = """
    <div>
      <h3>Administrative Setup - Tehsils</h3>
      <ul>
        <li>Haveli</li>
        <li>Baramati</li>
        <li>Khed</li>
      </ul>
    </div>
    """
    parser_list = GovAdminHTMLParser(target_type="taluka")
    parser_list.feed(list_html)
    assert sorted(parser_list.found_units) == ["Baramati", "Haveli", "Khed"]

    # Test 2: Administrative card link titles
    card_html = """
    <div class="card-grid">
      <div class="card"><a class="card-title search-title">Bhor</a></div>
      <div class="card"><a class="card-title search-title">Daund</a></div>
      <div class="card"><a class="card-title search-title">Junnar</a></div>
    </div>
    """
    parser_cards = GovAdminHTMLParser(target_type="taluka")
    parser_cards.feed(card_html)
    assert sorted(parser_cards.found_units) == ["Bhor", "Daund", "Junnar"]


# ---------------------------------------------------------------------------
# 4. Duplicate Normalization & Formatting
# ---------------------------------------------------------------------------

def test_gov_admin_html_parser_normalizes_and_deduplicates():
    html = """
    <table>
      <thead>
        <tr><th>Name of Tehsil</th></tr>
      </thead>
      <tbody>
        <tr><td>  dindori tehsil  </td></tr>
        <tr><td>Tehsil Dindori</td></tr>
        <tr><td>1. Sinnar</td></tr>
        <tr><td>SINNAR</td></tr>
        <tr><td>niphad</td></tr>
      </tbody>
    </table>
    """
    parser = GovAdminHTMLParser(target_type="taluka")
    parser.feed(html)
    unique = sorted(set(parser.found_units))

    assert unique == ["Dindori", "Niphad", "Sinnar"]


# ---------------------------------------------------------------------------
# 5. Non-Official Source Rejection
# ---------------------------------------------------------------------------

def test_non_official_source_rejected_in_discovery():
    # Search returns a third-party blog or Wikipedia
    backend = MockSearchBackend(
        candidates=[
            {"title": "Talukas of Nashik", "url": "https://en.wikipedia.org/wiki/Nashik_district", "snippet": "Dindori Sinnar"},
            {"title": "Travel Nashik", "url": "https://travelblog.com/nashik", "snippet": "Dindori"},
        ]
    )
    client, _ = make_mock_client({})
    directory = GovernmentLocationDirectory(
        search_backend=backend,
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_talukas("maharashtra", "nonexistent")

    # Rejects non-gov.in URLs and gracefully falls back to unavailable
    assert resp.available is False
    assert resp.source_type == "unavailable"
    assert resp.talukas == []


# ---------------------------------------------------------------------------
# 6. Snippet Rejection (Snippet alone not accepted)
# ---------------------------------------------------------------------------

def test_snippet_alone_not_authoritative_without_fetched_html():
    backend = MockSearchBackend(
        candidates=[
            {
                "title": "Administrative Setup",
                "url": "https://officialdistrict.gov.in/administrative-setup",
                "snippet": "Tehsils include TalukaOne, TalukaTwo, TalukaThree",
            }
        ]
    )
    # The server returns 500 when fetching the candidate URL
    error_resp = httpx.Response(500, text="Internal Server Error")
    client, _ = make_mock_client({"officialdistrict.gov.in": error_resp})

    directory = GovernmentLocationDirectory(
        search_backend=backend,
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_talukas("maharashtra", "officialdistrict")

    # Since the HTML page could not be fetched/verified, snippet text is NOT hallucinated into talukas
    assert resp.available is False
    assert resp.talukas == []


# ---------------------------------------------------------------------------
# 7. Cache Hit Avoids Repeated External Calls
# ---------------------------------------------------------------------------

def test_cache_hit_avoids_repeated_calls():
    html = "<table><tr><th>Tehsil</th></tr><tr><td>Dindori</td></tr></table>"
    mock_resp = httpx.Response(200, text=html, headers={"content-type": "text/html"})
    client, calls = make_mock_client({"nashik.gov.in": mock_resp})

    cache = LocationDirectoryCache(default_ttl_seconds=3600)
    directory = GovernmentLocationDirectory(http_client=client, cache=cache)

    resp1 = directory.get_talukas("maharashtra", "nashik")
    assert resp1.available is True
    assert [t.name for t in resp1.talukas] == ["Dindori"]

    # Second call should hit in-memory cache
    resp2 = directory.get_talukas("maharashtra", "nashik")
    assert resp2.available is True

    # Total HTTP calls across all endpoints for nashik.gov.in should remain 1
    total_calls = sum(calls.values())
    assert total_calls == 1


# ---------------------------------------------------------------------------
# 8. Cache TTL Expiry
# ---------------------------------------------------------------------------

def test_cache_ttl_expiry():
    cache = LocationDirectoryCache(default_ttl_seconds=1)
    cache.set("test_key", "sample_value", ttl=1)
    assert cache.get("test_key") == "sample_value"

    # Wait for TTL to elapse
    time.sleep(1.1)
    assert cache.get("test_key") is None


# ---------------------------------------------------------------------------
# 9. Graceful Unavailable State on Search Failure
# ---------------------------------------------------------------------------

def test_external_search_failure_returns_graceful_unavailable():
    backend = MockSearchBackend(candidates=[], available=False)
    client, _ = make_mock_client({})

    directory = GovernmentLocationDirectory(
        search_backend=backend,
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_districts("unknown_state")

    assert resp.available is False
    assert resp.source_type == "unavailable"
    assert resp.districts == []
    assert "could not be verified" in (resp.message or "").lower()


# ---------------------------------------------------------------------------
# 10. Separation from locations.json
# ---------------------------------------------------------------------------

def test_locations_json_not_used_to_masquerade_district_list():
    # If a state has no live official directory available, it should NOT return
    # only the pilot locations from locations.json (e.g. Pune/Nashik)
    client, _ = make_mock_client({})
    backend = MockSearchBackend(available=False)

    directory = GovernmentLocationDirectory(
        search_backend=backend,
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_districts("goa")

    assert resp.available is False
    assert resp.districts == []


# ---------------------------------------------------------------------------
# 11. Officer Names on /whos-who/ are NOT Parsed as Talukas
# ---------------------------------------------------------------------------

def test_officer_names_ignored_by_taluka_parser():
    html = """
    <html>
      <body>
        <h1>District Directory</h1>
        <table>
          <thead>
            <tr><th>Name</th><th>Designation</th><th>Contact</th></tr>
          </thead>
          <tbody>
            <tr><td>Shri Jalaj Sharma IAS</td><td>District Collector</td><td>0253-2578500</td></tr>
            <tr><td>Smt Rajeshwari Mane</td><td>Tahsildar Dindori</td><td>02557-221234</td></tr>
            <tr><td>Shri K. R. Patil</td><td>Resident Deputy Collector</td><td>kpatil@nic.in</td></tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    parser = GovAdminHTMLParser(target_type="taluka")
    parser.feed(html)

    # Officer names like Jalaj Sharma, Rajeshwari Mane, K. R. Patil must NOT become taluka names
    assert "Jalaj Sharma" not in parser.found_units
    assert "Rajeshwari Mane" not in parser.found_units
    assert "K. R. Patil" not in parser.found_units


def test_redirect_to_non_official_domain_is_rejected():
    """Ensure an official URL that redirects to an untrusted/non-official domain is rejected."""
    redirect_resp = httpx.Response(
        302,
        headers={"Location": "https://untrusted-portal.com/tehsils"},
    )
    evil_resp = httpx.Response(
        200,
        text="<table><thead><tr><th>Tehsil</th></tr></thead><tbody><tr><td>MaliciousTehsil</td></tr></tbody></table>",
        headers={"content-type": "text/html"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "beed.gov.in" in url_str:
            return httpx.Response(302, headers={"Location": "https://untrusted-portal.com/tehsils"}, request=request)
        elif "untrusted-portal.com" in url_str:
            return httpx.Response(200, text=evil_resp.text, headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    directory = GovernmentLocationDirectory(
        http_client=client,
        cache=LocationDirectoryCache(),
    )
    resp = directory.get_talukas("maharashtra", "beed")

    # The redirect leads to an untrusted domain, so it must be rejected
    assert resp.available is False
    assert resp.source_type == "unavailable"
    assert resp.talukas == []


# ---------------------------------------------------------------------------
# 12. FastAPI Endpoints Integration
# ---------------------------------------------------------------------------

def test_api_locations_states_endpoint():
    client = TestClient(app)
    response = client.get("/api/locations/states")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["source_type"] == "authoritative_reference"
    assert len(data["states"]) == 36
    names = [s["name"] for s in data["states"]]
    assert "Maharashtra" in names


def test_api_locations_districts_endpoint(monkeypatch):
    from app import government_locations

    mock_resp = DistrictDirectoryResponse(
        state="Maharashtra",
        districts=[
            {"name": "Ahmednagar", "source_url": "https://maharashtra.gov.in", "verified": True},
            {"name": "Nashik", "source_url": "https://maharashtra.gov.in", "verified": True},
            {"name": "Pune", "source_url": "https://maharashtra.gov.in", "verified": True},
        ],
        source_type="official_government_portal",
        source_url="https://maharashtra.gov.in",
        available=True,
    )

    directory = GovernmentLocationDirectory(cache=LocationDirectoryCache())
    monkeypatch.setattr(directory, "get_districts", lambda state: mock_resp)
    monkeypatch.setattr(government_locations, "get_location_directory", lambda: directory)

    client = TestClient(app)
    response = client.get("/api/locations/districts?state=maharashtra")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "Maharashtra"
    assert len(data["districts"]) == 3
    assert data["districts"][1]["name"] == "Nashik"


def test_api_locations_talukas_endpoint(monkeypatch):
    from app import government_locations

    mock_resp = TalukaDirectoryResponse(
        state="Maharashtra",
        district="Nashik",
        talukas=[
            {"name": "Dindori", "source_url": "https://nashik.gov.in", "verified": True},
            {"name": "Igatpuri", "source_url": "https://nashik.gov.in", "verified": True},
            {"name": "Sinnar", "source_url": "https://nashik.gov.in", "verified": True},
        ],
        source_type="official_district_portal",
        source_url="https://nashik.gov.in",
        available=True,
    )

    directory = GovernmentLocationDirectory(cache=LocationDirectoryCache())
    monkeypatch.setattr(directory, "get_talukas", lambda state, district: mock_resp)
    monkeypatch.setattr(government_locations, "get_location_directory", lambda: directory)

    client = TestClient(app)
    response = client.get("/api/locations/talukas?state=maharashtra&district=nashik")
    assert response.status_code == 200
    data = response.json()
    assert data["district"] == "Nashik"
    assert len(data["talukas"]) == 3
    assert data["talukas"][0]["name"] == "Dindori"
