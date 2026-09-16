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
    owns_house: Optional[bool] = None
    social_category: Optional[str] = None
    rural_or_urban: Optional[str] = None
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
    "शेतकरी": "agriculture", "शेतकऱ": "agriculture", "शेती": "agriculture",
    "student": "education", "scholarship": "education", "छात्रवृत्ति": "education",
    "शिष्यवृत्ती": "education", "पढ़ाई": "education", "शिक्षा": "education", "शिक्षण": "education",
    "healthcare": "health", "इलाज": "health", "आरोग्य": "health",
    "घर": "housing", "आवास": "housing", "मकान": "housing", "housing": "housing",
    "job": "employment", "नोकरी": "employment", "रोजगार": "employment",
    "business": "small businesses", "व्यवसाय": "small businesses", "loan": "financial inclusion",
}
CATEGORY_VALUES = INTENT_VALUES - {"find_schemes"}

SOCIAL_CATEGORY_VALUES = {"general", "sc", "st", "obc", "ebc", "dnt"}
SOCIAL_CATEGORY_ALIASES = {
    "sc": "sc", "scheduled caste": "sc", "अनुसूचित जाति": "sc", "दलित": "sc",
    "st": "st", "scheduled tribe": "st", "अनुसूचित जनजाति": "st", "आदिवासी": "st",
    "obc": "obc", "other backward class": "obc", "अन्य पिछड़ा वर्ग": "obc", "इमाव": "obc",
    "ebc": "ebc", "economically backward class": "ebc", "आर्थिक रूप से पिछड़ा": "ebc", "ईबीसी": "ebc",
    "dnt": "dnt", "de-notified": "dnt", "nomadic": "dnt", "विमुक्त": "dnt", "भटक्या": "dnt", "nt": "dnt", "डीएनटी": "dnt",
    "general": "general", "open": "general", "सामान्य": "general", "खुला": "general",
}

RURAL_URBAN_VALUES = {"rural", "urban"}
RURAL_URBAN_ALIASES = {
    "rural": "rural", "village": "rural", "गांव": "rural", "गावात": "rural", "ग्रामीण": "rural", "खेडेगाव": "rural",
    "urban": "urban", "city": "urban", "town": "urban", "शहर": "urban", "शहरात": "urban", "शहरी": "urban",
}


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
    values["social_category"] = _normalize_allowed(info.social_category, SOCIAL_CATEGORY_VALUES, SOCIAL_CATEGORY_ALIASES)
    values["rural_or_urban"] = _normalize_allowed(info.rural_or_urban, RURAL_URBAN_VALUES, RURAL_URBAN_ALIASES)
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
    def _has_alias(alias_str: str, source_text: str) -> bool:
        clean_a = _clean(alias_str)
        if len(clean_a) <= 3 and clean_a.isascii():
            return bool(re.search(r"\b" + re.escape(clean_a) + r"\b", source_text))
        return clean_a in source_text

    occupation = next((value for alias, value in OCCUPATION_ALIASES.items() if _has_alias(alias, lowered)), None)
    if occupation is None:
        occupation = next((value for value in OCCUPATION_VALUES if value in lowered), None)
    intent = next((value for alias, value in INTENT_ALIASES.items() if _has_alias(alias, lowered)), None)

    # Social category with word boundary protection (e.g. avoid 'sc' matching 'scholarship' or 'school')
    social_cat = next((value for alias, value in SOCIAL_CATEGORY_ALIASES.items() if _has_alias(alias, lowered)), None)

    # Rural / Urban
    rural_urban = next((value for alias, value in RURAL_URBAN_ALIASES.items() if _has_alias(alias, lowered)), None)

    age_match = re.search(r"(?:age|aged|वय|उम्र)\D{0,8}(\d{1,3})|\b(\d{1,3})\s*(?:years|वर्ष|साल)\b", lowered)
    age = int(next(group for group in age_match.groups() if group)) if age_match else None

    # Income extraction (e.g. 2.5 lakh, 50000, etc.)
    income = None
    income_lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|लाख|लख)", lowered)
    if income_lakh_match:
        try:
            income = float(income_lakh_match.group(1)) * 100000.0
        except ValueError:
            pass
    elif current_question == "annual_income":
        num_match = re.search(r"\b(\d{4,8})\b", lowered)
        if num_match:
            income = float(num_match.group(1))

    land_answer = extract_owns_land(text, current_question)
    house_answer = extract_owns_house(text, current_question)

    return ExtractedUserInfo(
        intent=intent,
        occupation=occupation,
        state=state,
        age=age,
        gender="female" if any(value in lowered for value in ("female", "woman", "महिला", "स्त्री")) else None,
        annual_income=income,
        is_farmer=True if occupation == "farmer" else None,
        is_student=True if occupation == "student" else None,
        is_business=True if occupation in {"small business", "street vendor", "self-employed"} else None,
        owns_land=land_answer,
        owns_house=house_answer,
        social_category=social_cat,
        rural_or_urban=rural_urban,
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
    tokens = set(re.findall(r"[\w\u0900-\u097F]+", text.lower()))
    if any(tok in tokens for tok in ("no", "नाही", "नहीं", "नको", "नाहीये", "not")):
        return False
    if any(tok in tokens for tok in ("yes", "हो", "होय", "हाँ", "हां", "yeah", "yep")):
        return True
    return None


def extract_owns_land(text: str, current_question: Optional[str] = None) -> Optional[bool]:
    lowered = _clean(text)
    tokens = set(re.findall(r"[\w\u0900-\u097F]+", lowered))
    neg_phrases = (
        "जमीन नाही", "शेतजमीन नाही", "शेती नाही", "जमीन नहीं", "no land",
        "landless", "tenant farmer", "कुळ", "शेतमजूर", "do not have land",
        "dont have land", "no agricultural land",
    )
    if any(p in lowered for p in neg_phrases):
        return False
    pos_phrases = (
        "जमीन आहे", "शेतजमीन आहे", "शेती आहे", "जमीन है", "own land",
        "have land", "owns land", "cultivable land", "own agricultural land",
    )
    if any(p in lowered for p in pos_phrases):
        return True
    if current_question == "owns_land":
        neg_tokens = ("no", "not", "dont", "नाही", "नहीं", "नको", "नाहीये", "landless", "tenant")
        if any(tok in tokens for tok in neg_tokens):
            return False
        pos_tokens = ("yes", "हो", "होय", "हाँ", "हां", "yeah", "yep")
        if any(tok in tokens for tok in pos_tokens):
            return True
        return _yes_no(text)
    return None


def extract_owns_house(text: str, current_question: Optional[str] = None) -> Optional[bool]:
    lowered = _clean(text)
    tokens = set(re.findall(r"[\w\u0900-\u097F]+", lowered))
    neg_phrases = (
        "पक्के घर नाही", "पक्के घर नाहीये", "घर नाही", "पक्का मकान नहीं",
        "कच्चे घर", "कच्चा मकान", "झोपडी", "no pucca house", "no permanent house",
        "homeless", "no house", "kutcha house", "do not have", "dont have",
    )
    if any(p in lowered for p in neg_phrases):
        return False
    pos_phrases = (
        "पक्के घर आहे", "स्वतःचे घर आहे", "पक्का मकान है", "own a house",
        "own pucca house", "have pucca house", "permanent house",
    )
    if any(p in lowered for p in pos_phrases):
        return True
    if current_question == "owns_house":
        neg_tokens = ("no", "not", "dont", "नाही", "नहीं", "नको", "नाहीये", "कच्चे", "कच्चा", "kutcha", "झोपडी", "rented", "भाड्याने")
        if any(tok in tokens for tok in neg_tokens):
            return False
        pos_tokens = ("yes", "हो", "होय", "हाँ", "हां", "yeah", "yep")
        if any(tok in tokens for tok in pos_tokens):
            return True
        if any(tok in tokens for tok in ("पक्के", "पक्का", "pucca", "permanent")) and not any(tok in tokens for tok in neg_tokens):
            return True
        return _yes_no(text)
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
is_farmer, is_business, owns_land, owns_house, social_category, rural_or_urban,
language, confidence.
Use null when a value is unknown. Understand Marathi, Hindi, English, and mixed language.
Resolve natural phrases such as Maharashtra, महाराष्ट्र, MH, महाराष्ट्रात, and Nashik to Maharashtra.
Resolve social categories to general, sc, st, obc, ebc, dnt.
Resolve rural_or_urban to rural or urban.
Do not infer sensitive credentials. Do not determine eligibility. Do not return scheme facts.
Use the current profile and current question to interpret short follow-up answers.
""".strip()
