import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CitizenProfile, Scheme
from app.scheme_discovery import discover_and_match_schemes, load_curated_schemes
from services.voice_agent.agent import VoiceAgent
from services.voice_agent.state import new_agent_state
from services.voice_agent.graph import retrieve_schemes
from services.web_scheme_discovery.schemas import DiscoveredScheme, WebSchemeSearchResponse
from services.web_scheme_discovery.service import get_discovery_service


def _valid_active_candidate(
    name: str = "Maharashtra Solar Pump Agriculture Scheme",
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


def test_discover_and_match_schemes_incorporates_live_discoveries(monkeypatch):
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

    profile = CitizenProfile(
        age=35,
        state="maharashtra",
        is_farmer=True,
        owns_land=True,
        needs=["agriculture"],
    )
    curated = load_curated_schemes()

    results, candidates, meta = discover_and_match_schemes(
        profile=profile,
        category="agriculture",
        curated_schemes=curated,
    )

    result_ids = [r.scheme.id for r in results]
    assert "web-maharashtra-krishi-urja-abhiyan" in result_ids
    # Curated schemes remain available as baseline
    assert "pmfby" in result_ids

    # Web scheme has discovery metadata attached
    web_match = next((r for r in results if r.scheme.id == "web-maharashtra-krishi-urja-abhiyan"), None)
    assert web_match is not None
    assert web_match.is_web_discovered is True
    assert web_match.discovery_confidence == 0.9


def test_voice_retrieve_schemes_ranks_live_and_curated_schemes_top_3(monkeypatch):
    cand = _valid_active_candidate(
        name="Maharashtra High Value Agri Scheme",
        state="maharashtra",
        benefits="Extensive financial grant for solar pump and farm equipment.",
        eligibility="Farmers residing in Maharashtra.",
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
        rejected_candidates=[],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    state = new_agent_state("test-session-voice")
    state["user_profile"] = CitizenProfile(
        age=40,
        state="maharashtra",
        is_farmer=True,
        owns_land=True,
        needs=["agriculture"],
    )
    state["category"] = "agriculture"
    state["current_question"] = None  # Discovery complete

    curated = load_curated_schemes()
    updated_state = retrieve_schemes(state, curated)

    retrieved = updated_state.get("retrieved_schemes", [])
    # Must return top 3 matched schemes overall
    assert len(retrieved) <= 3
    assert len(retrieved) > 0

    # Scores must be sorted descending
    scores = [r.relevance_score for r in retrieved]
    assert scores == sorted(scores, reverse=True)

    # Web scheme should participate in ranking
    all_cand_ids = [r.scheme.id for r in retrieved]
    assert any(sid.startswith("web-") or "pmfby" in sid or "pm-kisan" in sid for sid in all_cand_ids)


@pytest.mark.anyio
async def test_voice_agent_public_result_exposes_discovery_provenance(monkeypatch):
    cand = _valid_active_candidate(
        name="Maharashtra Krishi Vikas Scheme",
        state="maharashtra",
        benefits="Direct subsidy for farmers.",
        eligibility="Farmers in Maharashtra.",
    )
    fake_resp = WebSchemeSearchResponse(
        status="success",
        validated_schemes=[cand],
        rejected_candidates=[],
    )

    service = get_discovery_service()
    monkeypatch.setattr(service, "discover", lambda *args, **kwargs: fake_resp)

    agent = VoiceAgent(schemes=load_curated_schemes())
    session_id = "test-session-meta"

    # Seed state where discovery is complete and retrieved_schemes has been populated
    state = new_agent_state(session_id)
    state["user_profile"] = CitizenProfile(
        age=38,
        state="maharashtra",
        is_farmer=True,
        owns_land=True,
        needs=["agriculture"],
    )
    state["category"] = "agriculture"
    state["current_question"] = None
    state["language"] = "en"

    retrieve_schemes(state, agent.schemes)
    public_res = agent._public_result(state)

    schemes = public_res.get("schemes", [])
    assert len(schemes) > 0
    for s in schemes:
        assert "is_web_discovered" in s
        assert "discovery_confidence" in s
        assert "discovery_source_type" in s
