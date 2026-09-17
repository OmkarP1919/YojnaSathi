"""PHASE 6: Application guidance ("What do I do next?") end to end.

The guidance is derived only from the verified scheme data fields already in
the catalog (application_url, required_information, department). No government
information is fabricated anywhere: offline channels stay unavailable until an
offline channel is recorded in the data. Covers:

- computed `application_guidance` on the Scheme model (serialization)
- GET /api/schemes and GET /api/schemes/{id} expose it without breaking fields
- FREE_QA apply / documents answers (online portal, help note, full docs list)
- graceful "not available" behavior when a scheme has no application data

All tests are offline: conftest.py pins STT/TTS to mocks and the deterministic
fallback extractor is used.
"""

import asyncio
import json

import pytest


def _run(coro):
    return asyncio.run(coro)


def _schemes_data():
    from app.main import load_schemes_data

    return load_schemes_data()


def _scheme_by_id(schemes, scheme_id):
    return next((s for s in schemes if s.id == scheme_id), None)


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _agent(schemes=None):
    from services.voice_agent.agent import VoiceAgent

    return VoiceAgent(schemes=schemes if schemes is not None else _schemes_data())


def _custom_scheme():
    """A scheme that still matches the farmer flow (cloned from PMFBY) but has
    no application_url / required_information, so the guidance must degrade."""
    schemes = _schemes_data()
    base = next(s for s in schemes if s.id == "pmfby")
    return base.model_copy(
        update={
            "id": "custom-app",
            "name": "Custom Apply Scheme",
            "application_url": "",
            "required_information": {},
            "source_url": "",
        }
    )


def _reach_free_qa(agent, sid, messages, max_attempts=8):
    """Drive a discovery conversation until schemes are returned (FREE_QA)."""
    from collections import deque

    queue = deque(messages)
    result = None
    for _ in range(max_attempts):
        text = queue.popleft() if queue else "yes"
        result = _run(agent.process(sid, text))
        if result.get("schemes"):
            return result
    return result


@pytest.fixture(autouse=True)
def _reset_service_singletons():
    import app.main as main

    main._stt_service = None
    main._tts_service = None
    main._voice_agent = None
    yield
    main._stt_service = None
    main._tts_service = None
    main._voice_agent = None


# ---------------------------------------------------------------------------
# Schema: computed application_guidance
# ---------------------------------------------------------------------------

def test_application_guidance_derived_from_verified_fields():
    scheme = _scheme_by_id(_schemes_data(), "pm-kisan")
    guidance = scheme.application_guidance
    assert guidance.online_application.available is True
    assert guidance.online_application.portal_url == scheme.application_url == "https://pmkisan.gov.in/"
    assert guidance.online_application.portal_name == "pmkisan.gov.in"
    assert guidance.documents_required == scheme.required_information
    assert guidance.offline_application.available is False
    assert guidance.offline_application.authorized_channel is None

    dumped = scheme.model_dump()
    assert dumped["application_guidance"]["online_application"]["portal_url"] == scheme.application_url
    # JSON-serializable for API responses.
    json.loads(scheme.model_dump_json())


def test_application_guidance_defaults_gracefully_without_data():
    scheme = _custom_scheme()
    guidance = scheme.application_guidance
    assert guidance.online_application.available is False
    assert guidance.online_application.portal_url is None
    assert guidance.online_application.portal_name is None
    assert guidance.documents_required is None
    assert guidance.offline_application.available is False
    dumped = scheme.model_dump()
    assert dumped["application_guidance"]["online_application"]["available"] is False
    json.loads(scheme.model_dump_json())


# ---------------------------------------------------------------------------
# API endpoints expose guidance without breaking existing fields
# ---------------------------------------------------------------------------

def test_schemes_list_endpoint_includes_guidance():
    from app.schemas import SchemeListResponse

    client = _client()
    resp = client.get("/api/schemes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == len(_schemes_data())

    parsed = SchemeListResponse.model_validate(body)
    for scheme in parsed.schemes:
        assert "application_guidance" in scheme.model_dump()
        assert bool(scheme.application_url) == scheme.application_guidance.online_application.available
        assert scheme.application_guidance.online_application.portal_url == scheme.application_url
        if scheme.application_url:
            assert scheme.application_guidance.documents_required == scheme.required_information


def test_scheme_detail_endpoint_includes_guidance():
    from app.schemas import SingleSchemeResponse

    client = _client()
    resp = client.get("/api/schemes/pm-kisan")
    assert resp.status_code == 200, resp.text

    parsed = SingleSchemeResponse.model_validate(resp.json())
    scheme = parsed.scheme
    assert scheme.application_guidance.online_application.portal_url == "https://pmkisan.gov.in/"
    assert scheme.application_guidance.online_application.portal_name == "pmkisan.gov.in"
    # Existing fields remain intact.
    assert scheme.application_url == "https://pmkisan.gov.in/"
    assert scheme.id == "pm-kisan"


# ---------------------------------------------------------------------------
# FREE_QA: apply / documents answers from the verified scheme data
# ---------------------------------------------------------------------------

def test_free_qa_how_do_i_apply_answers_online_portal_and_help():
    agent = _agent()
    sid = "p6-apply-how"
    _run(agent.start(sid, "en"))
    results = _reach_free_qa(agent, sid, ["I am a farmer from Maharashtra"])

    answer = _run(agent.process(sid, "How do I apply?"))
    assert answer["stage"] == "free_qa"
    assert "Apply online: https://pmfby.gov.in/" in answer["response_text"]
    assert "For help, contact:" in answer["response_text"]
    assert "Apply online: https://pmkisan.gov.in/" in answer["response_text"]

    # Voice payload exposes the same guidance for the voice panel cards.
    assert results["schemes"][0]["application_guidance"]["online_application"]["portal_url"]


def test_free_qa_where_and_can_i_apply_online():
    agent = _agent()
    sid = "p6-apply-where"
    _run(agent.start(sid, "en"))
    _reach_free_qa(agent, sid, ["I am a farmer from Maharashtra"])

    for question in ("Where do I apply?", "Can I apply online?",
                     "What is the application process?", "मैं आवेदन कहां करूं?"):
        answer = _run(agent.process(sid, question))
        assert answer["stage"] == "free_qa", f"{question!r} -> {answer['response_text']}"
        assert "pmfby.gov.in" in answer["response_text"], f"{question!r} -> {answer['response_text']}"


def test_free_qa_documents_lists_all_documents():
    agent = _agent()
    sid = "p6-docs"
    _run(agent.start(sid, "en"))
    _reach_free_qa(agent, sid, ["I am a farmer from Maharashtra"])

    answer = _run(agent.process(sid, "What documents do I need?"))
    assert answer["stage"] == "free_qa"
    text = answer["response_text"]
    assert "Aadhaar number" in text
    assert "Land records (Khasra/Khatauni number)" in text
    assert "Sowing certificate or declaration" in text


def test_free_qa_apply_without_application_data_says_not_available():
    custom = _custom_scheme()
    agent = _agent(schemes=[custom])
    sid = "p6-apply-missing"
    _run(agent.start(sid, "en"))
    results = _reach_free_qa(agent, sid, ["I am a farmer from Maharashtra"])
    assert [s["id"] for s in results["schemes"]] == ["custom-app"]

    department = custom.department["en"]
    answer = _run(agent.process(sid, "Where do I apply?"))
    assert answer["stage"] == "free_qa"
    assert "not available in the current scheme data" in answer["response_text"]
    assert f"For help, contact: {department}" in answer["response_text"]
    assert "http" not in answer["response_text"].lower()


def test_free_qa_documents_gracefully_reports_missing():
    agent = _agent(schemes=[_custom_scheme()])
    sid = "p6-docs-missing"
    _run(agent.start(sid, "en"))
    _reach_free_qa(agent, sid, ["I am a farmer from Maharashtra"])

    answer = _run(agent.process(sid, "What documents do I need?"))
    assert answer["stage"] == "free_qa"
    assert "not available in the current scheme data" in answer["response_text"]