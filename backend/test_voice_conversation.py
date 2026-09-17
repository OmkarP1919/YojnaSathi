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