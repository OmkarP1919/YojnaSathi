import pytest
from fastapi.testclient import TestClient

from app.locations import find_locations, load_locations_data
from app.main import app
from app.schemas import (
    ApplicationLocation,
    CitizenProfile,
    RecommendationRequest,
    RecommendationResponse,
    SchemeMatchResult,
    SingleSchemeResponse,
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Schema & Backward Compatibility
# ---------------------------------------------------------------------------

def test_citizen_profile_backward_compatibility():
    # Previous profile initialization without district/taluka
    profile = CitizenProfile(
        age=42,
        gender="male",
        state="maharashtra",
        is_farmer=True,
    )
    assert profile.district is None
    assert profile.taluka is None
    assert profile.state == "maharashtra"


def test_citizen_profile_with_district_taluka():
    profile = CitizenProfile(
        age=42,
        gender="male",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert profile.district == "nashik"
    assert profile.taluka == "dindori"


def test_application_location_schema_validation():
    locs = load_locations_data()
    assert len(locs) >= 6
    for loc in locs:
        assert isinstance(loc, ApplicationLocation)
        assert loc.id
        assert loc.state
        assert loc.office_name
        assert loc.office_type
        assert loc.address
        assert loc.source_url and loc.source_url.startswith("https://")


# ---------------------------------------------------------------------------
# 2. Location Resolver (find_locations)
# ---------------------------------------------------------------------------

def test_find_locations_exact_taluka_match():
    # Dindori taluka has a specific Tahsil Office for Majhi Ladki Bahin
    matches = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert len(matches) == 1
    loc = matches[0]
    assert loc.id == "mah-nsk-dindori-tahsil"
    assert loc.taluka == "dindori"
    assert loc.district == "nashik"


def test_find_locations_district_fallback():
    # PM-KISAN in Sinnar taluka has no Sinnar-specific taluka entry,
    # so it falls back to the Nashik district agriculture office (DSAO)
    matches = find_locations(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="nashik",
        taluka="sinnar",
    )
    assert len(matches) == 1
    loc = matches[0]
    assert loc.id == "mah-nsk-dsao-agri"
    assert loc.district == "nashik"
    assert loc.taluka is None


def test_find_locations_state_level_fallback():
    # PM-KISAN in Satara district (not in pilot district list)
    # falls back to State Commissionerate of Agriculture
    matches = find_locations(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="satara",
        taluka="karad",
    )
    assert len(matches) == 1
    loc = matches[0]
    assert loc.id == "mah-state-krishi-ayuktalaya"
    assert loc.district is None
    assert loc.taluka is None


def test_find_locations_scheme_filtering():
    # Health scheme PM-JAY in Nashik should match civil hospital, NOT agriculture office
    matches = find_locations(
        scheme_id="pm-jay",
        state="maharashtra",
        district="nashik",
    )
    assert len(matches) == 1
    assert matches[0].id == "mah-nsk-civil-hospital"
    assert matches[0].office_type == "civil_hospital"


def test_find_locations_state_filtering_no_match():
    # Another state (e.g., bihar) where we have no data returns an empty list
    matches = find_locations(
        scheme_id="pm-kisan",
        state="bihar",
        district="patna",
    )
    assert matches == []


def test_find_locations_missing_state_returns_empty():
    matches = find_locations(
        scheme_id="pm-kisan",
        state=None,
    )
    assert matches == []


def test_find_locations_wildcard_scheme_matches_general_offices():
    # Collector office in Pune matches wildcard "*" schemes
    matches = find_locations(
        scheme_id="any-arbitrary-scheme",
        state="maharashtra",
        district="pune",
    )
    assert any(loc.id == "mah-pun-collectorate" for loc in matches)


# ---------------------------------------------------------------------------
# 3. API Integration (/api/recommend and /api/schemes/{id})
# ---------------------------------------------------------------------------

def test_api_recommend_without_district_taluka(client):
    # Existing request format without district/taluka works cleanly
    payload = {
        "profile": {
            "age": 42,
            "gender": "male",
            "state": "maharashtra",
            "is_farmer": True,
            "owns_land": True,
        },
        "category": "farmers",
    }
    resp = client.post("/api/recommend", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["results"]) > 0

    # Because state was provided, state-level fallback locations are attached
    pm_kisan_result = next((r for r in data["results"] if r["scheme"]["id"] == "pm-kisan"), None)
    assert pm_kisan_result is not None
    assert "locations" in pm_kisan_result
    assert len(pm_kisan_result["locations"]) > 0
    # State-level fallback was resolved
    assert pm_kisan_result["locations"][0]["id"] == "mah-state-krishi-ayuktalaya"


def test_api_recommend_with_district_taluka(client):
    payload = {
        "profile": {
            "age": 25,
            "gender": "female",
            "state": "maharashtra",
            "district": "nashik",
            "taluka": "dindori",
            "annual_income": 50000,
        },
        "category": "women",
    }
    resp = client.post("/api/recommend", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    ladki_bahin = next((r for r in data["results"] if r["scheme"]["id"] == "majhi-ladki-bahin"), None)
    assert ladki_bahin is not None
    assert len(ladki_bahin["locations"]) == 1
    assert ladki_bahin["locations"][0]["id"] == "mah-nsk-dindori-tahsil"
    assert ladki_bahin["locations"][0]["office_type"] == "tahsil_office"
    assert (
        ladki_bahin["scheme"]["application_guidance"]["offline_application"]["available"]
        is True
    )
    assert (
        len(ladki_bahin["scheme"]["application_guidance"]["offline_application"]["locations"])
        == 1
    )


def test_api_scheme_detail_with_location_params(client):
    resp = client.get(
        "/api/schemes/majhi-ladki-bahin?state=maharashtra&district=pune&taluka=haveli"
    )
    assert resp.status_code == 200
    data = resp.json()
    scheme = data["scheme"]
    guidance = scheme["application_guidance"]
    assert guidance["offline_application"]["available"] is True
    assert len(guidance["offline_application"]["locations"]) == 1
    assert guidance["offline_application"]["locations"][0]["id"] == "mah-pun-haveli-tahsil"


def test_api_locations_endpoint(client):
    resp = client.get("/api/locations?state=maharashtra&district=nashik&taluka=dindori")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(loc["id"] == "mah-nsk-dindori-tahsil" for loc in data)


# ---------------------------------------------------------------------------
# 4. Critical Edge Cases: Jurisdiction Scoping
# ---------------------------------------------------------------------------

def test_edge_case_1_state_only_does_not_return_district_offices():
    """Case 1: state=maharashtra, district=None, taluka=None.
    Must NOT return Nashik or Pune district-specific offices."""
    matches = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district=None,
        taluka=None,
    )
    # Majhi Ladki Bahin only has district/taluka offices (Dindori/Haveli).
    # Since citizen gave no district, none of those district offices must be returned.
    assert matches == []
    for loc in matches:
        assert loc.district is None, "Must not return district-specific office when district is None"


def test_edge_case_2_dindori_nashik():
    """Case 2: state=maharashtra, district=nashik, taluka=dindori.
    Dindori/Nashik appropriate locations can be returned."""
    matches = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="nashik",
        taluka="dindori",
    )
    assert len(matches) == 1
    assert matches[0].id == "mah-nsk-dindori-tahsil"
    assert matches[0].district == "nashik"
    assert matches[0].taluka == "dindori"


def test_edge_case_3_haveli_pune():
    """Case 3: state=maharashtra, district=pune, taluka=haveli.
    Haveli/Pune appropriate locations can be returned."""
    matches = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="pune",
        taluka="haveli",
    )
    assert len(matches) == 1
    assert matches[0].id == "mah-pun-haveli-tahsil"
    assert matches[0].district == "pune"
    assert matches[0].taluka == "haveli"


def test_edge_case_4_unrelated_district():
    """Case 4: unrelated district (e.g. Kolhapur).
    Must NOT return unrelated Nashik or Pune offices."""
    matches = find_locations(
        scheme_id="majhi-ladki-bahin",
        state="maharashtra",
        district="kolhapur",
        taluka="karvir",
    )
    assert matches == [], "Must not return Nashik or Pune offices for a Kolhapur citizen"


def test_edge_case_5_state_level_location_when_appropriate():
    """Case 5: state-level location.
    State-level headquarters (district=None, taluka=None) may be returned when appropriate."""
    matches = find_locations(
        scheme_id="pm-kisan",
        state="maharashtra",
        district="satara",
    )
    assert len(matches) == 1
    assert matches[0].id == "mah-state-krishi-ayuktalaya"
    assert matches[0].district is None
    assert matches[0].taluka is None
