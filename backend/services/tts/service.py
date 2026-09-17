from __future__ import annotations

import logging
import os

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("yojnasathi.tts")


class TTSService:
    content_type = "application/octet-stream"
    is_mock = False

    async def synthesize(self, text: str, language: str) -> bytes:
        raise NotImplementedError


class MockTTSService(TTSService):
    """Development adapter: returns UTF-8 text bytes as a predictable audio stub."""

    content_type = "text/plain; charset=utf-8"
    is_mock = True

    async def synthesize(self, text: str, language: str) -> bytes:
        if not text.strip():
            raise RuntimeError("TTS cannot synthesize empty text")
        return text.encode("utf-8")


class GeminiTTSService(TTSService):
    """Google Gemini text-to-speech via LangChain's gemini TTS models."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash-preview-tts",
        voice: str = "Kore",
    ) -> None:
        self._provider = ChatGoogleGenerativeAI(model=model, voice_name=voice)
        self.is_mock = False
        self.content_type = "audio/wav"

    async def synthesize(self, text: str, language: str) -> bytes:
        if not text.strip():
            raise RuntimeError("TTS cannot synthesize empty text")

        response = await self._provider.ainvoke(text)

        audio_bytes = (response.additional_kwargs or {}).get("audio")
        if not audio_bytes:
            raise RuntimeError("Gemini TTS returned no audio data")
        return audio_bytes


class ElevenLabsTTSService(TTSService):
    """ElevenLabs text-to-speech via the official HTTP API.

    Uses ``POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`` with
    the ``xi-api-key`` header. Returns MP3 bytes by default (``audio/mpeg``),
    which the browser audio pipeline decodes natively.

    Voice selection is language-aware: an explicit per-language voice can be
    configured for ``en``/``hi``/``mr`` and falls back to the default voice.
    """

    content_type = "audio/mpeg"
    is_mock = False

    def __init__(
        self,
        api_key: str,
        default_voice: str,
        voices: dict[str, str] | None = None,
        model: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.7,
        base_url: str = "https://api.elevenlabs.io",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.default_voice = default_voice
        self.voices = voices or {}
        self.model = model
        self.stability = stability
        self.similarity_boost = similarity_boost
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r}, default_voice={self.default_voice!r})"

    def _voice_for(self, language: str) -> str:
        lang = (language or "en").lower()
        return self.voices.get(lang) or self.default_voice

    async def synthesize(self, text: str, language: str) -> bytes:
        if not text.strip():
            raise RuntimeError("TTS cannot synthesize empty text")

        voice_id = self._voice_for(language)
        url = f"{self.base_url}/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise RuntimeError("ElevenLabs TTS request failed (provider unreachable)") from exc

        if response.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS failed with HTTP {response.status_code}")

        if not response.content:
            raise RuntimeError("ElevenLabs TTS returned empty audio")
        return response.content


def create_tts_service() -> TTSService:
    provider = (os.getenv("TTS_PROVIDER") or "").strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    if not provider:
        if elevenlabs_key:
            provider = "elevenlabs"
        elif gemini_key:
            provider = "gemini"
        else:
            provider = "mock"

    if provider == "mock":
        logger.info("TTS provider: mock")
        return MockTTSService()

    if provider == "gemini":
        if not gemini_key:
            raise RuntimeError(
                "TTS_PROVIDER=gemini but no GEMINI_API_KEY is set. "
                "Set GEMINI_API_KEY, or use TTS_PROVIDER=mock for development."
            )
        model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
        voice = os.getenv("GEMINI_TTS_VOICE", "Kore").strip()
        logger.info("TTS provider: gemini (%s, voice=%s)", model, voice)
        return GeminiTTSService(model=model, voice=voice)

    if provider == "elevenlabs":
        if not elevenlabs_key:
            raise RuntimeError(
                "TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY. "
                "Set the key, or use TTS_PROVIDER=mock for development."
            )
        default_voice = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip()
        if not default_voice:
            raise RuntimeError(
                "TTS_PROVIDER=elevenlabs requires ELEVENLABS_VOICE_ID "
                "(an ElevenLabs voice id; optionally set ELEVENLABS_VOICE_EN/HI/MR "
                "for language-specific voices)."
            )
        logger.info("TTS provider: elevenlabs (model=%s)", os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"))
        voices = {
            code: voice.strip()
            for code, voice in (
                ("en", os.getenv("ELEVENLABS_VOICE_EN") or ""),
                ("hi", os.getenv("ELEVENLABS_VOICE_HI") or ""),
                ("mr", os.getenv("ELEVENLABS_VOICE_MR") or ""),
            )
            if voice.strip()
        }
        return ElevenLabsTTSService(
            api_key=elevenlabs_key,
            default_voice=default_voice,
            voices=voices,
            model=os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip(),
            stability=float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
            similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY", "0.7")),
            timeout=float(os.getenv("ELEVENLABS_TIMEOUT", "60")),
        )

    raise RuntimeError(
        f"Unknown TTS_PROVIDER '{provider}'. Choose from 'mock', 'gemini', or 'elevenlabs'."
    )