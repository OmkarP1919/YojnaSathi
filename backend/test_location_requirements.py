"""
Targeted unit tests for Step 1 of Smart Location Questioning.
Tests app.location_requirements.evaluate_location_requirement.
"""
import pytest
from app.location_requirements import evaluate_location_requirement
from app.schemas import (
    ApplicationLocation,
    CitizenProfile,
    Scheme,
    SchemeMatchResult,
)


def _make_scheme(
    scheme_id: str,
    state: str = "all-india",
    category: str = "agriculture",
) -> Scheme:
    return Scheme(
        id=scheme_id,
        name={"en": f"Scheme {scheme_id}"},
        description={"en": "Test description"},
        category=category,
        target_groups=["farmers"],
        benefits={"en": ["Test benefit"]},
        eligibility=["Test eligibility"],
        required_information={"en": ["Aadhaar"]},
        state=state,
        department={"en": "Test Dept"},
        application_url="https://example.gov.in",
        source_url="https://example.gov.in",
        last_verified="2026-09-17",
    )


def _make_match_result(scheme: Scheme, score: int = 8) -> SchemeMatchResult:
    return SchemeMatchResult(
        scheme=scheme,
        relevance_score=score,
        matched_reasons=["Test match"],
        reason_codes=[],
        missing_information=[],
        locations=[],
    )


@pytest.fixture
def mock_locations_pool():
    return [
        # Taluka-specific office for Scheme A in Nashik/Dindori
        ApplicationLocation(
            id="loc-dindori",
            scheme_ids=["scheme-taluka"],
            categories=["agriculture"],
            state="maharashtra",
            district="nashik",
            taluka="dindori",
            office_name={"en": "Dindori Tahsil Office"},
            office_type="tahsil_office",
            address={"en": "Dindori, Nashik"},
            contact_phone="02557-111111",
        ),
        # District-level office for Scheme B in Nashik (taluka is None)
        ApplicationLocation(
            id="loc-nashik-dist",
            scheme_ids=["scheme-district-only"],
            categories=["agriculture"],
            state="maharashtra",
            district="nashik",
            taluka=None,
            office_name={"en": "Nashik District Office"},
            office_type="district_office",
            address={"en": "Nashik City"},
            contact_phone="0253-222222",
        ),
        # State-level office in Pune
        ApplicationLocation(
            id="loc-state-hq",
            scheme_ids=["scheme-all-india"],
            categories=["agriculture"],
            state="maharashtra",
            district=None,
            taluka=None,
            office_name={"en": "State HQ Pune"},
            office_type="state_office",
            address={"en": "Pune"},
        ),
    ]


# 1. All-India scheme + no state/district/taluka
def test_all_india_scheme_no_location(mock_locations_pool):
    scheme = _make_scheme("scheme-all-india", state="all-india")
    profile = CitizenProfile()  # state=None, district=None, taluka=None
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    # State is NOT required for scheme eligibility
    assert result.state_required_for_eligibility is False
    # Cataloged physical offices exist for this scheme in locations pool
    assert result.has_physical_offices is True
    # Because state is unknown, next level needed to narrow physical offices is "state"
    assert result.next_needed_level == "state"


# 2. All-India scheme + state only
def test_all_india_scheme_state_only(mock_locations_pool):
    scheme = _make_scheme("scheme-all-india", state="all-india")
    profile = CitizenProfile(state="maharashtra")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.state_required_for_eligibility is False
    assert result.has_physical_offices is True
    # State-level office has district=None, so no district needed
    assert result.next_needed_level is None


# 3. Maharashtra scheme + no state
def test_maharashtra_scheme_no_state(mock_locations_pool):
    scheme = _make_scheme("scheme-mah", state="maharashtra")
    profile = CitizenProfile()  # state=None
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    # State IS required for eligibility
    assert result.state_required_for_eligibility is True
    assert result.next_needed_level == "state"


# 4. Maharashtra scheme + Maharashtra state
def test_maharashtra_scheme_with_state(mock_locations_pool):
    scheme = _make_scheme("scheme-mah", state="maharashtra")
    profile = CitizenProfile(state="maharashtra")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    # State is already known
    assert result.state_required_for_eligibility is False
    # No physical offices cataloged for scheme-mah in mock pool
    assert result.has_physical_offices is False
    assert result.next_needed_level is None


# 5. Physical office available + no district
def test_physical_office_available_no_district(mock_locations_pool):
    scheme = _make_scheme("scheme-district-only", state="all-india")
    profile = CitizenProfile(state="maharashtra")  # district=None
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.state_required_for_eligibility is False
    assert result.has_physical_offices is True
    assert result.next_needed_level == "district"
    assert "nashik" in result.supported_districts


# 6. District-level office + district known
def test_district_level_office_district_known(mock_locations_pool):
    scheme = _make_scheme("scheme-district-only", state="all-india")
    profile = CitizenProfile(state="maharashtra", district="nashik")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.has_physical_offices is True
    # Only district-level office exists (taluka is None), so do NOT request taluka
    assert result.supported_talukas == []
    assert result.next_needed_level is None


# 7. Taluka-specific office + district known but taluka missing
def test_taluka_specific_office_taluka_missing(mock_locations_pool):
    scheme = _make_scheme("scheme-taluka", state="maharashtra")
    profile = CitizenProfile(state="maharashtra", district="nashik")  # taluka=None
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.has_physical_offices is True
    assert result.supported_talukas == ["dindori"]
    # Taluka is missing and taluka-specific office exists
    assert result.next_needed_level == "taluka"


# 8. Taluka-specific office + taluka known
def test_taluka_specific_office_taluka_known(mock_locations_pool):
    scheme = _make_scheme("scheme-taluka", state="maharashtra")
    profile = CitizenProfile(state="maharashtra", district="nashik", taluka="dindori")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.has_physical_offices is True
    assert result.supported_talukas == ["dindori"]
    assert result.next_needed_level is None


# 9. Unrelated/non-pilot district
def test_non_pilot_district(mock_locations_pool):
    scheme = _make_scheme("scheme-taluka", state="maharashtra")
    profile = CitizenProfile(state="maharashtra", district="nagpur")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    # In Nagpur, no physical offices in the mock pool
    assert result.supported_talukas == []
    assert result.next_needed_level is None


# 10. No physical office data
def test_no_physical_office_data(mock_locations_pool):
    scheme = _make_scheme("scheme-no-office", state="all-india")
    profile = CitizenProfile(state="karnataka")
    result = evaluate_location_requirement(
        profile, [_make_match_result(scheme)], locations_pool=mock_locations_pool
    )

    assert result.has_physical_offices is False
    assert result.next_needed_level is None
    assert result.supported_districts == []
    assert result.supported_talukas == []


# 11. Live dataset test with actual locations.json and PM-KISAN
def test_live_dataset_pm_kisan():
    from app.matching import match_schemes
    from app.main import load_schemes_data

    schemes = load_schemes_data()
    # Test PM-KISAN without district or taluka
    profile = CitizenProfile(is_farmer=True, owns_land=True, state="maharashtra")
    results = match_schemes(profile, schemes, category="farmers")
    assert len(results) > 0

    req = evaluate_location_requirement(profile, results)
    assert req.state_required_for_eligibility is False
    assert req.has_physical_offices is True
    assert req.next_needed_level == "district"
    assert "nashik" in req.supported_districts
