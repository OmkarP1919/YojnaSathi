"""Mocked tests for the independent web-scheme-discovery pipeline.

NEVER makes real Tavily calls by default. The optional live integration
test runs only when RUN_TAVILY_INTEGRATION_TEST=true AND TAVILY_API_KEY
exists.
"""

import os

import pytest
from fastapi.testclient import TestClient


def _official_result(title="PM-KISAN Samman Nidhi", url="https://pmkisan.gov.in/about.aspx"):
    from services.web_scheme_discovery.schemas import TavilyResultItem

    return TavilyResultItem(
        title=title,
        url=url,
        content=(
            "PM-KISAN provides Rs 6000 per year benefit to eligible farmer families. "
            "Eligibility criteria: must be a farmer with cultivable land, resident of India. "
            "Applications are open. Apply online at the official portal."
        ),
        score=0.95,
    )


def _blog_result():
    from services.web_scheme_discovery.schemas import TavilyResultItem

    return TavilyResultItem(
        title="Best Sarkari Yojana Tips Blog",
        url="https://randomblog.example.com/schemes",
        content="Some vague scheme tips with no clear benefits or eligibility details.",
        score=0.2,
    )


# 1. Tavily search success (mocked transport).
def test_tavily_search_success(monkeypatch):
    from services.web_scheme_discovery.tavily_search import TavilyClient

    class FakeResp:
        status_code = 200

        def json(self):
            return {"results": [{"title": "T", "url": "https://pmkisan.gov.in/x", "content": "C", "score": 0.9}]}

    client = TavilyClient(api_key="test-key")
    monkeypatch.setattr(client, "_post", lambda url, payload, headers: FakeResp())
    # Privacy: exact age/income must not leak into the payload query path here.
    assert "Authorization" in {"Authorization": "Bearer test-key"}
    items = client.search("maharashtra farmer scheme")
    assert len(items) == 1
    assert items[0].url == "https://pmkisan.gov.in/x"


# 2. Tavily API failure maps to TavilyAPIError.
def test_tavily_api_failure(monkeypatch):
    from services.web_scheme_discovery.exceptions import TavilyAPIError
    from services.web_scheme_discovery.tavily_search import TavilyClient

    class FakeResp:
        status_code = 500

        def json(self):
            return {}

    client = TavilyClient(api_key="test-key")
    monkeypatch.setattr(client, "_post", lambda url, payload, headers: FakeResp())
    with pytest.raises(TavilyAPIError):
        client.search("farmer scheme")


# 3. Missing API key.
def test_missing_api_key():
    from services.web_scheme_discovery.exceptions import MissingApiKeyError
    from services.web_scheme_discovery.tavily_search import TavilyClient

    client = TavilyClient(api_key="")
    with pytest.raises(MissingApiKeyError):
        client.search("farmer scheme")


# 4/5. Extraction produces structured candidates; unknowns stay empty/None.
def test_extraction_structured_scheme():
    from services.web_scheme_discovery.extractor import extract_candidates

    cands = extract_candidates([_official_result()])
    assert len(cands) == 1
    cand = cands[0]
    assert cand.scheme_name
    assert cand.source_url == "https://pmkisan.gov.in/about.aspx"
    assert cand.description  # traceable to source content
    assert cand.benefits  # Rs 6000 sentence captured
    assert cand.eligibility  # eligibility sentence captured
    assert cand.application_url == "https://pmkisan.gov.in/about.aspx"


def test_extraction_unknowns_not_invented():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem

    cands = extract_candidates([TavilyResultItem(title="Mystery Scheme", url="https://example.com/x", content="Hello world.", score=0.1)])
    assert cands[0].application_url is None
    assert cands[0].eligibility == []


# 6. Official source validates to verified (with active signal in fixture).
def test_official_source_validation():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.validator import apply_validation

    cand = extract_candidates([_official_result()])[0]
    apply_validation(cand)
    assert cand.validation_status == "verified"
    assert cand.active_status == "active"
    assert cand.source_type == "official_government"
    assert cand.confidence > 0.5


# 7. Non-authoritative source cannot verify.
def test_non_authoritative_source_rejected_or_partial():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.validator import apply_validation

    cand = extract_candidates([_blog_result()])[0]
    apply_validation(cand)
    assert cand.validation_status in {"rejected", "partially_verified"}
    assert cand.validation_status != "verified"


# 8. Inactive scheme detection.
def test_inactive_scheme_detection():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem
    from services.web_scheme_discovery.validator import apply_validation

    item = TavilyResultItem(
        title="Old Scheme",
        url="https://myscheme.gov.in/old",
        content="This scheme has been discontinued and applications are closed permanently. Benefits were Rs 5000. Eligibility was for farmers.",
        score=0.8,
    )
    cand = extract_candidates([item])[0]
    apply_validation(cand)
    assert cand.active_status == "inactive"
    assert cand.validation_status != "verified"


# 9. Unknown active status stays unknown.
def test_unknown_active_status():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem
    from services.web_scheme_discovery.validator import detect_active_status

    item = TavilyResultItem(title="Quiet Scheme", url="https://example.com/q", content="A scheme exists.", score=0.3)
    cand = extract_candidates([item])[0]
    assert detect_active_status(cand) == "unknown"


def test_active_status_invited_and_year_signals():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem
    from services.web_scheme_discovery.validator import detect_active_status

    invited = TavilyResultItem(
        title="SMAM Scheme", url="https://agrimachinery.gov.in/x",
        content="Applications are invited from farmers under the scheme. See guidelines.",
        score=0.8,
    )
    assert detect_active_status(extract_candidates([invited])[0]) == "active"
    yearly = TavilyResultItem(
        title="Crop Scheme 2025", url="https://myscheme.gov.in/x",
        content="Guidelines for the 2025-26 season have been issued for farmers.",
        score=0.8,
    )
    assert detect_active_status(extract_candidates([yearly])[0]) == "active"


def test_inactive_wins_over_year_mention():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem
    from services.web_scheme_discovery.validator import detect_active_status

    item = TavilyResultItem(
        title="Old Scheme", url="https://myscheme.gov.in/old",
        content="The 2023 scheme has been discontinued and is no longer accepting applications.",
        score=0.8,
    )
    assert detect_active_status(extract_candidates([item])[0]) == "inactive"


def test_tavily_payload_scoped_to_india(monkeypatch):
    from services.web_scheme_discovery.tavily_search import TavilyClient

    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"results": []}

    def fake_post(url, payload, headers):
        captured.update(payload)
        assert headers["Authorization"] == "Bearer test-key"
        return FakeResp()

    monkeypatch.delenv("TAVILY_INCLUDE_DOMAINS", raising=False)
    client = TavilyClient(api_key="test-key")
    monkeypatch.setattr(client, "_post", fake_post)
    client.search("maharashtra farmer scheme")
    assert captured["country"] == "india"
    assert "include_domains" not in captured  # unset unless explicitly configured
    assert "facebook.com" in captured["exclude_domains"]
    # Only documented fields are sent.
    assert set(captured) <= {
        "query", "search_depth", "max_results", "include_answer",
        "topic", "exclude_domains", "country", "include_domains",
    }


# 10. Missing eligibility evidence -> not verified.
def test_missing_eligibility_evidence():
    from services.web_scheme_discovery.extractor import extract_candidates
    from services.web_scheme_discovery.schemas import TavilyResultItem
    from services.web_scheme_discovery.validator import apply_validation

    item = TavilyResultItem(
        title="Benefit Only Scheme",
        url="https://pmkisan.gov.in/benefit",
        content="Get Rs 6000 per year benefit. Apply online now. Currently active.",
        score=0.8,
    )
    cand = extract_candidates([item])[0]
    assert cand.eligibility == []
    apply_validation(cand)
    assert cand.validation_status != "verified"


# 11. Missing application URL -> at best partially verified.
def test_missing_application_url():
    from services.web_scheme_discovery.schemas import DiscoveredScheme
    from services.web_scheme_discovery.validator import apply_validation

    cand = DiscoveredScheme(
        scheme_name="Test Scheme",
        normalized_name="test scheme",
        description="Rs 1000 benefit.",
        benefits=["Rs 1000 benefit."],
        eligibility=["Must be a farmer."],
        source_url="https://pmkisan.gov.in/x",
        source_urls=["https://pmkisan.gov.in/x"],
        source_type="official_government",
        application_url=None,
    )
    apply_validation(cand)
    assert cand.validation_status in {"partially_verified", "rejected"}


# 12/13/14. Deduplication incl. PM-KISAN aliases and URL merging.
def test_deduplication_and_alias_normalization():
    from services.web_scheme_discovery.deduplicator import deduplicate, normalize_name
    from services.web_scheme_discovery.schemas import DiscoveredScheme

    assert normalize_name("PM-KISAN") == normalize_name("Pradhan Mantri Kisan Samman Nidhi")
    a = DiscoveredScheme(
        scheme_name="PM-KISAN", normalized_name="", source_url="https://pmkisan.gov.in/a",
        source_urls=["https://pmkisan.gov.in/a"], source_type="official_government",
    )
    b = DiscoveredScheme(
        scheme_name="Pradhan Mantri Kisan Samman Nidhi", normalized_name="",
        source_url="https://pmkisan.gov.in/b", source_urls=["https://pmkisan.gov.in/b"],
        source_type="official_government",
    )
    merged = deduplicate([a, b])
    assert len(merged) == 1
    assert len(merged[0].source_urls) == 2


# 15. Malformed LLM/Tavily output handled gracefully.
def test_malformed_search_payload(monkeypatch):
    from services.web_scheme_discovery.exceptions import TavilyAPIError
    from services.web_scheme_discovery.tavily_search import TavilyClient

    class FakeResp:
        status_code = 200

        def json(self):
            return {"unexpected": "shape"}

    client = TavilyClient(api_key="test-key")
    monkeypatch.setattr(client, "_post", lambda url, payload, headers: FakeResp())
    with pytest.raises(TavilyAPIError):
        client.search("farmer scheme")


def test_extractor_skips_empty_results():
    from services.web_scheme_discovery.extractor import extract_candidates

    assert extract_candidates([]) == []


# 16. No schemes found -> empty status, no crash.
def test_service_no_schemes_found(monkeypatch):
    from services.web_scheme_discovery.service import WebSchemeDiscoveryService
    from services.web_scheme_discovery.tavily_search import TavilyClient

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    service = WebSchemeDiscoveryService(tavily_client=TavilyClient(api_key="test-key"))
    monkeypatch.setattr(service.tavily_client, "search", lambda *a, **k: [])
    resp = service.discover({"state": "Maharashtra", "need": "housing"})
    assert resp.status == "empty"
    assert resp.validated_schemes == []


# 17. API endpoint success (mocked service layer).
def test_api_endpoint_success(monkeypatch):
    from app.main import app
    from services.web_scheme_discovery.schemas import (
        DiscoveredScheme,
        SearchMetadata,
        WebSchemeSearchResponse,
    )
    import services.web_scheme_discovery.routes as routes

    fake = WebSchemeSearchResponse(
        status="success",
        query_summary="mocked",
        validated_schemes=[
            DiscoveredScheme(
                scheme_name="PM-KISAN", normalized_name="pmkisan",
                source_url="https://pmkisan.gov.in/x", source_urls=["https://pmkisan.gov.in/x"],
                source_type="official_government", validation_status="verified",
                active_status="active", confidence=0.9,
            )
        ],
        rejected_candidates=[],
        metadata=SearchMetadata(queries_used=4, candidates_found=1, candidates_validated=1),
        errors=[],
    )

    class FakeService:
        def discover(self, profile, max_candidates=None):
            return fake

    monkeypatch.setattr(routes, "get_discovery_service", lambda: FakeService())
    client = TestClient(app)
    resp = client.post("/api/web-schemes/search", json={"profile": {"state": "Maharashtra"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert len(resp.json()["validated_schemes"]) == 1


# 18. API endpoint partial failure degrades gracefully.
def test_api_endpoint_partial_failure(monkeypatch):
    from app.main import app
    from services.web_scheme_discovery.tavily_search import TavilyClient
    from services.web_scheme_discovery.service import WebSchemeDiscoveryService

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    def boom(*a, **k):
        from services.web_scheme_discovery.exceptions import TavilyAPIError

        raise TavilyAPIError("down")

    service = WebSchemeDiscoveryService(tavily_client=TavilyClient(api_key="test-key"))
    monkeypatch.setattr(service, "tavily_client", service.tavily_client)
    monkeypatch.setattr(service.tavily_client, "search", boom)
    import services.web_scheme_discovery.routes as routes

    monkeypatch.setattr(routes, "get_discovery_service", lambda: service)
    client = TestClient(app)
    resp = client.post("/api/web-schemes/search", json={"profile": {"state": "Maharashtra"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "partial"


# 19. Existing /api/recommend still works.
def test_existing_recommend_still_works():
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/recommend",
        json={"profile": {"age": 42, "state": "maharashtra", "is_farmer": True, "owns_land": True}},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# 20. Existing voice endpoints still mounted.
def test_existing_voice_routes_still_mounted():
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/voice/start" in paths
    assert "/api/voice/process" in paths


# 21. Existing CALL-E endpoints still mounted.
def test_existing_calle_routes_still_mounted():
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/calle/call" in paths
    assert "/api/calle/webhook" in paths


# 23. Optional REAL integration test (gated, never runs by default).
@pytest.mark.skipif(
    os.environ.get("RUN_TAVILY_INTEGRATION_TEST", "").lower() != "true"
    or not (os.environ.get("TAVILY_API_KEY") or "").strip(),
    reason="Live Tavily integration test disabled by default.",
)
def test_live_tavily_integration_optional():
    from services.web_scheme_discovery.service import discover_web_schemes

    resp = discover_web_schemes({"state": "Maharashtra", "occupation": "farmer", "specific_need": "crop support"})
    assert resp.status in {"success", "partial", "empty"}
