from __future__ import annotations

import logging
import os

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


def create_tts_service() -> TTSService:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
    voice = os.getenv("GEMINI_TTS_VOICE", "Kore").strip()
    if api_key:
        logger.info("TTS provider: gemini (%s, voice=%s)", model, voice)
        return GeminiTTSService(model=model, voice=voice)
    provider = os.getenv("TTS_PROVIDER", "mock").strip().lower()
    if provider == "mock":
        logger.info("TTS provider: mock")
        return MockTTSService()
    raise RuntimeError(
        "No GEMINI_API_KEY set and TTS_PROVIDER is not 'mock'. "
        "Set GEMINI_API_KEY for real text-to-speech."
    )