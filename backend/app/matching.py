"""
Deterministic scheme-matching engine for YojnaSathi.

Evaluates citizen profile information against schemes to identify
potentially relevant schemes without making legal eligibility claims.
"""
from typing import Any, Dict, List, Optional, Set
from app.schemas import CitizenProfile, ReasonCodeItem, Scheme, SchemeMatchResult

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
    "pmay-u": 900000.0,
    "pm-yasasvi": 250000.0,
    "post-matric-sc": 250000.0,
    "majhi-ladki-bahin": 250000.0,
}

# Domains a scheme's *category* must belong to for a given target-group signal to
# count. For live-discovered schemes (heuristic category/target groups, no
# structured eligibility criteria) a broad target-group hit alone must not
# surface a scheme whose actual domain is unrelated (e.g. a girls' education
# scholarship is not a generic women-welfare scheme).
TARGET_GROUP_DOMAINS = {
    "farmer": {"agriculture"},
    "student": {"education"},
    "women": {"women"},
    "business": {"small businesses", "financial inclusion"},
    "unskilled": {"employment"},
}

# Social-category equivalence buckets. "open" and "general" are the same
# unreserved beneficiary category in Maharashtra; VJNT/DNT labels overlap and
# are treated as interchangeable for allow-list membership.
SOCIAL_CATEGORY_EQUIVALENCE = {
    "general": {"general", "open", "ebc"},
    "open": {"general", "open", "ebc"},
    "ebc": {"general", "open", "ebc"},
    "vjnt": {"vjnt", "dnt", "nt"},
    "dnt": {"vjnt", "dnt", "nt"},
    "nt": {"vjnt", "dnt", "nt"},
}
_RESIDENCE_HOSTEL_VALUES = {"hosteller", "hostel", "hostel resident", "living in hostel"}


_EDU_LEVEL_MAP = {
    "10th": "secondary",
    "ssc": "secondary",
    "secondary": "secondary",
    "11th": "higher_secondary",
    "12th": "higher_secondary",
    "hsc": "higher_secondary",
    "junior college": "higher_secondary",
    "junior_college": "higher_secondary",
    "higher secondary": "higher_secondary",
    "higher_secondary": "higher_secondary",
    "diploma": "diploma",
    "polytechnic": "diploma",
    "graduation": "undergraduate",
    "undergraduate": "undergraduate",
    "degree": "undergraduate",
    "ug": "undergraduate",
    "bachelor": "undergraduate",
    "postgraduate": "postgraduate",
    "post graduate": "postgraduate",
    "pg": "postgraduate",
    "master": "postgraduate",
    "doctorate": "doctorate",
    "phd": "doctorate",
    "ph.d": "doctorate",
    "research": "doctorate",
}


def _normalize_edu_level(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw_l = raw.strip().lower()
    for k, v in _EDU_LEVEL_MAP.items():
        if k in raw_l:
            return v
    return raw_l


def _normalize_social_category(cat: Optional[str]) -> str:
    return (cat or "").strip().lower()


def _social_categories_overlap(candidate: str, valid_cats: Set[str]) -> bool:
    candidate_set = SOCIAL_CATEGORY_EQUIVALENCE.get(candidate, {candidate})
    for valid in valid_cats:
        valid_set = SOCIAL_CATEGORY_EQUIVALENCE.get(valid, {valid})
        if candidate_set & valid_set:
            return True
    return False


def _append_missing_info(missing_information, note: str):
    """Append a follow-up note to missing_information without mutating shared
    scheme objects (scheme.required_information is cached across requests)."""
    if isinstance(missing_information, dict):
        return {lang: list(items) + [note] for lang, items in missing_information.items()}
    return list(missing_information or []) + [note]

# Mapping of website UI categories to backend scheme categories
CATEGORY_FILTER_MAP = {
    "farmers": {"agriculture"},
    "agriculture": {"agriculture"},
    "women": {"women"},
    "education": {"education"},
    "healthcare": {"health"},
    "health": {"health"},
    "housing": {"housing"},
    "employment": {"employment", "insurance"},
    "business": {"small businesses", "financial inclusion"},
    "small businesses": {"small businesses", "financial inclusion"},
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
    "financial support": ["women", "financial inclusion"],
    "financial aid": ["women", "financial inclusion"],
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
        normalized_need = need_str.strip().lower().replace("_", " ")
        for key, categories in NEED_KEYWORD_MAP.items():
            if key in normalized_need or normalized_need in key:
                matched_categories.update(categories)
    return matched_categories


def match_schemes(
    profile: CitizenProfile,
    schemes: List[Scheme],
    category: Optional[str] = None,
) -> List[SchemeMatchResult]:
    """
    Deterministically evaluates a citizen profile against schemes.
    Supports strict domain/category filtering and structured reason codes.
    Returns candidate schemes sorted by relevance_score descending.
    Does not make legal eligibility determinations.
    """
    results: List[SchemeMatchResult] = []

    # 1. Resolve Category / Domain constraints
    allowed_categories: Optional[Set[str]] = None
    if category:
        normalized_cat = category.strip().lower()
        if normalized_cat in CATEGORY_FILTER_MAP:
            allowed_categories = CATEGORY_FILTER_MAP[normalized_cat]
        else:
            allowed_categories = {normalized_cat}

    # Pre-compute profile attributes
    profile_state = profile.state.strip().lower() if profile.state else None
    profile_gender = profile.gender.strip().lower() if profile.gender else None
    profile_occupation = profile.occupation.strip().lower() if profile.occupation else None
    profile_social_cat = profile.social_category.strip().lower() if profile.social_category else None
    profile_rural_urban = profile.rural_or_urban.strip().lower() if profile.rural_or_urban else None
    profile_residence = profile.residence.strip().lower() if profile.residence else None
    profile_education_level = profile.education_level.strip().lower() if profile.education_level else None

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
        crit = scheme.eligibility_criteria
        # Live-discovered schemes use heuristically derived categories/target
        # groups, so target-group signals must be validated against the domain.
        is_live_discovered = scheme_id.startswith("web-")

        # -------------------------------------------------------------
        # Filter A: Category / Domain Filtering
        # -------------------------------------------------------------
        if allowed_categories is not None:
            if scheme_category not in allowed_categories:
                # Outside the citizen's selected domain
                continue

        relevance_score = 0
        matched_reasons: List[str] = []
        reason_codes: List[ReasonCodeItem] = []
        # Missing-information checklist starts from the scheme's documented
        # document requirements; eligibility follow-ups are appended below.
        missing_info = scheme.required_information

        # -------------------------------------------------------------
        # Filter B: State Compatibility
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
                    reason_codes.append(ReasonCodeItem(code="STATE_SPECIFIC_MATCH", params={"state": scheme.state}))
            else:
                # profile_state is missing: state-specific schemes require strong signal
                pass
        else:
            # All-India scheme
            if profile_state is not None:
                relevance_score += 2
                matched_reasons.append(
                    f"Applicable across India, including {profile.state.strip().title()}"
                )
                reason_codes.append(ReasonCodeItem(code="ALL_INDIA_AVAILABLE", params={"state": profile.state}))

        # -------------------------------------------------------------
        # Filter C: Scheme Eligibility Criteria Exclusions & Signals
        # -------------------------------------------------------------
        if crit:
            # 1. Farmer requirement
            if crit.requires_farmer is True and profile.is_farmer is False:
                continue

            # 2. Land ownership requirement (e.g. PM-KISAN requires cultivable landholding)
            if crit.requires_land is True:
                if profile.owns_land is False:
                    # Explicitly stated no land -> PM-KISAN cannot apply
                    continue
                elif profile.owns_land is True:
                    relevance_score += 1
                    matched_reasons.append("Matches your cultivable land ownership status")
                    reason_codes.append(ReasonCodeItem(code="LAND_OWNERSHIP_MATCH", params={}))

            # 3. Student requirement
            if crit.requires_student is True and profile.is_student is False:
                continue

            # 4. Social category (e.g., SC for Post-Matric SC, OBC for PM-YASASVI).
            #    ``social_categories`` is the scheme's ALLOW-LIST; a general/open
            #    profile passes schemes that admit the unreserved category (e.g.
            #    Shikshan Shulkh admits General + SEBC) and is excluded only when
            #    the scheme is restricted to reserved categories.
            if crit.social_categories:
                valid_cats = {c.strip().lower() for c in crit.social_categories}
                if profile_social_cat is not None:
                    if _social_categories_overlap(profile_social_cat, valid_cats):
                        relevance_score += 2
                        matched_reasons.append(
                            f"Matches your social category ({profile.social_category.upper()})"
                        )
                        reason_codes.append(
                            ReasonCodeItem(code="SOCIAL_CATEGORY_MATCH", params={"category": profile.social_category})
                        )
                    else:
                        # Belongs to a category outside this scheme's allow-list.
                        continue
                else:
                    # Unknown/Not specified: remains candidate, missing info noted
                    missing_info = _append_missing_info(
                        missing_info,
                        "Confirm your social category (this scheme is restricted to specific categories)",
                    )

            # 5. Rural / Urban area requirement (e.g., PMAY-G vs PMAY-U)
            if crit.rural_or_urban:
                req_area = crit.rural_or_urban.strip().lower()
                if profile_rural_urban is not None:
                    if profile_rural_urban != req_area:
                        continue
                    else:
                        relevance_score += 1
                        matched_reasons.append(f"Specifically designed for {req_area} areas")
                        reason_codes.append(ReasonCodeItem(code="AREA_MATCH", params={"area": req_area}))

            # 6. Pucca house ownership check (e.g. PMAY)
            if crit.requires_no_pucca_house is True:
                if profile.owns_house is True:
                    # Citizen family already owns a permanent pucca house -> excluded
                    continue
                elif profile.owns_house is False:
                    relevance_score += 1
                    matched_reasons.append("Addresses households without a permanent pucca house")
                    reason_codes.append(ReasonCodeItem(code="HOUSING_NEED_MATCH", params={}))

            # 7. Gender requirement
            if crit.gender:
                req_gender = crit.gender.strip().lower()
                if req_gender == "female":
                    if profile_gender in {"male", "man"}:
                        continue
                    elif is_female_profile:
                        relevance_score += 1
                        matched_reasons.append("Matches the scheme's female-applicant requirement")
                        reason_codes.append(ReasonCodeItem(code="GENDER_MATCH", params={"gender": "female"}))
                    elif profile_gender is None:
                        missing_info = _append_missing_info(
                            missing_info,
                            "Confirm gender eligibility (scheme is for female applicants)",
                        )
                elif req_gender == "male":
                    if is_female_profile:
                        continue
                    elif profile_gender in {"male", "man"}:
                        relevance_score += 1
                        matched_reasons.append("Matches the scheme's male-applicant requirement")
                        reason_codes.append(ReasonCodeItem(code="GENDER_MATCH", params={"gender": "male"}))
                    elif profile_gender is None:
                        missing_info = _append_missing_info(
                            missing_info,
                            "Confirm gender eligibility (scheme is for male applicants)",
                        )

            # 8. Disability requirement (affirmative restriction: must be explicitly confirmed)
            if crit.requires_disability is True:
                if profile.disability is not True:
                    continue
                relevance_score += 1
                matched_reasons.append("Matches the scheme's disability eligibility requirement")
                reason_codes.append(ReasonCodeItem(code="DISABILITY_MATCH", params={}))

            # 8b. Specific Institution requirement (affirmative restriction)
            if crit.requires_specific_institution is True:
                profile_inst = (profile.institution or "").strip().lower()
                if not profile_inst:
                    continue
                if not any(kw in profile_inst for kw in ["jnu", "vidyaniketan", "vidhyaniketan"]):
                    continue
                relevance_score += 2
                matched_reasons.append("Matches your specific educational institution")
                reason_codes.append(ReasonCodeItem(code="INSTITUTION_MATCH", params={"institution": profile.institution}))

            # 9. Minority community requirement (affirmative restriction: must be explicitly confirmed)
            if crit.minority_communities:
                if profile.is_minority is not True:
                    continue
                relevance_score += 1
                matched_reasons.append("Matches the scheme's minority community eligibility")
                reason_codes.append(ReasonCodeItem(code="MINORITY_MATCH", params={}))

            # 10. Special status requirement (affirmative restriction: must be explicitly confirmed)
            if crit.requires_special_status:
                profile_special = {sp.strip().lower() for sp in (profile.special_status or [])}
                if not any(req in profile_special for req in crit.requires_special_status):
                    continue
                relevance_score += 2
                matched_reasons.append("Matches your special eligibility status")
                reason_codes.append(
                    ReasonCodeItem(
                        code="SPECIAL_STATUS_MATCH",
                        params={"status": ", ".join(crit.requires_special_status)},
                    )
                )

            # 11. Residence requirement (hostel schemes)
            if crit.requires_hostel is True or (crit.residence and crit.residence.strip().lower() == "hosteller"):
                if profile.is_hosteller is False or profile_residence in {"day_scholar", "home", "with_parents", "non_hosteller"}:
                    continue
                elif profile.is_hosteller is True or profile_residence in _RESIDENCE_HOSTEL_VALUES:
                    relevance_score += 2
                    matched_reasons.append("Matches your hostel residence status")
                    reason_codes.append(ReasonCodeItem(code="RESIDENCE_MATCH", params={"residence": "hosteller"}))
                else:
                    missing_info = _append_missing_info(
                        missing_info,
                        "Confirm whether you reside in a hostel (scheme covers hostel residents)",
                    )
                    relevance_score -= 1

            # 12. Education level requirement
            if crit.education_level:
                prof_edu = _normalize_edu_level(profile.education_level)
                if prof_edu is not None:
                    if prof_edu in crit.education_level or (prof_edu == "undergraduate" and "diploma" in crit.education_level):
                        relevance_score += 2
                        matched_reasons.append("Matches your current education level")
                        reason_codes.append(ReasonCodeItem(code="EDUCATION_LEVEL_MATCH", params={"level": prof_edu}))
                    else:
                        continue
                else:
                    missing_info = _append_missing_info(
                        missing_info,
                        f"Confirm your course / education level (scheme covers: {', '.join(crit.education_level)})",
                    )

            # 13. Course / stream type requirement
            if crit.course_types:
                prof_course = (profile.course_type or "").strip().lower()
                if prof_course:
                    if any(ct in prof_course or prof_course in ct for ct in crit.course_types):
                        relevance_score += 1
                        matched_reasons.append("Matches your course / stream of study")
                        reason_codes.append(ReasonCodeItem(code="COURSE_TYPE_MATCH", params={"course": prof_course}))
                    else:
                        continue
                else:
                    missing_info = _append_missing_info(
                        missing_info,
                        f"Confirm your course / stream (scheme applies to: {', '.join(crit.course_types)})",
                    )

            # 14. Merit / board rank requirement
            if crit.requires_merit_rank is True:
                missing_info = _append_missing_info(
                    missing_info,
                    "Confirm if you secured top rank in secondary/higher secondary divisional board examinations",
                )
                relevance_score -= 1

            # 15. Minimum percentage requirement
            if crit.min_percentage is not None:
                if profile.percentage is not None:
                    if profile.percentage >= crit.min_percentage:
                        relevance_score += 1
                        matched_reasons.append(f"Your academic score meets the minimum {crit.min_percentage:.0f}% threshold")
                        reason_codes.append(ReasonCodeItem(code="PERCENTAGE_MATCH", params={"percentage": profile.percentage}))
                    else:
                        continue
                else:
                    missing_info = _append_missing_info(
                        missing_info,
                        f"Confirm your academic score (scheme requires minimum {crit.min_percentage:.0f}%)",
                    )

            # 16. Centralized Admission Process (CAP) requirement
            if crit.requires_cap_admission is True:
                missing_info = _append_missing_info(
                    missing_info,
                    "Confirm admission through Centralized Admission Process (CAP)",
                )

        # -------------------------------------------------------------
        # 2. Target Group Matching (+1 to +3)
        # -------------------------------------------------------------
        tg_matched = False

        if is_farmer_profile and any(tg in scheme_target_groups for tg in {"farmers", "rural citizens", "rural households"}):
            if not is_live_discovered or scheme_category in TARGET_GROUP_DOMAINS["farmer"]:
                tg_matched = True
                relevance_score += 3
                matched_reasons.append("Relevant for farmers and rural citizens")
                reason_codes.append(ReasonCodeItem(code="TARGET_GROUP_FARMER", params={}))

        if is_student_profile and any(tg in scheme_target_groups for tg in {"students", "youth"}):
            if not is_live_discovered or scheme_category in TARGET_GROUP_DOMAINS["student"]:
                tg_matched = True
                relevance_score += 1  # calibrated: generic student gives +1 so it does not inflate score
                matched_reasons.append("Relevant for students and youth")
                reason_codes.append(ReasonCodeItem(code="TARGET_GROUP_STUDENT", params={}))

        if is_female_profile and any(
            tg in scheme_target_groups
            for tg in {"women", "pregnant women", "lactating mothers", "women entrepreneurs"}
        ):
            if not is_live_discovered or scheme_category in TARGET_GROUP_DOMAINS["women"]:
                tg_matched = True
                relevance_score += 3
                matched_reasons.append("Provides targeted support for women")
                reason_codes.append(ReasonCodeItem(code="TARGET_GROUP_WOMEN", params={}))

        if is_business_profile and any(
            tg in scheme_target_groups
            for tg in {"street vendors", "micro entrepreneurs", "small business owners", "self-employed"}
        ):
            if not is_live_discovered or scheme_category in TARGET_GROUP_DOMAINS["business"]:
                tg_matched = True
                relevance_score += 3
                matched_reasons.append("Relevant for small businesses, vendors, and entrepreneurs")
                reason_codes.append(ReasonCodeItem(code="TARGET_GROUP_BUSINESS", params={}))

        if is_unskilled_profile and any(
            tg in scheme_target_groups
            for tg in {"unskilled workers", "unorganized sector workers", "low-income workers"}
        ):
            if not is_live_discovered or scheme_category in TARGET_GROUP_DOMAINS["unskilled"]:
                tg_matched = True
                relevance_score += 3
                matched_reasons.append("Relevant for unorganized and unskilled workers")
                reason_codes.append(ReasonCodeItem(code="TARGET_GROUP_WORKER", params={}))

        # -------------------------------------------------------------
        # 3. Need / Category Matching (+3)
        # -------------------------------------------------------------
        need_matched = False
        if scheme_category in relevant_categories:
            need_matched = True
            relevance_score += 3
            matched_reasons.append(f"Matches your interest in {scheme.category.lower()}")
            reason_codes.append(ReasonCodeItem(code="NEED_MATCH", params={"category": scheme.category}))

        # Granular Need Match (e.g. crop insurance specifically matches PMFBY)
        if profile.needs:
            for n in profile.needs:
                n_lower = n.lower()
                if ("crop insurance" in n_lower or "crop" in n_lower or "bima" in n_lower) and scheme_id == "pmfby":
                    relevance_score += 3
                elif ("direct support" in n_lower or "income support" in n_lower or "pm-kisan" in n_lower or "farming" in n_lower) and scheme_id == "pm-kisan":
                    relevance_score += 3
                elif "working capital" in n_lower and scheme_id == "pm-svanidhi":
                    relevance_score += 2

        # Live-discovered schemes rely on heuristically derived categories and
        # target groups (no structured eligibility criteria). When the citizen
        # has expressed concrete needs, a name-derived target-group match alone
        # must not surface a scheme from an unrelated domain.
        if (
            allowed_categories is None
            and relevant_categories
            and is_live_discovered
            and not need_matched
        ):
            continue

        # -------------------------------------------------------------
        # 4. Age Criteria (+1 or Exclusion)
        # -------------------------------------------------------------
        min_age, max_age, is_exclusive = None, None, True
        if crit and (crit.age_min is not None or crit.age_max is not None):
            min_age = crit.age_min
            max_age = crit.age_max
        elif scheme_id in AGE_BOUNDS:
            min_age, max_age, is_exclusive = AGE_BOUNDS[scheme_id]

        if profile.age is not None:
            if min_age is not None and profile.age < min_age:
                if is_exclusive:
                    continue
            elif max_age is not None and profile.age > max_age:
                if is_exclusive:
                    continue
            else:
                if min_age is not None or max_age is not None:
                    relevance_score += 1
                    matched_reasons.append(f"Your age ({profile.age}) matches the scheme criteria")
                    reason_codes.append(ReasonCodeItem(code="AGE_CRITERIA_MATCH", params={"age": profile.age}))

        # -------------------------------------------------------------
        # 5. Income Criteria (+1 or Exclusion)
        # -------------------------------------------------------------
        ceiling = crit.income_max if (crit and crit.income_max is not None) else INCOME_CEILINGS.get(scheme_id)
        if ceiling is not None:
            if profile.annual_income is not None:
                if profile.annual_income <= ceiling:
                    relevance_score += 1
                    matched_reasons.append("Your income is within the scheme's threshold")
                    reason_codes.append(ReasonCodeItem(code="INCOME_CRITERIA_MATCH", params={"income": profile.annual_income}))
                else:
                    # Exceeds genuine ceiling -> exclude
                    continue
            else:
                missing_info = _append_missing_info(
                    missing_info,
                    f"Confirm family annual income (scheme ceiling is Rs. {ceiling:,.0f})",
                )

        # -------------------------------------------------------------
        # 6. Primary Signal & Meaningful Score Threshold
        # -------------------------------------------------------------
        # A scheme must have a genuine situation match (not just All-India + state match)
        has_primary_signal = tg_matched or need_matched or (allowed_categories is not None and scheme_category in allowed_categories)

        if has_primary_signal and relevance_score >= 3:
            # Deduplicate reasons while preserving order
            unique_reasons = []
            for r in matched_reasons:
                if r not in unique_reasons:
                    unique_reasons.append(r)

            results.append(
                SchemeMatchResult(
                    scheme=scheme,
                    relevance_score=min(relevance_score, 10),
                    matched_reasons=unique_reasons,
                    reason_codes=reason_codes,
                    missing_information=missing_info,
                )
            )

    # Sort results by relevance_score descending
    results.sort(key=lambda item: item.relevance_score, reverse=True)
    return results
