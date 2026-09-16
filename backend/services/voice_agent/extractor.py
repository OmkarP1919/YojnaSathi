from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from services.voice_agent.graph_compat import detect_language_fallback

logger = logging.getLogger("yojnasathi.voice_agent")


class ExtractedUserInfo(BaseModel):
    """Allowlisted user facts extracted from one conversation turn."""

    model_config = ConfigDict(extra="ignore")

    intent: Optional[str] = None
    occupation: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=120)
    gender: Optional[str] = None
    category: Optional[str] = None
    annual_income: Optional[float] = Field(default=None, ge=0)
    is_student: Optional[bool] = None
    is_farmer: Optional[bool] = None
    is_business: Optional[bool] = None
    owns_land: Optional[bool] = None
    language: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: str = "llm"


# Canonical values are intentionally small. The model handles language and phrasing.
STATE_NAMES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu and kashmir", "ladakh", "puducherry", "chandigarh",
}
STATE_ALIASES = {
    "mh": "maharashtra",
    "महाराष्ट्र": "maharashtra",
    "महाराष्ट्रात": "maharashtra",
    "महाराष्ट्रातील": "maharashtra",
    "maharashtraat": "maharashtra",
    "maharashtratil": "maharashtra",
    "नाशिक": "maharashtra",
    "nashik": "maharashtra",
    "mp": "madhya pradesh",
    "मध्य प्रदेश": "madhya pradesh",
}
OCCUPATION_VALUES = {
    "farmer", "student", "small business", "street vendor", "self-employed",
    "laborer", "worker", "unemployed", "homemaker",
}
OCCUPATION_ALIASES = {
    "किसान": "farmer", "किसानों": "farmer", "शेतकरी": "farmer", "शेतकऱ": "farmer", "शेती": "farmer",
    "agriculture": "farmer", "farming": "farmer", "student": "student",
    "विद्यार्थी": "student", "छात्र": "student", "शिक्षार्थी": "student",
    "व्यवसाय": "small business", "business": "small business", "दुकान": "small business",
    "vendor": "street vendor", "विक्रेता": "street vendor", "laborer": "laborer",
    "worker": "worker", "unemployed": "unemployed", "गृहिणी": "homemaker",
}
INTENT_VALUES = {
    "agriculture", "education", "health", "housing", "employment", "insurance",
    "women", "small businesses", "financial inclusion", "find_schemes",
}
INTENT_ALIASES = {
    "farming": "agriculture", "farmer": "agriculture", "किसान": "agriculture",
    "शेतकरी": "agriculture", "शेतकऱ": "agriculture", "शेती": "agriculture", "student": "education",
    "scholarship": "education", "शिष्यवृत्ती": "education", "healthcare": "health",
    "इलाज": "health", "आरोग्य": "health", "घर": "housing", "आवास": "housing",
    "job": "employment", "नोकरी": "employment", "रोजगार": "employment",
    "business": "small businesses", "व्यवसाय": "small businesses", "loan": "financial inclusion",
}
CATEGORY_VALUES = INTENT_VALUES - {"find_schemes"}


class ProfileExtractor:
    """LLM-first structured extractor with a deliberately small fallback parser."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._llm = (
            ChatGoogleGenerativeAI(
                model=self.model,
                temperature=0,
                response_mime_type="application/json",
                max_retries=0,
            )
            if self.api_key
            else None
        )

    async def extract(
        self,
        text: str,
        current_profile: Dict[str, Any],
        current_question: Optional[str],
    ) -> ExtractedUserInfo:
        if self.api_key and self._llm is not None:
            try:
                raw = await self._call_llm(text, current_profile, current_question)
                validated = ExtractedUserInfo.model_validate(raw)
                normalized = normalize_extraction(validated)
                self._log(text, validated, normalized)
                return normalized
            except Exception as exc:  # Provider failures must not stop the conversation.
                logger.warning("LLM extraction unavailable; using fallback: %s", exc)

        fallback = normalize_extraction(fallback_extract(text, current_question))
        self._log(text, fallback, fallback)
        return fallback

    async def _call_llm(
        self,
        text: str,
        current_profile: Dict[str, Any],
        current_question: Optional[str],
    ) -> Dict[str, Any]:
        response = await self._llm.ainvoke(
            [
                SystemMessage(content=EXTRACTION_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "message": text,
                            "current_profile": current_profile,
                            "current_question": current_question,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        content = re.sub(r"^```json\s*|\s*```$", "", str(response.content).strip())
        return json.loads(content)

    @staticmethod
    def _log(text: str, extracted: ExtractedUserInfo, normalized: ExtractedUserInfo) -> None:
        logger.info("USER INPUT: %s", _redact(text))
        logger.info("EXTRACTED: %s", extracted.model_dump(exclude_none=True))
        logger.info("NORMALIZED: %s", normalized.model_dump(exclude_none=True))


def normalize_extraction(info: ExtractedUserInfo) -> ExtractedUserInfo:
    values = info.model_dump()
    values["source"] = info.source
    values["state"] = _normalize_state(info.state)
    values["occupation"] = _normalize_allowed(info.occupation, OCCUPATION_VALUES, OCCUPATION_ALIASES)
    values["intent"] = _normalize_allowed(info.intent, INTENT_VALUES, INTENT_ALIASES)
    values["category"] = _normalize_allowed(info.category, CATEGORY_VALUES, INTENT_ALIASES)
    if info.gender:
        gender = _clean(info.gender)
        values["gender"] = {"महिला": "female", "स्त्री": "female", "woman": "female", "women": "female"}.get(gender, gender if gender in {"male", "female", "other"} else None)
    if values.get("is_farmer") is None and values.get("occupation") == "farmer":
        values["is_farmer"] = True
    if values.get("is_student") is None and values.get("occupation") == "student":
        values["is_student"] = True
    if values.get("is_business") is None and values.get("occupation") in {"small business", "street vendor", "self-employed"}:
        values["is_business"] = True
    if values.get("intent") is None and values.get("category"):
        values["intent"] = values["category"]
    return ExtractedUserInfo.model_validate(values)


def fallback_extract(text: str, current_question: Optional[str]) -> ExtractedUserInfo:
    lowered = _clean(text)
    state = _normalize_state(lowered)
    occupation = next((value for alias, value in OCCUPATION_ALIASES.items() if _clean(alias) in lowered), None)
    if occupation is None:
        occupation = next((value for value in OCCUPATION_VALUES if value in lowered), None)
    intent = next((value for alias, value in INTENT_ALIASES.items() if _clean(alias) in lowered), None)
    age_match = re.search(r"(?:age|aged|वय|उम्र)\D{0,8}(\d{1,3})|\b(\d{1,3})\s*(?:years|वर्ष|साल)\b", lowered)
    age = int(next(group for group in age_match.groups() if group)) if age_match else None
    answer = _yes_no(lowered) if current_question == "owns_land" else None
    return ExtractedUserInfo(
        intent=intent,
        occupation=occupation,
        state=state,
        age=age,
        gender="female" if any(value in lowered for value in ("female", "woman", "महिला", "स्त्री")) else None,
        is_farmer=True if occupation == "farmer" else None,
        is_student=True if occupation == "student" else None,
        is_business=True if occupation in {"small business", "street vendor", "self-employed"} else None,
        owns_land=answer,
        language=detect_language_fallback(text),
        source="fallback",
    )


def _normalize_state(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = _clean(value)
    cleaned = re.sub(r"(?:at|in|में|मध्ये|का|की|के)$", "", cleaned).strip()
    if cleaned in STATE_ALIASES:
        return STATE_ALIASES[cleaned]
    for alias, canonical in STATE_ALIASES.items():
        if alias in cleaned:
            return canonical
    for state_name in sorted(STATE_NAMES, key=len, reverse=True):
        if state_name in cleaned:
            return state_name
    return None


def _normalize_allowed(value: Optional[str], allowed: set[str], aliases: Dict[str, str]) -> Optional[str]:
    if not value:
        return None
    cleaned = _clean(value)
    if cleaned in allowed:
        return cleaned
    return aliases.get(cleaned)


def _clean(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _yes_no(text: str) -> Optional[bool]:
    if any(word in text for word in ("yes", "हो", "हां", "हाँ", "होय")):
        return True
    if any(word in text for word in ("no", "नाही", "नहीं", "नको")):
        return False
    return None


def _redact(text: str) -> str:
    text = re.sub(
        r"(?i)\b(?:aadhaar|otp|pin|password|bank account|bank password)\b[^,.!?;\n]*",
        "[REDACTED_SENSITIVE]",
        text,
    )
    return re.sub(r"\b(?:\d[ -]?){8,}\b", "[REDACTED_NUMBER]", text)


EXTRACTION_PROMPT = """
Extract only user profile facts useful for matching government schemes.
Return one JSON object with exactly these optional fields:
intent, occupation, state, age, gender, category, annual_income, is_student,
is_farmer, is_business, owns_land, language, confidence.
Use null when a value is unknown. Understand Marathi, Hindi, English, and mixed language.
Resolve natural phrases such as Maharashtra, महाराष्ट्र, MH, महाराष्ट्रात, and Nashik to Maharashtra.
Do not infer sensitive credentials. Do not determine eligibility. Do not return scheme facts.
Use the current profile and current question to interpret short follow-up answers.
""".strip()
