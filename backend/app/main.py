import base64
import json
import logging
import os
from pathlib import Path
from typing import List, Optional
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.ai import process_chat_message
from app.locations import find_locations
from app.matching import match_schemes
from app.schemas import (
    DISCLAIMER_MAP,
    ApplicationLocation,
    ApplicationOptionsResult,
    ChatRequest,
    ChatResponse,
    DistrictDirectoryResponse,
    RecommendationRequest,
    RecommendationResponse,
    Scheme,
    SchemeListResponse,
    SingleSchemeResponse,
    StateDirectoryResponse,
    TalukaDirectoryResponse,
    VoiceProcessRequest,
    VoiceResetRequest,
    VoiceStartRequest,
)
from services.calle.routes import router as calle_router
from services.stt.service import STTService, create_stt_service
from services.tts.service import TTSService, create_tts_service
from services.voice_agent.agent import VoiceAgent

# Load environment variables. backend/.env takes precedence; the repo-root .env
# is loaded as a non-overriding fallback so existing root-level secrets (such as
# GEMINI_API_KEY) keep working when backend/.env only overrides voice settings.
load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger("yojnasathi.api")

app = FastAPI(
    title="YojnaSathi API",
    description="Backend API for YojnaSathi - simplifying government scheme access for citizens.",
    version="0.4.0",
)

# Enable CORS for frontend development and production. Vite runs with host: true,
# so the SPA is reachable on loopback AND on the machine's private LAN address;
# accept those origins (any dev port) instead of hardcoding only :5173.
# Production origins (such as Render frontend URL) can be specified via ALLOWED_ORIGINS.
# No "*" wildcard is used so allow_credentials stays safe.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

env_allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
if env_allowed_origins:
    for origin in env_allowed_origins.split(","):
        cleaned = origin.strip()
        if cleaned and cleaned not in origins:
            origins.append(cleaned)
DEV_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")(?::\d{1,5})?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=DEV_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phone channel (CALL-E) - outbound scheme-discovery calls. Routed under /api/calle.
app.include_router(calle_router)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"

# Maximum accepted audio upload size (5MB). 16-bit mono 16kHz WAV is ~32KB/s,
# so this comfortably covers a ~2.5 minute utterance and guards against abuse.
MAX_AUDIO_BYTES = 5 * 1024 * 1024

# Audio content types handled by the STT layer. Gemini supports a subset of
# common audio containers; we reject anything we will hand straight through.
SUPPORTED_AUDIO_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp3",
    "audio/mpeg",
    "audio/aac",
    "audio/aiff",
    "audio/x-aiff",
    "audio/ogg",
    "audio/flac",
}


def _normalize_audio_content_type(raw: Optional[str]) -> Optional[str]:
    """Map a client-provided audio content-type to a normalized MIME value."""
    return (raw or "").strip().lower().split(";")[0].strip() or None


def load_schemes_data() -> List[Scheme]:
    """Load and parse schemes data from schemes.json."""
    if not DATA_PATH.exists():
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw_schemes = json.load(f)
    return [Scheme(**item) for item in raw_schemes]


@app.get("/api/health")
def health_check():
    """Service health check endpoint."""
    return {
        "status": "ok",
        "service": "YojnaSathi",
    }


@app.get("/api/schemes", response_model=SchemeListResponse)
def get_schemes(
    category: Optional[str] = Query(None, description="Filter by scheme category (e.g., agriculture, health)"),
    state: Optional[str] = Query(None, description="Filter by state (e.g., all-india, maharashtra)"),
    target_group: Optional[str] = Query(None, description="Filter by target group (e.g., women, farmers)"),
):
    """Retrieve all schemes with optional case-insensitive filtering."""
    schemes = load_schemes_data()

    if category:
        cat_filter = category.strip().lower()
        schemes = [s for s in schemes if s.category.lower() == cat_filter]

    if state:
        state_filter = state.strip().lower()
        schemes = [s for s in schemes if s.state.lower() == state_filter]

    if target_group:
        tg_filter = target_group.strip().lower()
        schemes = [
            s
            for s in schemes
            if any(tg_filter == tg.lower() or tg_filter in tg.lower() for tg in s.target_groups)
        ]

    return SchemeListResponse(
        success=True,
        count=len(schemes),
        schemes=schemes,
    )


@app.get("/api/schemes/{scheme_id}", response_model=SingleSchemeResponse)
def get_scheme_by_id(
    scheme_id: str,
    state: Optional[str] = Query(None, description="Optional state to resolve application locations"),
    district: Optional[str] = Query(None, description="Optional district to resolve application locations"),
    taluka: Optional[str] = Query(None, description="Optional taluka to resolve application locations"),
):
    """Retrieve a single scheme by its unique identifier with optional location resolution."""
    schemes = load_schemes_data()
    target_id = scheme_id.strip().lower()

    for s in schemes:
        if s.id.lower() == target_id:
            if state:
                locs = find_locations(
                    scheme_id=s.id,
                    state=state,
                    district=district,
                    taluka=taluka,
                )
                if locs:
                    guidance = s.application_guidance.model_copy(deep=True)
                    guidance.offline_application.locations = locs
                    guidance.offline_application.available = True
                    s.custom_application_guidance = guidance
            return SingleSchemeResponse(
                success=True,
                scheme=s,
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scheme with id '{scheme_id}' not found",
    )


@app.get("/api/locations/states", response_model=StateDirectoryResponse)
def get_location_states_endpoint():
    """
    Retrieve the authoritative list of Indian States and Union Territories.
    """
    from app.government_locations import get_location_directory
    directory = get_location_directory()
    return directory.get_states()


@app.get("/api/locations/districts", response_model=DistrictDirectoryResponse)
def get_location_districts_endpoint(
    state: str = Query(..., description="State name (e.g. maharashtra)"),
):
    """
    Dynamically discover and verify official districts for a state from official government sources.
    """
    from app.government_locations import get_location_directory
    directory = get_location_directory()
    return directory.get_districts(state=state)


@app.get("/api/locations/talukas", response_model=TalukaDirectoryResponse)
def get_location_talukas_endpoint(
    state: Optional[str] = Query(None, description="State name (e.g. maharashtra)"),
    district: str = Query(..., description="District name (e.g. nashik)"),
):
    """
    Dynamically discover and verify official talukas/tehsils for a district from official district portals.
    """
    from app.government_locations import get_location_directory
    directory = get_location_directory()
    return directory.get_talukas(state=state or "", district=district)


@app.get("/api/locations", response_model=List[ApplicationLocation])
def get_locations_endpoint(
    scheme_id: Optional[str] = Query(None, description="Filter by scheme ID"),
    state: str = Query(..., description="State (e.g., maharashtra)"),
    district: Optional[str] = Query(None, description="District (e.g., nashik)"),
    taluka: Optional[str] = Query(None, description="Taluka (e.g., dindori)"),
):
    """Retrieve verified physical application centers/offices for a jurisdiction."""
    if scheme_id:
        return find_locations(scheme_id=scheme_id, state=state, district=district, taluka=taluka)
    from app.locations import load_locations_data
    pool = load_locations_data()
    s_state = state.strip().lower()
    s_dist = district.strip().lower() if district and district.strip() else None
    s_tal = taluka.strip().lower() if taluka and taluka.strip() else None

    matches = []
    for loc in pool:
        if loc.state.strip().lower() != s_state:
            continue
        if s_dist and loc.district and loc.district.strip().lower() != s_dist:
            continue
        if s_tal and loc.taluka and loc.taluka.strip().lower() != s_tal:
            continue
        matches.append(loc)
    return matches


@app.get("/api/application-options", response_model=ApplicationOptionsResult)
def get_application_options_endpoint(
    scheme_id: str = Query(..., description="Target scheme ID"),
    state: str = Query(..., description="State (e.g. maharashtra)"),
    district: Optional[str] = Query(None, description="District (e.g. nashik)"),
    taluka: Optional[str] = Query(None, description="Taluka (e.g. dindori)"),
):
    """
    Retrieve structured application options (both online and physical application centers)
    for a given scheme and location, searching official sources with verified catalog fallback.
    """
    from app.location_search import find_application_options
    return find_application_options(
        scheme_id=scheme_id,
        state=state,
        district=district,
        taluka=taluka,
    )


@app.post("/api/recommend", response_model=RecommendationResponse)
def recommend_schemes(request: RecommendationRequest):
    """
    Recommend potentially relevant schemes for a citizen profile using deterministic matching.
    Does not make legal eligibility determinations.
    """
    schemes = load_schemes_data()
    results = match_schemes(request.profile, schemes, category=request.category)

    # Attach location-aware physical application centers if citizen state is provided
    if request.profile.state:
        for result in results:
            locs = find_locations(
                scheme_id=result.scheme.id,
                state=request.profile.state,
                district=request.profile.district,
                taluka=request.profile.taluka,
            )
            result.locations = locs
            if locs:
                guidance = result.scheme.application_guidance.model_copy(deep=True)
                guidance.offline_application.locations = locs
                guidance.offline_application.available = True
                result.scheme.custom_application_guidance = guidance

    from app.location_requirements import evaluate_location_requirement
    loc_requirement = evaluate_location_requirement(request.profile, results)

    return RecommendationResponse(
        success=True,
        count=len(results),
        disclaimer=dict(DISCLAIMER_MAP),
        results=results,
        location_requirement=loc_requirement,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Process natural-language citizen chat messages using LangChain + Gemini,
    extracts/updates citizen profile, matches candidate schemes deterministically,
    and returns a citizen-friendly explanation.
    """
    schemes = load_schemes_data()
    return process_chat_message(
        message=request.message,
        profile=request.profile,
        schemes=schemes,
    )


_voice_agent: Optional[VoiceAgent] = None
_stt_service: Optional[STTService] = None
_tts_service: Optional[TTSService] = None


def get_voice_agent() -> VoiceAgent:
    """Return singleton instance of VoiceAgent loaded with curated schemes."""
    global _voice_agent
    if _voice_agent is None:
        schemes = load_schemes_data()
        _voice_agent = VoiceAgent(schemes=schemes)
    return _voice_agent


def get_stt_service() -> STTService:
    """Return the shared STT service used by the voice pipeline."""
    global _stt_service
    if _stt_service is None:
        _stt_service = create_stt_service()
    return _stt_service


def get_tts_service() -> TTSService:
    """Return the shared TTS service used by the voice pipeline."""
    global _tts_service
    if _tts_service is None:
        _tts_service = create_tts_service()
    return _tts_service


@app.post("/api/voice/process")
async def voice_process_endpoint(request: VoiceProcessRequest):
    """
    Thin transport layer for shared VoiceAgent service.
    Accepts text or transcribed voice messages and delegates to the VoiceAgent.
    """
    agent = get_voice_agent()
    return await agent.process(
        session_id=request.session_id,
        user_text=request.message,
        language_hint=request.language,
    )


@app.post("/api/voice/start")
async def voice_start_endpoint(request: VoiceStartRequest):
    """
    Agent-first conversation start.

    Creates (or uses) a session and returns the agent's localized greeting plus
    the first discovery question without any user input, alongside TTS audio so
    the frontend can display and auto-play the initial message immediately.
    """
    agent = get_voice_agent()
    session_id = (request.session_id or "").strip() or f"voice-{uuid4().hex}"
    result = await agent.start(session_id=session_id, language=request.language)

    response_text = result.get("response_text", "")
    audio_b64 = ""
    audio_content_type = "text/plain; charset=utf-8"
    tts_error = None
    if response_text.strip():
        try:
            tts = get_tts_service()
            audio_bytes = await tts.synthesize(response_text, result.get("language", "en"))
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            audio_content_type = getattr(tts, "content_type", "audio/wav")
        except Exception as exc:
            logger.warning("TTS failed for session %s: %s", session_id, exc)
            tts_error = str(exc)

    return {
        "session_id": result.get("session_id", session_id),
        "response_text": response_text,
        "language": result.get("language", "en"),
        "next_action": result.get("next_action", "ask_question"),
        "stage": result.get("stage", "greeting"),
        "should_send_sms": result.get("should_send_sms", False),
        "profile": result.get("profile", {}),
        "schemes": result.get("schemes", []),
        "audio_b64": audio_b64,
        "audio_content_type": audio_content_type,
        "tts_error": tts_error,
    }


@app.post("/api/voice/process/audio")
async def voice_process_audio_endpoint(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form(""),
):
    """
    Full voice round-trip for a single (push-to-talk) utterance.

    Flow: uploaded WAV bytes -> STT transcription -> shared VoiceAgent ->
    TTS synthesis -> base64 audio returned alongside the structured response.

    Returns the same VoiceAgent payload as the text endpoint plus `transcript`
    and `audio_b64` (WAV) so the browser can render and speak the reply.
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio upload.",
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio upload exceeds the 5MB limit.",
        )

    content_type = _normalize_audio_content_type(audio.content_type) or "audio/wav"
    if content_type not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio content type '{content_type}'. "
            "Provide WAV, MP3, AAC, AIFF, OGG, or FLAC audio.",
        )

    language_hint = (language or "").strip() or None

    try:
        stt = get_stt_service()
    except Exception as exc:
        logger.warning("STT provider configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech-to-text is not configured. Check STT environment variables.",
        ) from exc

    try:
        tts = get_tts_service()
    except Exception as exc:
        logger.warning("TTS provider configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is not configured. Check TTS environment variables.",
        ) from exc

    agent = get_voice_agent()

    try:
        transcript = await stt.transcribe(
            audio_bytes=audio_bytes,
            language=language_hint,
            content_type=content_type,
        )
    except Exception as exc:
        logger.warning("STT failed for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not transcribe the audio. Please speak clearly and try again.",
        ) from exc

    if not (transcript or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No speech was detected in the audio.",
        )

    result = await agent.process(
        session_id=session_id,
        user_text=transcript,
        language_hint=language_hint,
    )

    response_text = result.get("response_text", "")
    audio_b64 = ""
    audio_content_type = "text/plain; charset=utf-8"
    tts_error = None
    if response_text.strip():
        try:
            wav_bytes = await tts.synthesize(response_text, result.get("language", "en"))
            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            audio_content_type = getattr(tts, "content_type", "audio/wav")
        except Exception as exc:
            # TTS is optional for the conversation: preserve the text and
            # scheme results so the user can continue without voice playback.
            logger.warning("TTS failed for session %s: %s", session_id, exc)
            tts_error = str(exc)

    return {
        "session_id": result.get("session_id", session_id),
        "transcript": transcript,
        "response_text": result.get("response_text", ""),
        "language": result.get("language", "en"),
        "next_action": result.get("next_action", "ask_question"),
        "stage": result.get("stage", "discovery"),
        "should_send_sms": result.get("should_send_sms", False),
        "profile": result.get("profile", {}),
        "schemes": result.get("schemes", []),
        "audio_b64": audio_b64,
        "audio_content_type": audio_content_type,
        "tts_error": tts_error,
    }


@app.post("/api/voice/reset")
def voice_reset_endpoint(request: VoiceResetRequest):
    """Reset conversational session state for a given session ID."""
    agent = get_voice_agent()
    agent.reset(request.session_id)
    return {"success": True, "session_id": request.session_id}


