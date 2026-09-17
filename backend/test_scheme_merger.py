"""Tests for the LIVE-FIRST web scheme discovery and recommendation integration.

Verifies that:
1. Live discovery succeeds -> live validated schemes form primary pool (curated catalog is NOT blindly appended).
2. Live discovered duplicate of PM-KISAN -> curated PM-KISAN canonical version is used.
3. Live discovery fails -> schemes.json fallback is used, /api/recommend succeeds.
4. Live discovery returns zero validated schemes -> curated fallback is used.
5. Cached discovery exists -> no second Tavily call is made.
6. Different profiles -> do not reuse another profile's cached discoveries.
7. Web result -> passes through match_schemes() deterministically.
8. Wrong-state web scheme -> rejected by match_schemes().
9. Irrelevant web scheme -> does not bypass matcher threshold.
10. Existing curated fallback behavior -> scores/order unchanged when discovery fails.
11. Provenance metadata survives.
12. Existing location/application guidance still executes.
13. Tavily timeout is bounded and falls back safely.
"""

from copy import deepcopy
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, load_schemes_data
from app.matching import match_schemes
from app.schemas import CitizenProfile, Scheme
from services.web_scheme_discovery.cache import get_shared_cache, profile_cache_key
from services.web_scheme_discovery.exceptions import TavilyAPIError
from services.web_scheme_discovery.merger import (
    build_live_scheme_pool,
    get_cached_web_schemes,
    merge_validated_web_schemes,
    perform_live_discovery,
)
from services.web_scheme_discovery.schemas import (
    DiscoveredScheme,
    DiscoveryMetadata,
    WebDiscoveryProfile,
    WebSchemeSearchResponse,
)
from services.web_scheme_discovery.service import get_discovery_service


@pytest.fixture(autouse=True)
def clear_shared_cache():
    """Ensure shared cache is cleared before and after each test."""
    cache = get_shared_cache()
    cache.clear()
    yield
    cache.clear()


def _valid_active_candidate(
    name: str = "Maharashtra Solar Agriculture Pump Scheme",
    state: str = "maharashtra",
    benefits: str = "Subsidized solar pump for agricultural irrigation.",
    eligibility: str = "Must be a farmer resident in Maharashtra with agricultural land.",
    app_url: str = "https://mahadiscom.in/solar",
    source_url: str = "https://mahadiscom.in/solar",
    confidence: float = 0.9,
) -> DiscoveredScheme:
    return DiscoveredScheme(
        scheme_name=name,
        normalized_name=name.lower(),
        state=state,
        description=f"{name} provides {benefits}",
        benefits=[benefits],
        eligibility=[eligibility],
        documents_required=["Aadhaar Card", "7/12 Extract"],
        application_url=app_url,
        source_url=source_url,
        source_urls=[source_url],
        source_type="official_government",
        active_status="active",
        validation_status="verified",
        validation_reasons=["Confirmed on official government portal"],
        confidence=confidence,
    )


# 1. Live discovery succeeds: live validated schemes are used, curated catalog is NOT blindly appended
def test_live_discovery_succeeds_primary_pool_not_blindly_appended(monkeypatch):
    cand = _valid_active_candidate(
        name="Maharashtra Krishi Urja Abhiyan",
        state="maharashtra",
        benefits="Farm solar electrification financial assistance.",
        eligibility="Farmers in Maharashtra.",
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
        rejected_candidates=[],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "is_farmer": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "web-maharashtra-krishi-urja-abhiyan" in result_ids
    # The curated catalog (e.g. pm-kisan, pm-svanidhi, apy) was NOT blindly appended
    assert "pm-svanidhi" not in result_ids
    assert "pmay-u" not in result_ids
    assert "pm-kisan" not in result_ids


# 2. Live discovered duplicate of PM-KISAN: curated PM-KISAN canonical version is used
def test_live_discovered_pm_kisan_uses_curated_canonical_version(monkeypatch):
    cand = _valid_active_candidate(
        name="Pradhan Mantri Kisan Samman Nidhi",
        state="central",
        benefits="Income support of Rs 6000 per year.",
        eligibility="All landholding farmer families.",
        app_url="https://pmkisan.gov.in",
        source_url="https://pmkisan.gov.in",
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
        rejected_candidates=[],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "is_farmer": True,
        "owns_land": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()

    result_ids = [r["scheme"]["id"] for r in data["results"]]
    # Curated canonical PM-KISAN is used, NOT web-pm-kisan
    assert "pm-kisan" in result_ids
    assert not any(rid.startswith("web-pm-kisan") for rid in result_ids)
    # The curated version retains is_web_discovered=False
    pm_res = next(r for r in data["results"] if r["scheme"]["id"] == "pm-kisan")
    assert pm_res["is_web_discovered"] is False


# 3. Live discovery fails: schemes.json fallback is used, /api/recommend still succeeds
def test_live_discovery_fails_uses_curated_fallback(monkeypatch):
    service = get_discovery_service()

    def _fail_discover(*args, **kwargs):
        raise TavilyAPIError("Tavily network connection timeout")

    monkeypatch.setattr(service, "discover", _fail_discover)

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "is_farmer": True,
        "owns_land": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Curated schemes from schemes.json returned as fallback
    assert data["count"] > 0
    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "pm-kisan" in result_ids
    assert all(r["is_web_discovered"] is False for r in data["results"])


# 4. Live discovery returns zero validated schemes: curated fallback is used
def test_live_discovery_zero_validated_schemes_uses_curated_fallback(monkeypatch):
    fake_resp = WebSchemeSearchResponse(
        status="empty",
        validated_schemes=[],
        rejected_candidates=[],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "is_farmer": True,
        "owns_land": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    # Curated fallback loaded
    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "pm-kisan" in result_ids
    assert all(r["is_web_discovered"] is False for r in data["results"])


# 5. Cached discovery exists: no second Tavily call is made
def test_cached_discovery_exists_bypasses_live_tavily(monkeypatch):
    cand = _valid_active_candidate(
        name="Cached Solar Scheme",
        state="maharashtra",
    )
    search_response = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
        rejected_candidates=[],
    )

    wp = WebDiscoveryProfile(
        state="maharashtra",
        occupation="farmer",
        farmer=True,
    )
    cache = get_shared_cache()
    key = profile_cache_key(wp.model_dump(), "15")
    cache.set(key, search_response)

    call_count = {"calls": 0}

    def _unexpected_discover(*args, **kwargs):
        call_count["calls"] += 1
        raise AssertionError("discover() should NOT be called when cache hit exists!")

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", _unexpected_discover)

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "is_farmer": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    assert call_count["calls"] == 0
    data = resp.json()
    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "web-cached-solar-scheme" in result_ids


# 6. Different profiles do not reuse another profile's cached discoveries
def test_different_profiles_do_not_leak_cache(monkeypatch):
    cache = get_shared_cache()
    # Cache for farmer in Maharashtra
    farmer_wp = WebDiscoveryProfile(
        state="maharashtra",
        occupation="farmer",
        farmer=True,
    )
    farmer_cand = _valid_active_candidate(name="Farmer Irrigation Scheme")
    cache.set(
        profile_cache_key(farmer_wp.model_dump(), "15"),
        WebSchemeSearchResponse(status="success", validated_schemes=[farmer_cand]),
    )

    # Student in Karnataka
    student_cand = _valid_active_candidate(
        name="Karnataka Student Scholarship",
        state="karnataka",
        benefits="Tuition support for college students.",
        eligibility="Students in Karnataka.",
    )

    service = get_discovery_service()
    monkeypatch.setattr(
        service,
        "discover",
        lambda *args, **kwargs: WebSchemeSearchResponse(status="success", validated_schemes=[student_cand]),
    )

    client = TestClient(app)
    student_profile = {
        "state": "karnataka",
        "is_student": True,
        "occupation": "student",
    }
    resp = client.post("/api/recommend", json={"profile": student_profile})
    assert resp.status_code == 200
    data = resp.json()

    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "web-karnataka-student-scholarship" in result_ids
    # Did NOT leak farmer scheme
    assert "web-farmer-irrigation-scheme" not in result_ids


# 7. Web result passes through match_schemes() deterministically
def test_web_result_passes_through_match_schemes():
    curated = load_schemes_data()
    cand = _valid_active_candidate(
        name="Vidarbha Cotton Subsidy",
        state="maharashtra",
        benefits="Financial assistance for cotton growers.",
        eligibility="Cotton farmers in Maharashtra.",
    )
    pool, meta = build_live_scheme_pool(curated, [cand])
    assert len(pool) == 1
    assert "web-vidarbha-cotton-subsidy" in meta

    mh_farmer = CitizenProfile(state="maharashtra", is_farmer=True, occupation="farmer")
    results = match_schemes(mh_farmer, pool)
    assert len(results) == 1
    assert results[0].scheme.id == "web-vidarbha-cotton-subsidy"
    assert results[0].relevance_score >= 3
    assert len(results[0].matched_reasons) > 0


# 8. Wrong-state web scheme is rejected by match_schemes()
def test_wrong_state_web_scheme_rejected_by_match_schemes(monkeypatch):
    cand = _valid_active_candidate(
        name="Gujarat Khedut Sahay Yojana",
        state="gujarat",
        benefits="Financial assistance for Gujarat farmers.",
        eligibility="Farmers resident in Gujarat.",
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    client = TestClient(app)
    # Citizen is in Maharashtra
    profile = {"state": "maharashtra", "is_farmer": True, "occupation": "farmer"}
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "web-gujarat-khedut-sahay-yojana" not in result_ids


# 9. Irrelevant web scheme does not bypass relevance threshold
def test_irrelevant_web_scheme_does_not_bypass_threshold(monkeypatch):
    cand = DiscoveredScheme(
        scheme_name="National Astronomy Telescope Grant",
        normalized_name="national astronomy telescope grant",
        state="all-india",
        description="Grants for amateur stargazing clubs.",
        benefits=["Binoculars and star maps."],
        eligibility=["Registered astronomy clubs."],
        application_url="https://dst.gov.in/astro",
        source_url="https://dst.gov.in/astro",
        source_type="official_government",
        active_status="active",
        validation_status="verified",
        confidence=0.9,
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    client = TestClient(app)
    profile = {"state": "maharashtra", "is_farmer": True, "occupation": "farmer"}
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    result_ids = [r["scheme"]["id"] for r in data["results"]]
    assert "web-national-astronomy-telescope-grant" not in result_ids


# 10. Existing curated fallback behavior: scores and order remain unchanged when discovery fails
def test_existing_curated_fallback_behavior_scores_order_unchanged(monkeypatch):
    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: WebSchemeSearchResponse(status="empty", validated_schemes=[]))

    schemes = load_schemes_data()
    profile = CitizenProfile(
        state="maharashtra",
        is_farmer=True,
        owns_land=True,
        occupation="farmer",
        gender="female",
        age=35,
    )
    direct_results = match_schemes(profile, schemes)

    client = TestClient(app)
    resp = client.post("/api/recommend", json={"profile": profile.model_dump()})
    assert resp.status_code == 200
    api_results = resp.json()["results"]

    assert len(api_results) == len(direct_results)
    for api_r, direct_r in zip(api_results, direct_results):
        assert api_r["scheme"]["id"] == direct_r.scheme.id
        assert api_r["relevance_score"] == direct_r.relevance_score
        assert api_r["is_web_discovered"] is False


# 11. Provenance metadata survives
def test_provenance_metadata_survives(monkeypatch):
    cand = _valid_active_candidate(
        name="Unique Agricultural Subsidy",
        confidence=0.94,
    )
    cand.validation_reasons = ["Verified on agriculture.gov.in", "Budget active"]

    service = get_discovery_service()
    monkeypatch.setattr(
        service,
        "discover",
        lambda *args, **kwargs: WebSchemeSearchResponse(status="success", validated_schemes=[cand]),
    )

    client = TestClient(app)
    profile = {"state": "maharashtra", "is_farmer": True, "occupation": "farmer"}
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()

    res = next(r for r in data["results"] if r["scheme"]["id"] == "web-unique-agricultural-subsidy")
    assert res["is_web_discovered"] is True
    assert res["discovery_confidence"] == 0.94
    assert res["discovery_source_type"] == "official_government"
    assert "Verified on agriculture.gov.in" in res["validation_reasons"]


# 12. Existing location/application guidance still executes
def test_location_guidance_executes_for_live_results(monkeypatch):
    cand = _valid_active_candidate(
        name="Nashik Grape Cultivation Subsidy",
        state="maharashtra",
    )
    service = get_discovery_service()
    monkeypatch.setattr(
        service,
        "discover",
        lambda *args, **kwargs: WebSchemeSearchResponse(status="success", validated_schemes=[cand]),
    )

    client = TestClient(app)
    profile = {
        "state": "maharashtra",
        "district": "nashik",
        "taluka": "dindori",
        "is_farmer": True,
        "occupation": "farmer",
    }
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    assert "location_requirement" in data
    res = data["results"][0]
    assert "locations" in res
    assert res["scheme"]["application_guidance"]["online_application"]["available"] is True


# 13. Tavily timeout is bounded and falls back safely
def test_tavily_timeout_falls_back_safely(monkeypatch):
    service = get_discovery_service()

    def _timeout(*args, **kwargs):
        raise httpx.TimeoutException("ReadTimeout after 15.0s")

    monkeypatch.setattr(service, "discover", _timeout)

    client = TestClient(app)
    profile = {"state": "maharashtra", "is_farmer": True, "occupation": "farmer"}
    resp = client.post("/api/recommend", json={"profile": profile})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] > 0
    # Curated fallback executed
    assert all(r["is_web_discovered"] is False for r in data["results"])
