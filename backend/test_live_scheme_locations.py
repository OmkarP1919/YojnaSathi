"""
Regression tests for physical application center resolution for live-discovered schemes.
Verifies scenarios A through E:
- A: Live-discovered Maharashtra scheme + Nashik + Dindori with CSC authorization -> CSC / Sewa Kendra provider returns centers.
- B: Curated Maharashtra scheme -> existing behavior unchanged.
- C: Scheme without CSC authorization -> no false CSC designation.
- D: Missing taluka -> do not query Sewa Kendra directory.
- E: Provider failure -> fallback to local verified catalog intact.
- Integration: POST /api/recommend attaches resolved centers to recommendation results.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    ApplicationLocation,
    ApplicationOptionsResult,
    CitizenProfile,
    RecommendationRequest,
    Scheme,
)
from app.location_search import (
    clear_location_cache,
    find_application_options,
    GovernmentWebSearchProvider,
    MaharashtraSewaKendraProvider,
    SerperSearchBackend,
)
from services.web_scheme_discovery.adapter import discovered_to_canonical_scheme
from services.web_scheme_discovery.schemas import DiscoveredScheme
from test_location_search import (
    SEWA_CENTERS_HTML,
    SEWA_TALUKA_JSON,
    SEWA_PAGE_HTML,
    _sewa_client,
)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_location_cache()
    yield
    clear_location_cache()


def _sewa_mock_transport_with_gov(centers_html=SEWA_CENTERS_HTML, taluka_json=None):
    taluka_json = SEWA_TALUKA_JSON if taluka_json is None else taluka_json
    requested = {"subdistrict_code": None, "n_requests": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        requested["n_requests"] += 1
        url = str(request.url)
        if request.method == "POST" and "SewaKendraDetails" in url:
            requested["subdistrict_code"] = request.content.decode("utf-8", "replace") if request.content else ""
            return httpx.Response(200, text=centers_html, headers={"content-type": "text/html"})
        if "GetTalukaDetails" in url:
            return httpx.Response(
                200,
                text=json.dumps(taluka_json),
                headers={"content-type": "application/json; charset=utf-8"},
            )
        if request.method == "GET" and "SewaKendraDetails" in url:
            return httpx.Response(200, text=SEWA_PAGE_HTML, headers={"content-type": "text/html"})
        if "nashik.gov.in" in url:
            return httpx.Response(
                200,
                text=(
                    "<html><body><p>Eligible beneficiaries may submit at any authorised Setu Kendra, "
                    "Maha e-Seva Kendra or Common Service Centre (CSC).</p></body></html>"
                ),
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, text="Not Found")

    return handler, requested


def _build_test_gov_provider(organic_results=None):
    """Construct a GovernmentWebSearchProvider with mocked search backend and HTTP client."""
    handler, requested = _sewa_mock_transport_with_gov()

    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "organic": organic_results or []
    }
    mock_search_client = MagicMock(spec=httpx.Client)
    mock_search_client.post.return_value = mock_search_resp

    http_client = _sewa_client(handler)
    backend = SerperSearchBackend(api_key="test_key", client=mock_search_client)
    return GovernmentWebSearchProvider(backend=backend, http_client=http_client), requested


def test_scenario_a_live_discovered_scheme_csc_resolution():
    """
    Scenario A:
    A live-discovered scheme with CSC authorization in Maharashtra + Nashik + Dindori
    reaches MaharashtraSewaKendraProvider and returns real citizen-facing centers.
    """
    candidate = DiscoveredScheme(
        scheme_name="Mukhyamantri Baliraja Shetkari Yojana",
        description="Electricity tariff concession for farmers in Maharashtra.",
        benefits=["Free electricity concession"],
        eligibility=["Must be a farmer residing in Maharashtra with active agricultural pump"],
        application_process=["Apply online at portal or visit nearest CSC, Maha e-Seva Kendra, or Setu Kendra with 7/12 extract."],
        application_url="https://krishi.maharashtra.gov.in/baliraja",
        source_url="https://krishi.maharashtra.gov.in/baliraja",
        source_urls=["https://krishi.maharashtra.gov.in/baliraja"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )

    scheme = discovered_to_canonical_scheme(candidate)
    assert scheme.id.startswith("web-")
    assert scheme.custom_application_guidance is not None
    assert scheme.custom_application_guidance.offline_application is not None
    assert "CSC" in scheme.custom_application_guidance.offline_application.authorized_channel

    gov_provider, requested = _build_test_gov_provider()

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=gov_provider,
        scheme=scheme,
    )

    assert options.verification_status == "live_verified"
    assert options.source_type == "live_official_source"
    assert len(options.physical_locations) == 3
    assert all(loc.office_type == "citizen_service_center" for loc in options.physical_locations)
    assert all(loc.state == "maharashtra" for loc in options.physical_locations)
    assert all(loc.district == "nashik" for loc in options.physical_locations)
    assert all(loc.taluka == "dindori" for loc in options.physical_locations)
    assert "mahaonline.gov.in" in (options.physical_locations[0].source_url or "")
    assert requested["subdistrict_code"] is not None
    assert "SubDistrictcode=4149" in requested["subdistrict_code"]


def test_scenario_b_curated_maharashtra_scheme_unchanged():
    """
    Scenario B:
    Curated Maharashtra scheme behavior is preserved.
    """
    gov_provider, requested = _build_test_gov_provider(
        organic_results=[
            {
                "title": "Ladki Bahin Notice",
                "link": "https://nashik.gov.in/en/notice/ladki-bahin-notice/",
                "snippet": "Apply at Setu Kendra or CSC.",
            }
        ]
    )

    options = find_application_options(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=gov_provider,
    )

    assert options.verification_status == "live_verified"
    assert len(options.physical_locations) > 0
    assert all(loc.office_type == "citizen_service_center" for loc in options.physical_locations)
    assert requested["subdistrict_code"] is not None


def test_scenario_c_scheme_without_csc_authorization_no_false_csc():
    """
    Scenario C:
    A scheme without CSC authorization must NOT query Sewa Kendra directory
    and must NOT produce false CSC locations.
    """
    candidate = DiscoveredScheme(
        scheme_name="Maharashtra Higher Education Scholarship",
        description="Scholarship for college students.",
        benefits=["Tuition reimbursement"],
        eligibility=["Enrolled student in Maharashtra"],
        application_process=["Applications must be submitted exclusively online through the MahaDBT web portal."],
        application_url="https://mahadbt.maharashtra.gov.in",
        source_url="https://mahadbt.maharashtra.gov.in",
        source_urls=["https://mahadbt.maharashtra.gov.in"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.90,
    )

    scheme = discovered_to_canonical_scheme(candidate)
    gov_provider, requested = _build_test_gov_provider()

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=gov_provider,
        scheme=scheme,
    )

    # Online-only should suppress physical locations or return none
    assert not any(loc.office_type == "citizen_service_center" for loc in options.physical_locations)
    assert requested["subdistrict_code"] is None  # Sewa Kendra details POST was NOT called


def test_scenario_d_missing_taluka_does_not_query_sewa_kendra():
    """
    Scenario D:
    Missing taluka prevents querying the taluka-level Sewa Kendra directory.
    """
    candidate = DiscoveredScheme(
        scheme_name="Mukhyamantri Baliraja Shetkari Yojana",
        description="Electricity tariff concession for farmers in Maharashtra.",
        benefits=["Free electricity concession"],
        eligibility=["Must be a farmer in Maharashtra"],
        application_process=["Submit at nearest CSC, Maha e-Seva Kendra, or Setu Kendra."],
        application_url="https://krishi.maharashtra.gov.in/baliraja",
        source_url="https://krishi.maharashtra.gov.in/baliraja",
        source_urls=["https://krishi.maharashtra.gov.in/baliraja"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )

    scheme = discovered_to_canonical_scheme(candidate)
    gov_provider, requested = _build_test_gov_provider()

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka=None,  # Missing taluka
        live_provider=gov_provider,
        scheme=scheme,
    )

    assert requested["subdistrict_code"] is None  # No taluka-specific directory lookup made
    assert not any(loc.office_type == "citizen_service_center" for loc in options.physical_locations)


def test_regression_nashik_dindori_exact_filtering_and_terminology():
    """
    Focused test 1:
    Maharashtra + Nashik + Dindori sends Dindori subdistrict ID (4149),
    returns ONLY Dindori centers, and uses Aaple Sarkar Seva Kendra terminology.
    """
    candidate = DiscoveredScheme(
        scheme_name="Mukhyamantri Baliraja Shetkari Yojana",
        description="Electricity tariff concession for farmers in Maharashtra.",
        benefits=["Free electricity concession"],
        eligibility=["Must be a farmer residing in Maharashtra with active agricultural pump"],
        application_process=["Submit at nearest CSC, Maha e-Seva Kendra, or Setu Kendra."],
        application_url="https://krishi.maharashtra.gov.in/baliraja",
        source_url="https://krishi.maharashtra.gov.in/baliraja",
        source_urls=["https://krishi.maharashtra.gov.in/baliraja"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )
    scheme = discovered_to_canonical_scheme(candidate)
    gov_provider, requested = _build_test_gov_provider()

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=gov_provider,
        scheme=scheme,
    )

    assert options.verification_status == "live_verified"
    assert requested["subdistrict_code"] is not None
    assert "SubDistrictcode=4149" in requested["subdistrict_code"]
    assert len(options.physical_locations) == 3
    for loc in options.physical_locations:
        assert loc.taluka == "dindori"
        assert loc.district == "nashik"
        assert loc.state == "maharashtra"
        assert "Aaple Sarkar Seva Kendra" in loc.office_name["en"]
        assert "sinnar" not in loc.address["en"].lower()
        assert "niphad" not in loc.address["en"].lower()


def test_regression_nashik_another_taluka_niphad():
    """
    Focused test 2:
    Maharashtra + Nashik + Niphad sends Niphad subdistrict ID (4155),
    and returned centers belong only to Niphad.
    """
    candidate = DiscoveredScheme(
        scheme_name="Mukhyamantri Baliraja Shetkari Yojana",
        description="Electricity tariff concession for farmers in Maharashtra.",
        benefits=["Free electricity concession"],
        eligibility=["Must be a farmer residing in Maharashtra with active agricultural pump"],
        application_process=["Submit at nearest CSC, Maha e-Seva Kendra, or Setu Kendra."],
        application_url="https://krishi.maharashtra.gov.in/baliraja",
        source_url="https://krishi.maharashtra.gov.in/baliraja",
        source_urls=["https://krishi.maharashtra.gov.in/baliraja"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )
    scheme = discovered_to_canonical_scheme(candidate)

    niphad_centers_html = '''<!DOCTYPE html>
<html><body>
<table class="table table-bordered table-striped">
    <thead>
        <tr><th> VLE Name </th><th> Address </th><th> Pincode </th><th> Mobile </th><th> EmailID </th></tr>
    </thead>
    <tbody>
        <tr>
            <td>NIPHAD SEVA KENDRA</td>
            <td>Main Road, Niphad, Taluka Niphad, Dist Nashik</td>
            <td>422303</td>
            <td>9822123456</td>
            <td>niphad[at]gmail[dot]com</td>
        </tr>
    </tbody>
</table>
</body></html>
'''
    handler, requested = _sewa_mock_transport_with_gov(centers_html=niphad_centers_html)
    mock_search_resp = MagicMock(spec=httpx.Response)
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {"organic": []}
    mock_search_client = MagicMock(spec=httpx.Client)
    mock_search_client.post.return_value = mock_search_resp
    http_client = _sewa_client(handler)
    backend = SerperSearchBackend(api_key="test_key", client=mock_search_client)
    gov_provider = GovernmentWebSearchProvider(backend=backend, http_client=http_client)

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka="niphad",
        live_provider=gov_provider,
        scheme=scheme,
    )

    assert options.verification_status == "live_verified"
    assert requested["subdistrict_code"] is not None
    assert "SubDistrictcode=4155" in requested["subdistrict_code"]
    assert len(options.physical_locations) == 1
    assert options.physical_locations[0].taluka == "niphad"
    assert "Aaple Sarkar Seva Kendra" in options.physical_locations[0].office_name["en"]


def test_regression_unknown_taluka_no_district_wide_fallback():
    """
    Focused test 3 & 4:
    Unknown taluka does not resolve to an official ID, and returns NO CSC centers
    rather than falling back to district-wide centers.
    """
    candidate = DiscoveredScheme(
        scheme_name="Mukhyamantri Baliraja Shetkari Yojana",
        description="Electricity tariff concession for farmers in Maharashtra.",
        benefits=["Free electricity concession"],
        eligibility=["Must be a farmer residing in Maharashtra with active agricultural pump"],
        application_process=["Submit at nearest CSC, Maha e-Seva Kendra, or Setu Kendra."],
        application_url="https://krishi.maharashtra.gov.in/baliraja",
        source_url="https://krishi.maharashtra.gov.in/baliraja",
        source_urls=["https://krishi.maharashtra.gov.in/baliraja"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )
    scheme = discovered_to_canonical_scheme(candidate)
    gov_provider, requested = _build_test_gov_provider()

    options = find_application_options(
        scheme_id=scheme.id,
        state="maharashtra",
        district="nashik",
        taluka="nonexistent_taluka_xyz",
        live_provider=gov_provider,
        scheme=scheme,
    )

    # Provider must not have sent a POST for SewaKendraDetails
    assert requested["subdistrict_code"] is None
    # No CSC centers returned
    assert not any(loc.office_type == "citizen_service_center" for loc in options.physical_locations)


def test_scenario_e_provider_failure_falls_back_to_catalog():
    """
    Scenario E:
    When live provider fails or throws, fallback to local catalog (locations.json) succeeds.
    """
    failing_provider = MagicMock(spec=GovernmentWebSearchProvider)
    failing_provider.search.side_effect = httpx.ConnectTimeout("Search engine timeout")

    options = find_application_options(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
        live_provider=failing_provider,
    )

    assert options.source_type == "local_catalog_fallback"
    assert options.verification_status == "catalog_fallback"
    assert len(options.physical_locations) > 0


def test_recommend_endpoint_populates_locations_for_live_scheme():
    """
    End-to-end integration test:
    POST /api/recommend returns live-discovered schemes with physical application centers attached.
    """
    client = TestClient(app)

    candidate = DiscoveredScheme(
        scheme_name="Maharashtra Kisan Solar Pump Yojana",
        description="Solar pump subsidy for farmers in Maharashtra.",
        benefits=["90% subsidy on solar agricultural pumps"],
        eligibility=["Farmers with agricultural land in Maharashtra"],
        application_process=["Submit applications at any Maha e-Seva Kendra, CSC, or Setu Kendra."],
        application_url="https://krishi.maharashtra.gov.in/solar",
        source_url="https://krishi.maharashtra.gov.in/solar",
        source_urls=["https://krishi.maharashtra.gov.in/solar"],
        source_type="primary",
        state="maharashtra",
        active_status="active",
        validation_status="verified",
        confidence=0.95,
    )

    gov_provider, _ = _build_test_gov_provider()

    with patch("services.web_scheme_discovery.merger.perform_live_discovery", return_value=[candidate]), \
         patch("services.web_scheme_discovery.merger.get_cached_web_schemes", return_value=None), \
         patch("app.location_search.find_application_options") as mock_find_opts:

        # Mock find_application_options to return live verified options for the scheme
        from app.schemas import ApplicationOptionsResult
        mock_find_opts.return_value = ApplicationOptionsResult(
            scheme_id="web-maharashtra-kisan-solar-pump",
            state="maharashtra",
            district="nashik",
            taluka="dindori",
            physical_locations=[
                ApplicationLocation(
                    id="loc-test-1",
                    scheme_ids=["web-maharashtra-kisan-solar-pump"],
                    state="maharashtra",
                    district="nashik",
                    taluka="dindori",
                    office_name={"en": "GRAMPANCHAYAT Korhate", "mr": "ग्रामपंचायत कोरहाटे"},
                    office_type="citizen_service_center",
                    address={"en": "KORHATE KORHATE 422207", "mr": "कोरहाटे ४२२२०७"},
                    contact_phone="8669254871",
                    source_url="https://aaplesarkar.mahaonline.gov.in/en/Common/SewaKendraDetails",
                )
            ],
            source_type="live_official_source",
            verification_status="live_verified",
        )

        response = client.post(
            "/api/recommend",
            json={
                "profile": {
                    "state": "maharashtra",
                    "district": "nashik",
                    "taluka": "dindori",
                    "occupation": "farmer",
                }
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Find the solar pump scheme in results
    def get_name(name_val):
        return name_val if isinstance(name_val, str) else name_val.get("en", "")

    solar_results = [r for r in data["results"] if "solar" in get_name(r["scheme"]["name"]).lower()]
    assert len(solar_results) == 1
    match = solar_results[0]
    assert match["is_web_discovered"] is True
    assert len(match["locations"]) > 0
    assert all(loc["office_type"] == "citizen_service_center" for loc in match["locations"])
    assert match["scheme"]["application_guidance"]["offline_application"]["available"] is True
    assert len(match["scheme"]["application_guidance"]["offline_application"]["locations"]) > 0
