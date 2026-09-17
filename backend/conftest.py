import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Test isolation: force deterministic providers BEFORE app.main is imported so
# no real Gemini / Whisper / ElevenLabs call or quota is ever hit during tests.
os.environ["GEMINI_API_KEY"] = ""
for key in (
    "WHISPER_API_KEY",
    "OPENAI_API_KEY",
    "ELEVENLABS_API_KEY",
    "STT_PROVIDER",
    "TTS_PROVIDER",
):
    os.environ.pop(key, None)
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"