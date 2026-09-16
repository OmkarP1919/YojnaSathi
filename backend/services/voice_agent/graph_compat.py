from __future__ import annotations

import re


def detect_language_fallback(text: str) -> str:
    if not re.search(r"[\u0900-\u097F]", text):
        return "en"
    hindi_markers = ("मुझे", "मैं", "चाहिए", "किसान", "किसानों", "योजना", "राज्य", "हूँ")
    marathi_markers = ("मला", "मी", "पाहिजे", "शेत", "शेतकरी", "तुम्ही", "आहे", "मराठी")
    hindi_score = sum(marker in text for marker in hindi_markers)
    marathi_score = sum(marker in text for marker in marathi_markers)
    return "mr" if marathi_score >= hindi_score else "hi"
