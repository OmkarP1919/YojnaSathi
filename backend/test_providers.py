"""Provider contract + configuration tests.

All tests are offline: they exercise the mock services, factories and
configuration validation and never call Gemini / Whisper / ElevenLabs.
"""

import asyncio
import os

import pytest

from app.main import MAX_AUDIO_BYTES
from services.stt.service import (
    MockSTTService,
    STTService,
    WhisperSTTService,
    create_stt_service,
)
from services.tts.service import (
    ElevenLabsTTSService,
    MockTTSService,
    TTSService,
    create_tts_service,
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# STT service contract
# ---------------------------------------------------------------------------

def test_mock_stt_returns_utf8_text():
    service = MockSTTService()
    text = run(service.transcribe("मला शेतीसाठी योजना पाहिजे".encode("utf-8"), language="mr", content_type="audio/wav"))
    assert text == "मला शेतीसाठी योजना पाहिजे"


def test_mock_stt_rejects_binary_audio():
    service = MockSTTService()
    with pytest.raises(RuntimeError):
        run(service.transcribe(bytes([0x00, 0xFF, 0x80]), language="en", content_type="audio/wav"))


def test_stt_contract_signature():
    assert STTService().transcribe is not None


# ---------------------------------------------------------------------------
# TTS service contract
# ---------------------------------------------------------------------------

def test_mock_tts_returns_utf8_bytes():
    service = MockTTSService()
    out = run(service.synthesize("नमस्कार", "hi"))
    assert out.decode("utf-8") == "नमस्कार"
    assert service.content_type == "text/plain; charset=utf-8"
    assert service.is_mock is True


def test_mock_tts_rejects_empty_text():
    service = MockTTSService()
    with pytest.raises(RuntimeError):
        run(service.synthesize("   ", "en"))


def test_tts_contract_signature():
    assert TTSService().synthesize is not None


# ---------------------------------------------------------------------------
# Factories + provider selection (mock default, no API keys)
# ---------------------------------------------------------------------------

def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert isinstance(create_stt_service(), MockSTTService)
    assert isinstance(create_tts_service(), MockTTSService)


def test_factory_mock_explicit(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert isinstance(create_stt_service(), MockSTTService)
    assert isinstance(create_tts_service(), MockTTSService)


# ---------------------------------------------------------------------------
# ElevenLabs configuration validation WITHOUT exposing the key
# ---------------------------------------------------------------------------

def test_elevenlabs_missing_key_is_clear_and_secret_safe(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_secret_should_never_leak_12345")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    with pytest.raises(RuntimeError) as excinfo:
        create_tts_service()
    message = str(excinfo.value)
    assert "ELEVENLABS_VOICE_ID" in message
    assert "sk_secret_should_never_leak_12345" not in "".join(excinfo.value.args)


def test_elevenlabs_requires_api_key(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        create_tts_service()
    assert "ELEVENLABS_API_KEY" in str(excinfo.value)


def test_elevenlabs_constructed_key_not_exposed_by_repr(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_secret_abc123")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-alpha")
    monkeypatch.delenv("ELEVENLABS_VOICE_EN", raising=False)
    service = create_tts_service()
    assert isinstance(service, ElevenLabsTTSService)
    assert service.api_key == "sk_secret_abc123"
    assert "sk_secret_abc123" not in repr(service)
    assert "sk_secret_abc123" not in str(service)


def test_elevenlabs_language_aware_voice_selection(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "default-voice")
    monkeypatch.setenv("ELEVENLABS_VOICE_EN", "english-voice")
    monkeypatch.setenv("ELEVENLABS_VOICE_HI", "hindi-voice")
    monkeypatch.setenv("ELEVENLABS_VOICE_MR", "marathi-voice")
    service = ElevenLabsTTSService(api_key="k", default_voice="default-voice", voices={"en": "english-voice", "hi": "hindi-voice", "mr": "marathi-voice"})
    assert service._voice_for("en") == "english-voice"
    assert service._voice_for("hi") == "hindi-voice"
    assert service._voice_for("mr") == "marathi-voice"
    assert service._voice_for("other") == "default-voice"


# ---------------------------------------------------------------------------
# Whisper configuration validation WITHOUT exposing the key
# ---------------------------------------------------------------------------

def test_whisper_requires_api_key(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        create_stt_service()
    assert "WHISPER_API_KEY" in str(excinfo.value)


def test_whisper_defaults(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_API_KEY", "wh_key_secret")
    monkeypatch.delenv("WHISPER_BASE_URL", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    service = create_stt_service()
    assert isinstance(service, WhisperSTTService)
    assert service.model == "whisper-large-v3-turbo"
    assert service.base_url == "https://api.openai.com/v1"
    assert "wh_key_secret" not in repr(service)


def test_whisper_accepts_openai_key_fallback(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fallback")
    service = create_stt_service()
    assert isinstance(service, WhisperSTTService)
    assert service.api_key == "sk-openai-fallback"


def test_whisper_language_hint_passes_two_letter_codes_only():
    from services.stt.service import whisper_language_code

    assert whisper_language_code("hi") == "hi"
    assert whisper_language_code("mr") == "mr"
    assert whisper_language_code("en") == "en"
    assert whisper_language_code("Hindi") == ""
    assert whisper_language_code("hi-IN") == ""
    assert whisper_language_code(None) == ""


def test_whisper_rejects_empty_audio():
    service = WhisperSTTService(api_key="k")
    with pytest.raises(RuntimeError):
        run(service.transcribe(b"", "en", "audio/wav"))


# ---------------------------------------------------------------------------
# Voice audio endpoint (mock providers, offline)
# ---------------------------------------------------------------------------

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


def _wav_stub(text: str) -> bytes:
    return text.encode("utf-8")


def _audio_files(data: bytes, content_type: str = "audio/wav"):
    return {"audio": ("utterance.wav", data, content_type)}


def test_voice_audio_round_trip():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/voice/process/audio",
        files=_audio_files(_wav_stub("मला शेतीसाठी योजना पाहिजे")),
        data={"session_id": "py-mr", "language": "mr"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == "मला शेतीसाठी योजना पाहिजे"
    assert body["language"] == "mr"
    assert body["response_text"]
    assert body["audio_content_type"] == "text/plain; charset=utf-8"
    assert body["tts_error"] is None


def test_voice_audio_round_trip_to_schemes():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    sid = "py-farmer"
    client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("I am a farmer from Maharashtra")), data={"session_id": sid, "language": "en"})
    client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("Maharashtra")), data={"session_id": sid, "language": "en"})
    final = client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("yes")), data={"session_id": sid, "language": "en"})
    assert final.status_code == 200, final.text
    body = final.json()
    assert body["next_action"] == "completed"
    assert len(body["schemes"]) > 0


def test_voice_audio_empty_upload_returns_400():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(b""), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 400


def test_voice_audio_oversized_returns_413():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(b"x" * (MAX_AUDIO_BYTES + 1)), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 413


def test_voice_audio_unsupported_content_type_returns_415():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/voice/process/audio",
        files={"audio": ("clip.webm", _wav_stub("hi"), "video/webm")},
        data={"session_id": "x", "language": "en"},
    )
    assert resp.status_code == 415


def test_voice_audio_invalid_binary_returns_422():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(bytes([0x00, 0xFF, 0x80, 0x7F])), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 422


def test_voice_audio_no_speech_returns_422(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    class SilentSTT:
        async def transcribe(self, audio_bytes, language=None, content_type=None):
            return ""

    main._stt_service = None
    monkeypatch.setattr(main, "get_stt_service", lambda: SilentSTT())

    client = TestClient(main.app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("anything")), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 422
    assert "speech" in resp.json()["detail"].lower()


def test_voice_audio_tts_failure_preserves_text_and_schemes(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    class FailingTTS:
        content_type = "text/plain"
        is_mock = True

        async def synthesize(self, text, language):
            raise RuntimeError("ElevenLabs TTS failed with HTTP 429")

    monkeypatch.setattr(main, "get_tts_service", lambda: FailingTTS())

    client = TestClient(main.app)
    # Non-idle utterance so the pipeline reaches TTS.
    resp = client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("I am a farmer from Maharashtra")), data={"session_id": "tts-fail", "language": "en"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["response_text"], "response text must be preserved when TTS fails"
    assert body["tts_error"] is not None
    assert "429" in body["tts_error"] or "TTS" in body["tts_error"]
    assert body["audio_b64"] == ""


def test_voice_audio_config_error_returns_503(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    def broken_stt():
        raise RuntimeError("TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY")

    monkeypatch.setattr(main, "get_stt_service", broken_stt)

    client = TestClient(main.app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("hi")), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 503
    assert "Speech-to-text is not configured" in resp.json()["detail"]


def test_text_endpoint_still_works():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/voice/process", json={"session_id": "py-json", "message": "मला शेतीसाठी योजना पाहिजे", "language": "mr"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["language"] == "mr"


def test_reset_endpoint_still_works():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/voice/reset", json={"session_id": "py-json"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# Provider HTTP status mapping (offline: httpx is faked, no network calls)
# ---------------------------------------------------------------------------
# These simulate Groq/ElevenLabs responses so that error paths such as an
# invalid API key (401), an unknown Whisper model or voice (404), and provider
# downtime (5xx) are exercised without consuming API quota.

class _FakeResponse:
    def __init__(self, status_code, content=b"", json_payload=None):
        self.status_code = status_code
        self.content = content
        self._json = json_payload

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _FakeAsyncClient:
    """Async-context-manager httpx.AsyncClient stand-in with a canned handler."""

    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return self._handler(*args, **kwargs)


def _fake_httpx(monkeypatch, handler):
    from services.stt import service as stt_module
    from services.tts import service as tts_module

    monkeypatch.setattr(stt_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(handler))
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(handler))


def test_whisper_groq_configuration(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setenv("WHISPER_API_KEY", "groq_secret")
    monkeypatch.setenv("WHISPER_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    service = create_stt_service()
    assert isinstance(service, WhisperSTTService)
    assert service.base_url == "https://api.groq.com/openai/v1"
    assert service.model == "whisper-large-v3-turbo"
    assert "groq_secret" not in repr(service)


def test_groq_provider_alias_defaults_to_groq_endpoint(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "groq")
    monkeypatch.setenv("WHISPER_API_KEY", "groq_secret")
    monkeypatch.delenv("WHISPER_BASE_URL", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    service = create_stt_service()
    assert isinstance(service, WhisperSTTService)
    assert service.base_url == "https://api.groq.com/openai/v1"
    assert service.model == "whisper-large-v3-turbo"
    assert "groq_secret" not in repr(service)


def test_groq_provider_requires_key(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "groq")
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        create_stt_service()
    assert "WHISPER_API_KEY" in str(excinfo.value)


def test_whisper_maps_http_401_to_error(monkeypatch):
    captured = {}

    def handler(url, headers, data, files):
        captured["auth"] = headers.get("Authorization", "")
        return _FakeResponse(401, json_payload={"error": {"message": "invalid api key"}})

    _fake_httpx(monkeypatch, handler)
    service = WhisperSTTService(api_key="bad_key")
    with pytest.raises(RuntimeError) as excinfo:
        run(service.transcribe(b"a" * 100, "en", "audio/wav"))
    assert "401" in str(excinfo.value)
    assert "bad_key" not in repr(service)


def test_whisper_maps_invalid_model_404_to_error(monkeypatch):
    _fake_httpx(monkeypatch, lambda *a, **k: _FakeResponse(404, json_payload={"error": {"message": "Model not found"}}))
    service = WhisperSTTService(api_key="k", model="not-a-real-model")
    with pytest.raises(RuntimeError) as excinfo:
        run(service.transcribe(b"a" * 100, "en", "audio/wav"))
    assert "404" in str(excinfo.value)


def test_whisper_maps_http_500_to_error(monkeypatch):
    _fake_httpx(monkeypatch, lambda *a, **k: _FakeResponse(500, json_payload={}))
    service = WhisperSTTService(api_key="k")
    with pytest.raises(RuntimeError) as excinfo:
        run(service.transcribe(b"a" * 100, "en", "audio/wav"))
    assert "500" in str(excinfo.value)


def test_whisper_sends_groq_form_and_language_hint(monkeypatch):
    captured = {}

    def handler(url, headers, data, files):
        captured["url"] = url
        captured["model"] = data["model"]
        captured["language"] = data.get("language", None)
        captured["response_format"] = data.get("response_format")
        captured["form_fields"] = set(data.keys())
        captured["form_files"] = set(files.keys())
        captured["filename"], _, captured["ctype"] = files["file"]
        captured["file_bytes"] = captured["filename"] or None
        return _FakeResponse(200, json_payload={"text": " मी शेतकरी आहे "})

    _fake_httpx(monkeypatch, handler)
    service = WhisperSTTService(
        api_key="groq_secret",
        base_url="https://api.groq.com/openai/v1",
        model="whisper-large-v3-turbo",
    )
    text = run(service.transcribe(b"\x00audio", "hi", "audio/mpeg"))
    assert text == "मी शेतकरी आहे"
    assert captured["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert captured["model"] == "whisper-large-v3-turbo"
    assert captured["language"] == "hi"
    assert captured["response_format"] == "json"
    assert captured["ctype"] == "audio/mpeg"
    assert captured["filename"] == "audio.mp3"
    assert captured["form_files"] == {"file"}
    assert captured["form_fields"] == {"model", "response_format", "language"}


def test_whisper_empty_transcript_raises(monkeypatch):
    _fake_httpx(monkeypatch, lambda *a, **k: _FakeResponse(200, json_payload={"text": "   "}))
    service = WhisperSTTService(api_key="k")
    with pytest.raises(RuntimeError):
        run(service.transcribe(b"a" * 100, "en", "audio/wav"))


def test_elevenlabs_maps_invalid_voice_404_to_error(monkeypatch):
    captured = {}

    def handler(url, headers, json):
        captured["url"] = url
        captured["voice"] = url.rsplit("/", 1)[-1]
        return _FakeResponse(404, json_payload={"detail": {"message": "Voice not found"}})

    _fake_httpx(monkeypatch, handler)
    service = ElevenLabsTTSService(api_key="k", default_voice="unknown-voice", voices={"hi": "hindi-voice"})
    with pytest.raises(RuntimeError) as excinfo:
        run(service.synthesize("नमस्कार", "hi"))
    assert "404" in str(excinfo.value)
    assert captured["voice"] == "hindi-voice"


def test_elevenlabs_returns_mp3_bytes(monkeypatch):
    captured = {}

    def handler(url, headers, json):
        captured["url"] = url
        captured["key"] = headers.get("xi-api-key")
        captured["accept"] = headers.get("Accept")
        captured["model_id"] = json.get("model_id")
        return _FakeResponse(200, content=b"\x1a\x00\x00\x00ID3 fake-mp3")

    _fake_httpx(monkeypatch, handler)
    service = ElevenLabsTTSService(
        api_key="eli_key",
        default_voice="default-voice",
        voices={"en": "english-voice"},
        model="eleven_multilingual_v2",
    )
    audio = run(service.synthesize("Hello farmer", "en"))
    assert audio == b"\x1a\x00\x00\x00ID3 fake-mp3"
    assert captured["url"].endswith("/v1/text-to-speech/english-voice")
    assert captured["key"] == "eli_key"
    assert captured["accept"] == "audio/mpeg"
    assert captured["model_id"] == "eleven_multilingual_v2"
    assert "eli_key" not in repr(service)


def test_voice_audio_tts_config_error_returns_503(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    def broken_tts():
        raise RuntimeError("TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY")

    monkeypatch.setattr(main, "get_tts_service", broken_tts)

    client = TestClient(main.app)
    resp = client.post("/api/voice/process/audio", files=_audio_files(_wav_stub("hi")), data={"session_id": "x", "language": "en"})
    assert resp.status_code == 503
    assert "Text-to-speech is not configured" in resp.json()["detail"]