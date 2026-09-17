from __future__ import annotations

import logging
import os
import re

import httpx
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("yojnasathi.stt")


def whisper_language_code(language_hint: str | None) -> str:
    """Return a Whisper-compatible ISO-639-1 language code or '' if unusable."""
    if language_hint and re.fullmatch(r"[a-z]{2}", language_hint.lower()):
        return language_hint.lower()
    return ""


_AUDIO_UPLOAD_EXTENSIONS = {
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/aac": "m4a",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/webm": "webm",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}


def whisper_upload_filename(content_type: str | None) -> str:
    """Return a upload filename whose extension matches the audio content type.

    Providers such as Groq reject audio uploads unless the multipart filename
    carries one of their recognised audio extensions, so the name must not be a
    generic ``audio.bin``.
    """
    mime = (content_type or "audio/wav").split(";")[0].strip().lower()
    ext = _AUDIO_UPLOAD_EXTENSIONS.get(mime, "wav")
    return f"audio.{ext}"


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


class WhisperSTTService(STTService):
    """OpenAI-compatible Whisper transcription service.

    Talks to the standard ``POST {base_url}/audio/transcriptions`` multipart
    contract used by OpenAI, Groq, Together AI and other OpenAI-compatible
    Whisper providers, so the exact endpoint/model are selectable through
    configuration rather than hardcoded to one vendor.

    ``whisper-large-v3-turbo`` is the default model. Providers expose it under
    their own model name (e.g. OpenAI serves large-v3-turbo under ``whisper-1``),
    so ``WHISPER_MODEL`` can be overridden per provider.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-large-v3-turbo",
        language: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r}, base_url={self.base_url!r})"

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        content_type: str | None = None,
    ) -> str:
        if not audio_bytes:
            raise RuntimeError("STT received empty audio")

        language_hint = self.language or language

        form_data = {
            "model": self.model,
            "response_format": "json",
        }
        language_code = whisper_language_code(language_hint)
        if language_code:
            form_data["language"] = language_code

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=form_data,
                    files={
                        "file": (
                            whisper_upload_filename(content_type),
                            audio_bytes,
                            content_type or "audio/wav",
                        )
                    },
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("Whisper transcription request failed (provider unreachable)") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Whisper transcription failed with HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Whisper returned an invalid JSON response") from exc

        text = (payload.get("text") or "").strip()
        if not text:
            raise RuntimeError("Whisper returned an empty transcript")
        return text


def create_stt_service() -> STTService:
    provider = (os.getenv("STT_PROVIDER") or "").strip().lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    whisper_key = (os.getenv("WHISPER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()

    if not provider:
        if gemini_key:
            provider = "gemini"
        elif whisper_key:
            provider = "whisper"
        else:
            provider = "mock"

    if provider == "mock":
        logger.info("STT provider: mock")
        return MockSTTService()

    if provider == "gemini":
        if not gemini_key:
            raise RuntimeError(
                "STT_PROVIDER=gemini but no GEMINI_API_KEY is set. "
                "Set GEMINI_API_KEY, or use STT_PROVIDER=mock for development."
            )
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        logger.info("STT provider: gemini (%s)", model)
        return GeminiSTTService(model=model)

    # 'groq' and 'whisper' share the same OpenAI-compatible /audio/transcriptions
    # contract; 'groq' defaults to Groq's endpoint and model when not overridden.
    if provider in ("whisper", "groq"):
        if not whisper_key:
            raise RuntimeError(
                f"STT_PROVIDER={provider} requires WHISPER_API_KEY (or OPENAI_API_KEY). "
                "Set the key, or use STT_PROVIDER=mock for development."
            )
        default_base_url = (
            "https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1"
        )
        model = (os.getenv("WHISPER_MODEL") or "whisper-large-v3-turbo").strip()
        logger.info("STT provider: %s (%s)", provider, model)
        return WhisperSTTService(
            api_key=whisper_key,
            base_url=(os.getenv("WHISPER_BASE_URL") or "").strip() or default_base_url,
            model=model,
            language=(os.getenv("WHISPER_LANGUAGE") or "").strip() or None,
            timeout=float(os.getenv("WHISPER_TIMEOUT", "60")),
        )

    raise RuntimeError(
        f"Unknown STT_PROVIDER '{provider}'. Choose from 'mock', 'gemini', 'groq', or 'whisper'."
    )
