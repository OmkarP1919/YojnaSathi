from __future__ import annotations

import logging
import os

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("yojnasathi.stt")


class STTService:
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        content_type: str | None = None,
    ) -> str:
        raise NotImplementedError


class MockSTTService(STTService):
    """Development adapter: accepts UTF-8 text bytes as pseudo-audio."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        content_type: str | None = None,
    ) -> str:
        try:
            text = audio_bytes.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise RuntimeError("Mock STT expects UTF-8 text bytes, not binary audio") from exc
        if not text:
            raise RuntimeError("STT returned empty text")
        return text


class GeminiSTTService(STTService):
    """Google Gemini speech-to-text via LangChain multimodal chat."""

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self._provider = ChatGoogleGenerativeAI(model=model, temperature=0, max_retries=0)

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        content_type: str | None = None,
    ) -> str:
        if not audio_bytes:
            raise RuntimeError("STT received empty audio")

        mime = content_type or "audio/wav"

        prompt = "Transcribe the following speech verbatim. Output only the raw transcript text with no extra commentary."
        if language:
            prompt += f" The speaker is speaking {language}."

        response = await self._provider.ainvoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {
                            "type": "media",
                            "mime_type": mime,
                            "data": audio_bytes,
                        },
                    ]
                )
            ]
        )

        text = (response.content or "").strip()
        if not text:
            raise RuntimeError("Gemini STT returned empty transcript")
        return text


def create_stt_service() -> STTService:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if api_key:
        logger.info("STT provider: gemini (%s)", model)
        return GeminiSTTService(model=model)
    provider = os.getenv("STT_PROVIDER", "mock").strip().lower()
    if provider == "mock":
        logger.info("STT provider: mock")
        return MockSTTService()
    raise RuntimeError(
        "No GEMINI_API_KEY set and STT_PROVIDER is not 'mock'. "
        "Set GEMINI_API_KEY for real speech-to-text."
    )
