"""
Deterministic scheme-matching engine for YojnaSathi.

Evaluates citizen profile information against schemes to identify
potentially relevant schemes without making legal eligibility claims.
"""
from typing import List, Optional, Set
from app.schemas import CitizenProfile, Scheme, SchemeMatchResult

# Explicit age criteria boundaries: (min_age, max_age, is_exclusive)
AGE_BOUNDS = {
    "apy": (18, 40, True),                # 18–40 exclusive
    "pmsby": (18, 70, True),              # 18–70 exclusive
    "pmkvy": (15, 45, True),              # 15–45 exclusive
    "majhi-ladki-bahin": (21, 65, True),  # 21–65 exclusive
    "pmjdy": (10, None, True),            # 10+ exclusive lower bound
    "pm-jay": (70, None, False),          # 70+ senior citizen pathway (bonus only, non-exclusive)
}

# Explicit income ceilings (Rs)
INCOME_CEILINGS = {
    "pmay-u": 600000.0,
    "pm-yasasvi": 250000.0,
    "post-matric-sc": 250000.0,
    "majhi-ladki-bahin": 250000.0,
}

# Need keywords to scheme categories mapping
NEED_KEYWORD_MAP = {
    "crop insurance": ["agriculture"],
    "farming": ["agriculture"],
    "agriculture": ["agriculture"],
    "crop": ["agriculture"],
    "kisan": ["agriculture"],
    "fasal": ["agriculture"],
    "education": ["education"],
    "scholarship": ["education"],
    "student": ["education"],
    "study": ["education"],
    "school": ["education"],
    "college": ["education"],
    "housing": ["housing"],
    "house": ["housing"],
    "home": ["housing"],
    "shelter": ["housing"],
    "pucca": ["housing"],
    "awas": ["housing"],
    "awaas": ["housing"],
    "health": ["health"],
    "hospital": ["health"],
    "treatment": ["health"],
    "medical": ["health"],
    "health treatment": ["health"],
    "illness": ["health"],
    "medicine": ["health"],
    "business": ["small businesses", "financial inclusion"],
    "loan": ["small businesses", "financial inclusion"],
    "shop": ["small businesses", "financial inclusion"],
    "entrepreneur": ["small businesses", "financial inclusion"],
    "small business": ["small businesses", "financial inclusion"],
    "working capital": ["small businesses"],
    "micro enterprise": ["small businesses"],
    "bank": ["financial inclusion"],
    "banking": ["financial inclusion"],
    "savings": ["financial inclusion"],
    "credit": ["financial inclusion"],
    "employment": ["employment"],
    "job": ["employment"],
    "work": ["employment"],
    "skill": ["employment"],
    "training": ["employment"],
    "unemployed": ["employment"],
    "wage": ["employment"],
    "mgnrega": ["employment"],
    "insurance": ["insurance"],
    "accident insurance": ["insurance"],
    "life insurance": ["insurance"],
    "pension": ["insurance"],
    "women": ["women"],
    "woman": ["women"],
    "financial assistance for women": ["women"],
    "financial assistance": ["women", "financial inclusion"],
    "pregnancy": ["women"],
    "maternity": ["women"],
    "cooking gas": ["women"],
    "lpg": ["women"],
    "ladki": ["women"],
    "bahin": ["women"],
}


def _resolve_categories_from_needs(needs: Optional[List[str]]) -> Set[str]:
    """Map profile need phrases to standard scheme categories."""
    if not needs:
        return set()
    matched_categories: Set[str] = set()
    for need_str in needs:
        if not need_str:
            continue
        normalized_need = need_str.strip().lower()
        for key, categories in NEED_KEYWORD_MAP.items():
            if key in normalized_need or normalized_need in key:
                matched_categories.update(categories)
    return matched_categories


def match_schemes(
    profile: CitizenProfile,
    schemes: List[Scheme],
) -> List[SchemeMatchResult]:
    """
    Deterministically evaluates a citizen profile against schemes.
    
    Returns candidate schemes sorted by relevance_score descending,
    with clear matched reasons and missing information.
    Does not make legal eligibility determinations.
    """
    results: List[SchemeMatchResult] = []

    # Pre-compute profile attributes
    profile_state = profile.state.strip().lower() if profile.state else None
    profile_gender = profile.gender.strip().lower() if profile.gender else None
    profile_occupation = profile.occupation.strip().lower() if profile.occupation else None

    is_farmer_profile = (
        profile.is_farmer is True
        or profile.owns_land is True
        or (profile_occupation is not None and profile_occupation in {"farmer", "agriculture", "kisan"})
    )

    is_student_profile = (
        profile.is_student is True
        or (profile_occupation is not None and profile_occupation == "student")
    )

    is_female_profile = profile_gender in {"female", "woman"}

    is_business_profile = (
        profile_occupation is not None
        and profile_occupation in {
            "street vendor",
            "vendor",
            "small business",
            "entrepreneur",
            "self-employed",
        }
    )

    is_unskilled_profile = (
        profile_occupation is not None
        and profile_occupation in {"laborer", "daily wage", "worker", "unorganized"}
    )

    relevant_categories = _resolve_categories_from_needs(profile.needs)

    for scheme in schemes:
        scheme_id = scheme.id.lower()
        scheme_state = scheme.state.strip().lower()
        scheme_category = scheme.category.strip().lower()
        scheme_target_groups = {tg.strip().lower() for tg in scheme.target_groups}

        relevance_score = 0
        matched_reasons: List[str] = []

        # -------------------------------------------------------------
        # 1. State Compatibility & Scoring (+2)
        # -------------------------------------------------------------
        if scheme_state != "all-india":
            # State-specific scheme (e.g., Maharashtra)
            if profile_state is not None:
                if profile_state != scheme_state:
                    # Incompatible state -> exclude completely
                    continue
                else:
                    relevance_score += 2
                    matched_reasons.append(
                        f"Specifically available for residents of {scheme.state.strip().title()}"
                    )
            else:
                # profile_state is missing: may remain candidate only if another strong signal matches
                pass
        else:
            # All-India scheme
            if profile_state is not None:
                relevance_score += 2
                matched_reasons.append(
                    f"Applicable across India, including {profile.state.strip().title()}"
                )

        # -------------------------------------------------------------
        # 2. Target Group Matching (+3)
        # -------------------------------------------------------------
        tg_matched = False
        tg_reasons: List[str] = []

        # Farmer signals
        if is_farmer_profile:
            if any(tg in scheme_target_groups for tg in {"farmers", "rural citizens", "rural households"}):
                tg_matched = True
                tg_reasons.append("Relevant for farmers and rural citizens")

        # Student signals
        if is_student_profile:
            if any(tg in scheme_target_groups for tg in {"students", "youth"}):
                tg_matched = True
                tg_reasons.append("Relevant for students and youth")

        # Gender signals (Women)
        if is_female_profile:
            if any(
                tg in scheme_target_groups
                for tg in {"women", "pregnant women", "lactating mothers", "women entrepreneurs"}
            ):
                tg_matched = True
                tg_reasons.append("Provides targeted support for women")

        # Street vendor / micro-business
        if is_business_profile:
            if any(
                tg in scheme_target_groups
                for tg in {"street vendors", "micro entrepreneurs", "small business owners", "self-employed"}
            ):
                tg_matched = True
                tg_reasons.append("Relevant for small businesses, vendors, and entrepreneurs")

        # Unskilled / unorganized worker
        if is_unskilled_profile:
            if any(
                tg in scheme_target_groups
                for tg in {"unskilled workers", "unorganized sector workers", "low-income workers"}
            ):
                tg_matched = True
                tg_reasons.append("Relevant for unorganized and unskilled workers")

        if tg_matched:
            relevance_score += 3
            for r in tg_reasons:
                if r not in matched_reasons:
                    matched_reasons.append(r)

        # -------------------------------------------------------------
        # 3. Need / Category Matching (+3)
        # -------------------------------------------------------------
        if scheme_category in relevant_categories:
            relevance_score += 3
            matched_reasons.append(f"Matches your interest in {scheme.category.lower()}")

        # -------------------------------------------------------------
        # 4. Age Criteria (+1 or Exclusion)
        # -------------------------------------------------------------
        if scheme_id in AGE_BOUNDS:
            min_age, max_age, is_exclusive = AGE_BOUNDS[scheme_id]
            if profile.age is not None:
                if min_age is not None and profile.age < min_age:
                    if is_exclusive:
                        # Below strict minimum -> exclude
                        continue
                elif max_age is not None and profile.age > max_age:
                    if is_exclusive:
                        # Above strict maximum -> exclude
                        continue
                else:
                    # In range
                    relevance_score += 1
                    matched_reasons.append(f"Your age ({profile.age}) matches the scheme criteria")

        # -------------------------------------------------------------
        # 5. Income Criteria (+1 or Exclusion)
        # -------------------------------------------------------------
        if scheme_id in INCOME_CEILINGS:
            ceiling = INCOME_CEILINGS[scheme_id]
            if profile.annual_income is not None:
                if profile.annual_income <= ceiling:
                    relevance_score += 1
                    matched_reasons.append("Your income is within the scheme's threshold")
                else:
                    # Exceeds genuine ceiling -> exclude
                    continue

        # -------------------------------------------------------------
        # 6. State-specific scheme without profile.state guardrail
        # -------------------------------------------------------------
        if scheme_state != "all-india" and profile_state is None:
            # Must have at least another strong signal (target group or category match)
            if not tg_matched and scheme_category not in relevant_categories:
                continue

        # -------------------------------------------------------------
        # 7. Relevance Score Threshold
        # -------------------------------------------------------------
        if relevance_score > 0:
            missing_info = list(scheme.required_information)

            results.append(
                SchemeMatchResult(
                    scheme=scheme,
                    relevance_score=relevance_score,
                    matched_reasons=matched_reasons,
                    missing_information=missing_info,
                )
            )

    # Sort results by relevance_score descending
    results.sort(key=lambda item: item.relevance_score, reverse=True)
    return results
