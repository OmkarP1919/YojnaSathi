"""Phase 3: agent-initiated conversations + guided two-stage flow.

Covers the full lifecycle GREETING -> DISCOVERY -> MATCHING/RESULTS -> FREE_QA
while keeping the legacy /api/voice/process and /api/voice/process/audio
contracts untouched (next_action == "completed" on the results turn, etc.).

All tests are offline: conftest.py pins the STT/TTS providers to the mocks and
empties GEMINI/WHISPER/ELEVENLABS keys, so extraction uses the deterministic
fallback parser.
"""

import asyncio

import pytest

from app.main import load_schemes_data
from services.voice_agent.agent import VoiceAgent


def _run(coro):
    return asyncio.run(coro)


def _agent() -> VoiceAgent:
    return VoiceAgent(schemes=load_schemes_data())


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


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
# Agent-first session start
# ---------------------------------------------------------------------------

def test_start_endpoint_english_greeting_and_first_question():
    client = _client()
    resp = client.post("/api/voice/start", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"], "server should assign a session id"
    assert body["language"] == "en"
    assert body["stage"] == "greeting"
    assert body["next_action"] == "ask_question"
    assert "Hello" in body["response_text"]
    assert "What kind of scheme" in body["response_text"]
    assert body["schemes"] == []
    assert body["audio_b64"], "greeting should be TTS-synthesized"
    assert body["audio_content_type"].startswith("text/plain")
    assert body["tts_error"] is None


def test_start_endpoint_hindi_greeting():
    client = _client()
    resp = client.post("/api/voice/start", json={"session_id": "hi-start", "language": "hi"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "hi"
    assert body["stage"] == "greeting"
    assert "नमस्ते" in body["response_text"]
    assert "खेती" in body["response_text"]


def test_start_endpoint_marathi_greeting():
    client = _client()
    resp = client.post("/api/voice/start", json={"session_id": "mr-start", "language": "mr"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "mr"
    assert body["stage"] == "greeting"
    assert "नमस्कार" in body["response_text"]
    assert "शेती" in body["response_text"]


def test_start_defaults_to_english_for_unknown_language():
    client = _client()
    resp = client.post("/api/voice/start", json={"language": "fr"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["language"] == "en"


def test_started_session_continues_in_process_endpoint():
    client = _client()
    start = client.post("/api/voice/start", json={"session_id": "cont", "language": "en"})
    assert start.status_code == 200, start.text
    assert start.json()["session_id"] == "cont"

    resp = client.post(
        "/api/voice/process",
        json={"session_id": "cont", "message": "I am a farmer from Maharashtra", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stage"] == "discovery"
    assert body["next_action"] == "ask_question"
    assert body["profile"].get("state") == "maharashtra"
    assert "land" in body["response_text"].lower()


# ---------------------------------------------------------------------------
# Stage lifecycle through the shared agent (no HTTP)
# ---------------------------------------------------------------------------

def test_agent_start_direct_without_user_input():
    agent = _agent()
    res = _run(agent.start("direct", "mr"))
    assert res["stage"] == "greeting"
    assert res["next_action"] == "ask_question"
    assert "नमस्कार" in res["response_text"]
    assert len(res["schemes"]) == 0


def test_discovery_to_results_to_free_qa_lifecycle():
    agent = _agent()
    sid = "flow-en"

    greeting = _run(agent.start(sid, "en"))
    assert greeting["stage"] == "greeting"

    r1 = _run(agent.process(sid, "I am a farmer from Maharashtra"))
    assert r1["stage"] == "discovery"
    assert r1["next_action"] == "ask_question"
    assert "land" in r1["response_text"].lower()

    r2 = _run(agent.process(sid, "yes"))
    # Legacy contract: the results turn keeps next_action "completed" ...
    assert r2["next_action"] == "completed"
    # ... while the new stage explicitly transitions into FREE_QA.
    assert r2["stage"] == "free_qa"
    assert len(r2["schemes"]) > 0
    assert "pmfby" in [s["id"] for s in r2["schemes"]]
    assert "ask me any question" in r2["response_text"].lower()


def test_free_qa_benefit_question_answers_from_schemes():
    agent = _agent()
    sid = "qa-benefit"
    _run(agent.start(sid, "en"))
    _run(agent.process(sid, "I am a farmer from Maharashtra"))
    results = _run(agent.process(sid, "yes"))

    answer = _run(agent.process(sid, "How much money will I get?"))
    assert answer["stage"] == "free_qa"
    assert answer["next_action"] == "free_qa"
    assert results["schemes"][0]["name"] in answer["response_text"]
    assert "benefit" in answer["response_text"].lower()


def test_free_qa_application_question_includes_links():
    agent = _agent()
    sid = "qa-apply"
    _run(agent.start(sid, "en"))
    _run(agent.process(sid, "I am a farmer from Maharashtra"))
    results = _run(agent.process(sid, "yes"))

    answer = _run(agent.process(sid, "Where do I apply?"))
    assert answer["stage"] == "free_qa"
    assert results["schemes"][0]["name"] in answer["response_text"]
    assert "http" in answer["response_text"].lower()


def test_free_qa_eligibility_question():
    agent = _agent()
    sid = "qa-elig"
    _run(agent.start(sid, "en"))
    _run(agent.process(sid, "I am a farmer from Maharashtra"))
    _run(agent.process(sid, "yes"))

    answer = _run(agent.process(sid, "Am I eligible for these?"))
    assert answer["stage"] == "free_qa"
    assert "eligib" in answer["response_text"].lower()


def test_free_qa_does_not_pollute_citizen_profile():
    agent = _agent()
    sid = "qa-nopollute"
    _run(agent.start(sid, "en"))
    _run(agent.process(sid, "I am a farmer from Maharashtra"))
    results = _run(agent.process(sid, "yes"))

    answer = _run(agent.process(sid, "What documents do I need?"))
    assert answer["stage"] == "free_qa"
    assert answer["next_action"] == "free_qa"
    assert answer["profile"] == results["profile"], "FREE_QA turns must not mutate the profile"
    assert answer["profile"].get("age") is None


# ---------------------------------------------------------------------------
# Backward compatibility with the existing gesture-driven flows
# ---------------------------------------------------------------------------

def test_tenant_farmer_flow_still_returns_completed():
    agent = _agent()
    sid = "tenant-phase3"
    _run(agent.process(sid, "I am a farmer"))
    _run(agent.process(sid, "Maharashtra"))
    result = _run(agent.process(sid, "no"))

    scheme_ids = [s["id"] for s in result["schemes"]]
    assert "pmfby" in scheme_ids
    assert "pm-kisan" not in scheme_ids
    assert result["next_action"] == "completed"
    assert result["stage"] == "free_qa"


def test_legacy_audio_round_trip_to_schemes_keeps_working():
    client = _client()
    sid = "legacy-audio"

    def _wav(text):
        return {"audio": ("utterance.wav", text.encode("utf-8"), "audio/wav")}

    client.post("/api/voice/process/audio", files=_wav("I am a farmer from Maharashtra"), data={"session_id": sid, "language": "en"})
    client.post("/api/voice/process/audio", files=_wav("Maharashtra"), data={"session_id": sid, "language": "en"})
    final = client.post("/api/voice/process/audio", files=_wav("yes"), data={"session_id": sid, "language": "en"})

    assert final.status_code == 200, final.text
    body = final.json()
    assert body["next_action"] == "completed"
    assert body["stage"] == "free_qa"
    assert len(body["schemes"]) > 0
    assert body["audio_content_type"] == "text/plain; charset=utf-8"


# ---------------------------------------------------------------------------
# Phase 4: extraction fixes (deterministic fallback parser)
# ---------------------------------------------------------------------------

def _extract(text, question=None):
    from services.voice_agent.extractor import ProfileExtractor

    extractor = ProfileExtractor()
    return _run(extractor.extract(text, current_profile={}, current_question=question))


def test_extraction_age_singular_year():
    info = _extract("I am 25 year old")
    assert info.age == 25


def test_extraction_gender_male_tokens():
    info = _extract("I am a man from Pune")
    assert info.gender == "male"
    female = _extract("I am 30 year old woman from Nagpur")
    assert female.gender == "female"


def test_extraction_women_intent_aliases():
    for message in ("I need a maternity scheme", "I am pregnant and need help", "I need a cooking gas connection"):
        assert _extract(message).intent == "women", f"'{message}' should map to women"


def test_extraction_insurance_pension_aliases():
    assert _extract("I need a pension scheme").intent == "insurance"
    assert _extract("I want accident insurance").intent == "insurance"
    assert _extract("I need health insurance").intent == "insurance"


def test_extraction_financial_inclusion_aliases():
    assert _extract("I want to open a bank account").intent == "financial inclusion"
    assert _extract("I need banking services").intent == "financial inclusion"
    assert _extract("I need a loan").intent == "financial inclusion"


def test_extraction_small_business_working_capital():
    assert _extract("I need working capital").intent == "small businesses"


def test_extraction_monthly_income_converts_to_annual():
    info = _extract("I earn 15000 a month")
    assert info.annual_income == 180000
    info2 = _extract("my monthly income is 15000")
    assert info2.annual_income == 180000
    info3 = _extract("my annual income is 2 lakh")
    assert info3.annual_income == 200000


def test_extraction_unemployed_maps_to_employment():
    assert _extract("I am unemployed").intent == "employment"


# ---------------------------------------------------------------------------
# Phase 4: criteria-aware discovery planner
# ---------------------------------------------------------------------------

def test_employment_asks_age_then_area_then_matches_mgnrega():
    agent = _agent()
    sid = "p4-employment"
    _run(agent.process(sid, "I am unemployed and looking for a job"))
    r1 = _run(agent.process(sid, "Maharashtra"))
    assert "age" in r1["response_text"].lower(), f"expected age question, got: {r1['response_text']}"
    r2 = _run(agent.process(sid, "35"))
    assert "rural" in r2["response_text"].lower(), f"expected rural/urban question, got: {r2['response_text']}"
    r3 = _run(agent.process(sid, "village"))
    assert "mgnrega" in [s["id"] for s in r3["schemes"]], f"schemes: {[s['id'] for s in r3['schemes']]}"
    assert r3["next_action"] == "completed"


def test_small_business_asks_area_then_matches_svanidhi():
    agent = _agent()
    sid = "p4-business"
    _run(agent.process(sid, "I run a small business in Maharashtra"))
    r1 = _run(agent.process(sid, "urban"))
    ids = [s["id"] for s in r1["schemes"]]
    assert "pm-svanidhi" in ids, f"schemes: {ids}"
    assert r1["next_action"] == "completed"


def test_education_asks_income_then_matches_yasasvi():
    agent = _agent()
    sid = "p4-student"
    _run(agent.process(sid, "I am an OBC student from Maharashtra"))
    r1 = _run(agent.process(sid, "2 lakh"))
    ids = [s["id"] for s in r1["schemes"]]
    assert "pm-yasasvi" in ids, f"schemes: {ids}"
    assert "post-matric-sc" not in ids, "OBC must not match SC-only scheme"
    assert r1["next_action"] == "completed"


def test_women_asks_age_then_income():
    agent = _agent()
    sid = "p4-women"
    r0 = _run(agent.process(sid, "I am a woman from Maharashtra"))
    assert "age" in r0["response_text"].lower(), f"expected age question, got: {r0['response_text']}"
    r1 = _run(agent.process(sid, "30"))
    assert "earn" in r1["response_text"].lower(), f"expected income question, got: {r1['response_text']}"


def test_agriculture_never_asks_age_or_income():
    agent = _agent()
    sid = "p4-agri"
    _run(agent.process(sid, "I am a farmer"))
    r1 = _run(agent.process(sid, "Maharashtra"))
    assert "owns" in r1["response_text"].lower() or "land" in r1["response_text"].lower()
    assert "age" not in r1["response_text"].lower() and "income" not in r1["response_text"].lower()


def test_health_never_asks_age_or_income():
    agent = _agent()
    sid = "p4-health"
    _run(agent.process(sid, "I need help paying for healthcare"))
    result = _run(agent.process(sid, "Maharashtra"))
    assert result["next_action"] == "completed", f"expected results immediately, got: {result['response_text']}"
    assert "What is your age" not in result["response_text"]


def test_housing_never_asks_age_or_income():
    agent = _agent()
    sid = "p4-housing"
    _run(agent.process(sid, "I need a housing scheme"))
    r1 = _run(agent.process(sid, "Maharashtra"))
    assert "rural" in r1["response_text"].lower(), f"expected rural/urban question, got: {r1['response_text']}"
    assert "What is your age" not in r1["response_text"], f"must not ask age: {r1['response_text']}"
    assert "earn" not in r1["response_text"].lower(), f"must not ask income: {r1['response_text']}"


def test_p4_smoke_case_a_farmer_42_with_land_no_followup():
    agent = _agent()
    sid = "p4-smoke-a"
    _run(agent.start(sid, "en"))
    result = _run(agent.process(sid, "I am a 42 year old male farmer from Maharashtra who owns 3 acres of land"))
    ids = [s["id"] for s in result["schemes"]]
    assert "pm-kisan" in ids and "pmfby" in ids, f"schemes: {ids}"
    assert result["next_action"] == "completed"
    assert "What is your age" not in result["response_text"]
    assert result["profile"].get("age") == 42
    assert result["profile"].get("gender") == "male"


def test_p4_smoke_case_b_unemployed_via_http():
    client = _client()
    r1 = client.post("/api/voice/process", json={"session_id": "smoke-b", "message": "I am an unemployed person from Maharashtra", "language": "en"})
    assert r1.status_code == 200, r1.text
    assert "age" in r1.json()["response_text"].lower(), f"got: {r1.json()['response_text']}"
    r2 = client.post("/api/voice/process", json={"session_id": "smoke-b", "message": "35", "language": "en"})
    assert "rural" in r2.json()["response_text"].lower(), f"got: {r2.json()['response_text']}"
    r3 = client.post("/api/voice/process", json={"session_id": "smoke-b", "message": "village", "language": "en"})
    body = r3.json()
    assert body["next_action"] == "completed"
    assert "mgnrega" in [s["id"] for s in body["schemes"]], f"schemes: {[s['id'] for s in body['schemes']]}"


def test_p4_smoke_case_c_small_business_via_http():
    client = _client()
    r1 = client.post("/api/voice/process", json={"session_id": "smoke-c", "message": "I run a small business in Maharashtra", "language": "en"})
    assert r1.status_code == 200, r1.text
    assert "rural" in r1.json()["response_text"].lower(), f"got: {r1.json()['response_text']}"
    r2 = client.post("/api/voice/process", json={"session_id": "smoke-c", "message": "urban", "language": "en"})
    body = r2.json()
    assert body["next_action"] == "completed"
    assert "pm-svanidhi" in [s["id"] for s in body["schemes"]], f"schemes: {[s['id'] for s in body['schemes']]}"