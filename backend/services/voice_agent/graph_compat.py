from __future__ import annotations

import re
from typing import Optional

HINDI_DISTINCT_WORDS = {
    "मुझे", "मैं", "चाहिए", "किसान", "किसानों", "हूँ", "हूं", "हिंदी",
    "है", "हैं", "हाँ", "हां", "नहीं", "पास", "मेरे", "मेरा", "मेरी",
    "के", "की", "का", "में", "से", "आप", "आपका", "आपकी", "क्या",
    "करना", "करता", "करते", "करती", "योजनाएं", "योजनाओं", "कच्चा", "मकान",
    "लिए", "रहते", "रहता", "रहती", "भारत",
}

MARATHI_DISTINCT_WORDS = {
    "मला", "मी", "पाहिजे", "शेत", "शेतकरी", "शेतकऱ्यांना", "तुम्ही",
    "आहे", "आहेत", "मराठी", "नाही", "नाहीत", "नाहीये", "होय", "माझे",
    "माझ्या", "माझ्याकडे", "माझी", "नको", "करावे", "करतो", "करते",
    "काय", "मध्ये", "तुमचे", "तुमच्या", "तुमच्याकडे", "हवे", "हवी",
    "कच्चे", "घर", "गावात", "शहरात", "राहता", "राहतो", "राहते", "प्रवर्ग",
    "सापडली", "सापडल्या",
}

SHORT_FOLLOWUP_WORDS = {
    "yes", "no", "y", "n", "obc", "sc", "st", "ebc", "dnt", "general",
    "mh", "maharashtra", "rural", "urban", "male", "female", "farmer",
    "student", "nashik", "pune", "mumbai", "nagpur",
}


def detect_language_fallback(
    text: str,
    client_hint: Optional[str] = None,
    session_lang: Optional[str] = None,
) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return client_hint or session_lang or "en"

    devanagari_chars = re.findall(r"[\u0900-\u097F]", cleaned)
    if not devanagari_chars:
        words = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", cleaned)]
        is_short_followup = len(words) <= 2 and (
            all(w.isdigit() for w in words)
            or any(w in SHORT_FOLLOWUP_WORDS for w in words)
        )
        if is_short_followup and session_lang in {"hi", "mr"}:
            return session_lang

        if client_hint in {"hi", "mr", "en"}:
            return client_hint

        return "en"

    words = set(re.findall(r"[\u0900-\u097F]+", cleaned))
    hindi_score = sum(1 for w in words if w in HINDI_DISTINCT_WORDS)
    marathi_score = sum(1 for w in words if w in MARATHI_DISTINCT_WORDS)

    if marathi_score > hindi_score:
        return "mr"
    if hindi_score > marathi_score:
        return "hi"

    if client_hint in {"hi", "mr"}:
        return client_hint
    if session_lang in {"hi", "mr"}:
        return session_lang
    return "hi"
