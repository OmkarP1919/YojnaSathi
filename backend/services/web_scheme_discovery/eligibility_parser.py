"""Generic eligibility extraction for officially published scheme text.

Converts plain-language eligibility / overview / scheme-name text (as published
on an official government portal) into a structured ``SchemeEligibilityCriteria``.

Design rules
------------
- Rules are derived from language patterns, NEVER from hardcoded scheme names.
- Only signals that are expressed as *restrictions* are turned into constraints;
  differential wording (e.g. benefit tables describing hosteller vs day-scholar
  amounts) is ignored so it cannot produce false exclusions.
- Unknown profile-side dimensions (disability, minority, residence,
  education level) are surfaced by the matcher as "missing information" rather
  than fabricated exclusions.
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.schemas import SchemeEligibilityCriteria

# ---------------------------------------------------------------------------
# Social-category restriction detection.
#
# The scheme text is split into sentences; only sentences that actually mention
# a "category"/"community" keyword contribute restriction tokens. Multi-word
# reserved phrases (scheduled caste, other backward class, ...) are recognised
# anywhere in such a sentence; short abbreviations (sc, st, obc, ...) only near
# the keyword to avoid cross-sentence bleed ("...first two children...").
# "open category" and "general category" are the same unreserved bucket in
# Maharashtra, so both normalize to "general".
# ---------------------------------------------------------------------------
_FULL_PHRASE_TOKENS: List[tuple] = [
    (r"\bscheduled caste\b", "sc"),
    (r"\bschedule caste\b", "sc"),
    (r"\bscheduled tribe\b", "st"),
    (r"\bschedule tribe\b", "st"),
    (r"\bother backward class\b", "obc"),
    (r"\bsocially and educationally backward class\b", "sebc"),
    (r"\bspecial backward class\b", "sbc"),
    (r"\beconomically backward class\b", "ebc"),
    (r"\beconomically weaker section\b", "ews"),
    (r"\bdenotified\b", "dnt"),
    (r"\bnomadic tribe\b", "dnt"),
    (r"\bnomadic\b", "dnt"),
    (r"\bvimukta\b", "vjnt"),
    (r"\b(?:general|open)\s+categor(?:y|ies)?\b", "general"),
]

_SHORT_TOKEN_RE = re.compile(
    r"\b(?:vjnt|sebc|obc|sbc|ebc|ews|dnt|nt-d|sc|st|nt|dt)\b", re.I
)
_SHORT_TOKEN_LABELS = {
    "vjnt": "vjnt",
    "sebc": "sebc",
    "obc": "obc",
    "sbc": "sbc",
    "ebc": "ebc",
    "ews": "ews",
    "dnt": "dnt",
    "nt-d": "dnt",
    "nt": "dnt",
    "dt": "dnt",
    "sc": "sc",
    "st": "st",
}

_NAME_STUDENT_RE = re.compile(
    r"\b(?:scheduled caste|schedule caste|scheduled tribe|schedule tribe|"
    r"other backward class|socially and educationally backward class|"
    r"special backward class|economically backward class|sc|st|obc|vjnt|"
    r"sbc|sebc|ebc|dnt)\b.{0,30}?\b(?:students?|candidates?|applicants?|girls?|boys?)\b",
    re.I,
)

_OPEN_TO_ALL_RE = re.compile(
    r"all\s+categor|open to all|open for all|any categor|no\s+categor|"
    r"no caste|irrespective of caste|caste no bar|caste certificate no bar"
    r"|any class|caste certificate is not needed",
    re.I,
)

_CATEGORY_KW_RE = re.compile(
    r"\bcategor(?:y|ies)\b|\bcommunities?\b|\bcastes?\b|\btribes?\b|\btribal\b|\bapplicable\s+for\b",
    re.I,
)

_CATEGORY_RESTRICTION_PATTERNS: List[tuple[str, str]] = [
    # ST / Tribal
    (r"\b(?:applicable for|for|only for|scheme for)\s+st\b", "st"),
    (r"\bst\s+(?:caste|category|only|students?|candidates?)\b", "st"),
    (r"\bfor\s+tribal\s+students?\b|\btribal\s+students?\b|\bscheduled\s+tribes?\b|\bschedule\s+tribes?\b", "st"),
    # SC
    (r"\b(?:applicable for|for|only for|scheme for)\s+sc\b", "sc"),
    (r"\bsc\s+(?:caste|category|only|students?|candidates?)\b", "sc"),
    (r"\bfor\s+sc\s+students?\b|\bscheduled\s+castes?\b|\bschedule\s+castes?\b", "sc"),
    # OBC
    (r"\b(?:applicable for|for|only for|scheme for)\s+obc\b", "obc"),
    (r"\bobc\s+(?:caste|category|only|students?|candidates?)\b", "obc"),
    (r"\bother\s+backward\s+class(?:es)?\b", "obc"),
    # VJNT / NT / DT
    (r"\b(?:applicable for|for|only for|scheme for)\s+(?:vjnt|vj|nt|dt)\b", "vjnt"),
    (r"\b(?:vjnt|vj|nt|dt|vimukta)\s+(?:caste|category|only|students?|candidates?)\b", "vjnt"),
    (r"\b(?:vjnt|vj|nt|dt)\s+students?\b", "vjnt"),
    (r"\bnomadic\s+tribes?\b|\bdenotified\s+tribes?\b|\bvimukta\s+jati\b", "vjnt"),
    # SBC
    (r"\b(?:applicable for|for|only for|scheme for)\s+sbc\b", "sbc"),
    (r"\bsbc\s+(?:caste|category|only|students?|candidates?)\b", "sbc"),
    (r"\bspecial\s+backward\s+class(?:es)?\b", "sbc"),
    # SEBC
    (r"\bsocially\s+and\s+educationally\s+backward\s+class(?:es)?\b|\bsebc\b", "sebc"),
    # EBC
    (r"\beconomically\s+backward\s+class(?:es)?\b|\bebc\b", "ebc"),
    # EWS
    (r"\beconomically\s+weaker\s+sections?\b|\bews\b", "ews"),
    # Open / General
    (r"\b(?:general|open)\s+categor(?:y|ies)?\b", "general"),
    (r"\b(?:applicable for|for|only for)\s+(?:general|open)\b", "general"),
    (r"\b(?:general|open)\s+(?:caste|only|students?|candidates?)\b", "general"),
    (r"\bopen\s+category\s+students?\b|\bgeneral\s+category\s+students?\b", "general"),
    (r"\bopen\s+merit\b", "general"),
]

_SPECIAL_STATUS_PATTERNS: List[tuple[str, str]] = [
    (r"\b(?:children\s+(?:of\s+)?ex[- ]service|ex[- ]servicem[ae]n|sainik\b)", "ex_servicemen"),
    (r"\b(?:children\s+(?:of\s+)?freedom\s+fighters?|freedom\s+fighters?\b|swatantrata\b)", "freedom_fighter"),
    (r"\b(?:only\s+for\s+orphans?|scheme\s+for\s+orphans?|orphan\s+students?)\b", "orphan"),
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_NEAR_KW_SPAN = 40


def _sentence_category_tokens(
    sentence: str, keyword_spans: List[tuple[int, int]]
) -> set[str]:
    """Extract category tokens that this sentence genuinely restricts on."""
    found: set[str] = set()
    for pattern, label in _FULL_PHRASE_TOKENS:
        if re.search(pattern, sentence, re.I):
            found.add(label)
    for start, end in keyword_spans:
        # "Beneficiary Category: OPEN" / "Category : General" colon form.
        tail = sentence[end:end + _NEAR_KW_SPAN]
        if re.match(r"\s*[:=]\s*-?\s*(?:open|general)\b", tail, re.I):
            found.add("general")
        span_lo = max(0, start - _NEAR_KW_SPAN)
        span_hi = min(len(sentence), end + _NEAR_KW_SPAN)
        span = sentence[span_lo:span_hi]
        for m in _SHORT_TOKEN_RE.finditer(span):
            label = _SHORT_TOKEN_LABELS.get(m.group(0).lower())
            if label:
                found.add(label)
    return found

# ---------------------------------------------------------------------------
# Numeric income ceilings: "(Rs.) 8.00 lakh", "Rs.8,00,000", "up to Rs. 8 lakh".
# Small rupee amounts (stipends, allowances) are deliberately ignored.
# ---------------------------------------------------------------------------
_INCOME_LAKH_RE = re.compile(
    r"\brs\.?\s*([0-9][0-9,.]{0,12})\s*(?:lacs?|lakhs?|lakh)\b", re.I
)
_INCOME_BIG_RE = re.compile(r"\brs\.?\s*([0-9][0-9,]{5,12})\b", re.I)


def _parse_money(raw: str) -> Optional[float]:
    s = re.sub(r"[^0-9.]", "", raw or "")
    if not s or s.count(".") > 1:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_income_max(text: str) -> Optional[float]:
    ceilings: List[float] = []
    for m in _INCOME_LAKH_RE.finditer(text or ""):
        val = _parse_money(m.group(1))
        if val is None:
            continue
        ceilings.append(val * 100_000.0)
    for m in _INCOME_BIG_RE.finditer(text or ""):
        val = _parse_money(m.group(1))
        if val is None or val < 100_000.0:
            continue
        ceilings.append(val)
    if not ceilings:
        return None
    return max(ceilings)


# ---------------------------------------------------------------------------
# Gender restriction: female-only phrases. Guarded against texts that also
# mention boys/males as eligible (benefit differentiation).
# ---------------------------------------------------------------------------
_FEMALE_ONLY_RE = re.compile(
    r"\b(?:girls? only|only (?:for )?girls?|only women|for (?:the )?girls? "
    r"under|girls? belong(?:ing)? to|scholarship to (?:the )?girls?|"
    r"girl (?:students?|candidates?|applicants?|child)|female (?:students?|"
    r"candidates?|applicants?)|women only)\b",
    re.I,
)
_HAS_BOYS_RE = re.compile(r"\bboys?|males?\b", re.I)

# ---------------------------------------------------------------------------
# Disability requirement.
# ---------------------------------------------------------------------------
_DISABILITY_RE = re.compile(r"\bdisab|divyang|differently able|\u0905\u092a\u0902\u0917", re.I)

# ---------------------------------------------------------------------------
# Residence requirement (hostel allowance schemes). Only phrases that state a
# hostel-stay *condition* count — allowance tables that merely mention hostlers
# ("for hostlers Rs.425/p.m.") do NOT indicate a residence requirement.
# ---------------------------------------------------------------------------
_RESIDENCE_HOSTEL_RE = re.compile(
    r"\b(?:hostel admission|admission in (?:a |the |government )?hostel|"
    r"staying in (?:a |the )?hostel|resid(?:ing|ents?) in (?:a |the )?hostel|"
    r"living in (?:a |the )?hostel)\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Minority requirement.
# ---------------------------------------------------------------------------
_MINORITY_RE = re.compile(
    r"\bminorit|muslim|buddhist|christian|sikh|parsi|jain|jews|\u0905\u0932\u094d\u092a\u0938\u0902\u0916\u094d\u092f",
    re.I,
)

# ---------------------------------------------------------------------------
# Education level / course signals (free form; used for context + missing info).
# ---------------------------------------------------------------------------
_EDUCATION_LEVEL_RE = re.compile(
    r"\b(?:post[ -]?matric|pre[ -]?matric|11th|12th|hsc|ssc|junior college|"
    r"senior college|degree course|diploma course|m\.?phil|p\.?h\.?d|"
    r"professional courses?|non[ -]professional courses?|itian?|"
    r"medical|dental|engineering|agriculture university|mbbs|bds|bams|bhms)\b",
    re.I,
)

_STUDENT_SIGNALS = (
    "scholarship", "shishyavrutti", "student", "vidyarthi", "college",
    "tuition", "exam", "hostel", "education", "course", "study", "school",
    "\u0935\u093f\u0926\u094d\u092f\u093e\u0930\u094d\u0925\u0940",
)

_MALE_ONLY_RE = re.compile(
    r"\b(?:boys? only|only (?:for )?boys?|for boys - only|male students? only)\b",
    re.I,
)

_HOSTEL_REQUIREMENT_RE = re.compile(
    r"\b(?:applicant should be hosteller|must be (?:a )?hosteller|"
    r"taken hostel admission|hostel maintenance allowance|"
    r"vasatigruh nirvah|vastigruh nirvah)\b",
    re.I,
)

_SPECIFIC_INSTITUTION_RE = re.compile(
    r"\b(?:studied in jnu|from jnu|decided by jnu|"
    r"vidy[ah]*niket[h]?[ah]n only|passed .* from .*vidy[ah]*niket[h]?[ah]n)\b",
    re.I,
)

_MERIT_RANK_RE = re.compile(
    r"\b(?:top rank in (?:secondary|higher secondary)|from each divisional board \d+ students|"
    r"divisional board total \d+ students)\b",
    re.I,
)

_MIN_PERCENT_RE = re.compile(
    r"\b(?:minimum|at\s*least|secure|securing|having|with)\s*(?:of\s*)?([5-9][0-9])\s*(?:%|percent|percentage)\b",
    re.I,
)

_CAP_ADMISSION_RE = re.compile(
    r"\b(?:centralized admission process|through cap|admitted through cap|cap admission)\b",
    re.I,
)

_COURSE_TYPE_PATTERNS: List[tuple[str, str]] = [
    (r"\bprofessional (?:and technical |and vocational )?courses?\b|\bprofessional technical\b", "professional"),
    (r"\bnon[ -]professional courses?\b", "non_professional"),
    (r"\b(?:mbbs|bds|bams|bhms|bpth|both|b\.?sc nursing|bums|bp & o|baslp|medical education|medical and dental)\b", "medical"),
    (r"\b(?:engineering|polytechnic|technical courses?|directorate of technical education|dte)\b", "engineering"),
    (r"\b(?:maths or physics|mathematics\s*/\s*physics)\b", "science_math_physics"),
    (r"\b(?:science graduation|science students|stream.*science|science exam)\b", "science"),
    (r"\b(?:arts,? commerce,? (?:and )?science|arts commerce and law|law,? commerce & arts)\b", "arts_commerce_science"),
    (r"\b(?:law graduation|law college)\b", "law"),
    (r"\b(?:agriculture university|agricultural|krishi|mafsu|veterinary)\b", "agriculture"),
    (r"\bdirectorate of art\b", "fine_art"),
    (r"\b(?:ph\.?d|research fellowship|jrf)\b", "research"),
]


def _extract_target_education_levels(text: str) -> Optional[List[str]]:
    text_l = text.lower()
    levels = set()

    if re.search(r"\b(?:ph\.?d|junior research fellowship|jrf|wanted to do ph\.?d)\b", text_l):
        levels.add("doctorate")

    if re.search(r"\b(?:admitted for post[ -]?graduate|studying in pg|only for pg|after pg|post graduate medical|post graduate degree)\b", text_l):
        levels.add("postgraduate")

    if re.search(r"\b(?:class 11|class 12|11th and 12th|11th - 12th|11 & 12th|in junior college)\b", text_l):
        levels.add("higher_secondary")

    if re.search(r"\b(?:science graduation|admited in arts commerce science law graduation|undergraduate|degree course|mbbs|bds|bams|bhms|diploma / graduation|diploma / degree)\b", text_l):
        levels.add("undergraduate")

    if re.search(r"\bdiploma\b", text_l):
        levels.add("diploma")

    if re.search(r"\b(?:diploma / degree / post ?graduate|diploma / graduation / post graduation)\b", text_l):
        levels.update(["diploma", "undergraduate", "postgraduate"])

    # If explicitly for postgraduate only (like Eklavya), discard undergraduate
    if re.search(r"\b(?:admitted for post[ -]?graduate|studying in pg|only for pg)\b", text_l) and not re.search(r"\bdiploma\b", text_l):
        levels.discard("undergraduate")

    return sorted(levels) if levels else None


def _restricted_social_categories(
    name: str, overview: str, eligibility_lines: List[str]
) -> Optional[set[str]]:
    """Return the *allow-list* of beneficiary social categories, or None if the
    scheme text does not state a category restriction."""
    text = re.sub(
        r"\s+",
        " ",
        " ".join([name or "", overview or "", " ".join(eligibility_lines or [])]),
    )
    if _OPEN_TO_ALL_RE.search(text):
        return None

    found: set[str] = set()

    # 1. Generic category restriction patterns across eligibility lines, overview, and title.
    for pattern, cat in _CATEGORY_RESTRICTION_PATTERNS:
        if re.search(pattern, text, re.I):
            found.add(cat)

    # 2. Sentences mentioning category/caste/community keywords.
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        keyword_spans = [(m.start(), m.end()) for m in _CATEGORY_KW_RE.finditer(sentence)]
        if keyword_spans:
            found.update(_sentence_category_tokens(sentence, keyword_spans))

    # 3. Scheme-title restriction ("... to OBC Students ...").
    if (name or "").strip() and _NAME_STUDENT_RE.search(name or ""):
        name_spans = [(0, len(name))] if _CATEGORY_KW_RE.search(name) else []
        found.update(_sentence_category_tokens(name, name_spans))
        # Short tokens in a title that both names a category and a beneficiary
        # group may lack the "category" keyword ("... to VJNT Students ...").
        for m in _SHORT_TOKEN_RE.finditer(name or ""):
            label = _SHORT_TOKEN_LABELS.get(m.group(0).lower())
            if label:
                found.add(label)
        for pattern, label in _FULL_PHRASE_TOKENS:
            phrase_label = "general" if label == "general" else label
            if re.search(pattern, name, re.I):
                found.add(phrase_label)

    return found or None


def derive_eligibility_criteria(
    name: Optional[str],
    eligibility_lines: Optional[List[str]],
    overview: Optional[str] = None,
    benefits: Optional[List[str]] = None,
) -> Optional[SchemeEligibilityCriteria]:
    """Build a structured criteria object from official plain-language text."""
    name = name or ""
    eligibility_lines = list(eligibility_lines or [])
    overview = overview or ""
    benefits = list(benefits or [])
    eligibility_text = " ".join(eligibility_lines)
    # Restriction detection scans name + eligibility + overview but NOT benefits
    # (benefit tables routinely describe differential rates for sub-groups and
    # would fabricate false constraints).
    restriction_text = " ".join([name, eligibility_text, overview])
    # Income may legitimately appear in the benefits/preview too.
    full_text = " ".join([restriction_text, " ".join(benefits)])

    social = _restricted_social_categories(name, overview, eligibility_lines)

    if social:
        sorted_cats = sorted(social)
    else:
        sorted_cats = []

    income = _extract_income_max(full_text)

    gender = None
    if _FEMALE_ONLY_RE.search(restriction_text) and not _HAS_BOYS_RE.search(
        restriction_text
    ):
        gender = "female"
    elif _MALE_ONLY_RE.search(restriction_text) and not _FEMALE_ONLY_RE.search(
        restriction_text
    ):
        gender = "male"

    disability = bool(_DISABILITY_RE.search(restriction_text))

    requires_hostel = bool(
        _HOSTEL_REQUIREMENT_RE.search(restriction_text)
        or _RESIDENCE_HOSTEL_RE.search(eligibility_text)
    )
    residence = "hosteller" if requires_hostel else None

    minority_tokens = [
        m.group(0).strip(" .") for m in _MINORITY_RE.finditer(restriction_text)
    ]
    minority = sorted({t.lower() for t in minority_tokens if t}) if minority_tokens else None

    special_status_found = set()
    for pattern, label in _SPECIAL_STATUS_PATTERNS:
        if re.search(pattern, restriction_text, re.I):
            special_status_found.add(label)
    requires_special = sorted(special_status_found) if special_status_found else None

    requires_specific_institution = bool(_SPECIFIC_INSTITUTION_RE.search(restriction_text))
    requires_merit_rank = bool(_MERIT_RANK_RE.search(restriction_text))
    requires_cap_admission = bool(_CAP_ADMISSION_RE.search(restriction_text))

    percents = [float(m.group(1)) for m in _MIN_PERCENT_RE.finditer(restriction_text)]
    min_percentage = min(percents) if percents else None

    education_level = _extract_target_education_levels(restriction_text)

    c_types = set()
    for pattern, ctype in _COURSE_TYPE_PATTERNS:
        if re.search(pattern, restriction_text, re.I):
            c_types.add(ctype)
    course_types = sorted(c_types) if c_types else None

    requires_student = any(sig in full_text.lower() for sig in _STUDENT_SIGNALS)

    if (
        not sorted_cats
        and income is None
        and gender is None
        and not disability
        and residence is None
        and not minority
        and not education_level
        and not requires_student
        and not requires_special
        and not requires_hostel
        and not requires_specific_institution
        and not requires_merit_rank
        and min_percentage is None
        and not course_types
        and not requires_cap_admission
    ):
        return None

    return SchemeEligibilityCriteria(
        social_categories=sorted_cats or None,
        income_max=income,
        gender=gender,
        requires_student=requires_student or None,
        requires_disability=disability or None,
        minority_communities=minority,
        residence=residence,
        education_level=education_level,
        requires_special_status=requires_special,
        course_types=course_types,
        min_percentage=min_percentage,
        requires_merit_rank=requires_merit_rank or None,
        requires_hostel=requires_hostel or None,
        requires_specific_institution=requires_specific_institution or None,
        requires_cap_admission=requires_cap_admission or None,
    )