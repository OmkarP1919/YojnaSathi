import asyncio
import os
import sys

os.environ["GEMINI_API_KEY"] = ""
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from app.main import app, MAX_AUDIO_BYTES


def wav_stub(text: str) -> bytes:
    return text.encode("utf-8")


def to_audio_files(data: bytes, content_type: str = "audio/wav"):
    return {"audio": ("utterance.wav", data, content_type)}


def main() -> None:
    client = TestClient(app)

    print("=== 1. MULTIPART ROUND-TRIP (audio -> STT -> agent -> TTS) ===")
    resp = client.post(
        "/api/voice/process/audio",
        files=to_audio_files(wav_stub("मला शेतीसाठी योजना पाहिजे")),
        data={"session_id": "audio-smoke-mr", "language": "mr"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == "मला शेतीसाठी योजना पाहिजे"
    assert body["language"] == "mr"
    assert body["response_text"]
    assert body["next_action"] in ("ask_question", "completed")
    assert "audio_b64" in body
    assert body["audio_content_type"] == "text/plain; charset=utf-8"
    assert body["tts_error"] is None
    print("OK round-trip:", body["language"], body["next_action"], "audio_b64_len:", len(body["audio_b64"]))

    print("=== 2. MULTI-TURN TO COMPLETION WITH SCHEMES ===")
    sid = "audio-smoke-farmer"
    client.post("/api/voice/process/audio", files=to_audio_files(wav_stub("I am a farmer from Maharashtra")), data={"session_id": sid, "language": "en"})
    client.post("/api/voice/process/audio", files=to_audio_files(wav_stub("Maharashtra")), data={"session_id": sid, "language": "en"})
    final = client.post("/api/voice/process/audio", files=to_audio_files(wav_stub("yes")), data={"session_id": sid, "language": "en"})
    assert final.status_code == 200, final.text
    fb = final.json()
    assert fb["next_action"] == "completed"
    assert len(fb["schemes"]) > 0, "Expected schemes on completed flow"
    assert fb["schemes"][0]["name"]
    print("OK completion with schemes:", [s["id"] for s in fb["schemes"]], "audio_b64_len:", len(fb["audio_b64"]))

    print("=== 3. VALIDATION: empty upload -> 400 ===")
    r = client.post("/api/voice/process/audio", files=to_audio_files(b""), data={"session_id": "x", "language": "en"})
    assert r.status_code == 400, r.status_code
    print("OK 400 empty")

    print("=== 4. VALIDATION: oversized upload -> 413 ===")
    r = client.post("/api/voice/process/audio", files=to_audio_files(b"x" * (MAX_AUDIO_BYTES + 1)), data={"session_id": "x", "language": "en"})
    assert r.status_code == 413, r.status_code
    print("OK 413 oversized")

    print("=== 5. VALIDATION: unsupported content type -> 415 ===")
    r = client.post(
        "/api/voice/process/audio",
        files={"audio": ("clip.webm", wav_stub("hi"), "video/webm")},
        data={"session_id": "x", "language": "en"},
    )
    assert r.status_code == 415, r.status_code
    print("OK 415 webm rejected")

    print("=== 6. VALIDATION: untranscribable binary -> 422 ===")
    r = client.post("/api/voice/process/audio", files=to_audio_files(bytes([0x00, 0xFF, 0x80, 0x7F])), data={"session_id": "x", "language": "en"})
    assert r.status_code == 422, r.status_code
    print("OK 422 STT failure")

    print("=== 7. EXISTING /api/voice/process STILL WORKS ===")
    r = client.post("/api/voice/process", json={"session_id": "json-smoke", "message": "मला शेतीसाठी योजना पाहिजे", "language": "mr"})
    assert r.status_code == 200, r.text
    assert r.json()["language"] == "mr"
    print("OK text endpoint")

    print("=== 8. EXISTING /api/voice/reset STILL WORKS ===")
    r = client.post("/api/voice/reset", json={"session_id": "audio-smoke-farmer"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    print("OK reset endpoint")

    print("\nALL ENDPOINT SMOKE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()