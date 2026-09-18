"""Focused tests for generic MahaDBT eligibility parsing and matching compatibility.

Verifies that:
1. Category-restricted schemes (SC/ST/OBC/VJNT/SBC) are excluded for General/Open profiles.
2. Affirmative restrictions (minority, disability, special status) exclude candidates when unconfirmed.
3. Gender conflicts exclude candidates when gender is explicitly known.
4. Open/EBC/merit schemes (e.g. Rajarshi/Panjabrao-type) remain eligible candidates for General/Open profiles.
5. Explicit SC/ST/OBC profiles can receive their corresponding category-specific schemes.
6. Unknown social category does not incorrectly exclude reserved-category schemes.
7. No hardcoded scheme names exist in parser or matching logic.
"""
import pytest
from app.matching import match_schemes
from app.schemas import CitizenProfile, Scheme, SchemeEligibilityCriteria
from services.maharashtra_schemes.service import get_maharashtra_schemes
from services.web_scheme_discovery.adapter import discovered_to_canonical_scheme
from services.web_scheme_discovery.eligibility_parser import (
    _restricted_social_categories,
    derive_eligibility_criteria,
)


@pytest.fixture(scope="module")
def mahadbt_schemes():
    """Load canonical schemes converted from live MahaDBT catalog."""
    discovered = get_maharashtra_schemes()
    return [discovered_to_canonical_scheme(d) for d in discovered]


# ---------------------------------------------------------------------------
# 1. Eligibility Parser Tests
# ---------------------------------------------------------------------------


def test_parser_extracts_st_and_sc_restrictions_generically():
    """Verify generic parsing of ST/SC variants without scheme names."""
    # ST phrases
    assert _restricted_social_categories("", "", ["Applicable for ST only"]) == {"st"}
    assert _restricted_social_categories("", "", ["Applicable for ST caste only"]) == {"st"}
    assert _restricted_social_categories("", "", ["Scheme for Scheduled Tribe students"]) == {"st"}
    assert _restricted_social_categories("", "", ["Tuition fee support for tribal students"]) == {"st"}

    # SC phrases
    assert _restricted_social_categories("", "", ["Applicable for SC only"]) == {"sc"}
    assert _restricted_social_categories("", "", ["Candidate must belong to Scheduled Caste"]) == {"sc"}
    assert _restricted_social_categories("", "", ["Post matric support for SC students"]) == {"sc"}


def test_parser_extracts_obc_vjnt_sbc_restrictions_generically():
    """Verify generic parsing of OBC, VJNT, and SBC restrictions."""
    assert _restricted_social_categories("", "", ["Applicable for OBC only"]) == {"obc"}
    assert _restricted_social_categories("", "", ["Eligible: Other Backward Classes only"]) == {"obc"}
    assert _restricted_social_categories("", "", ["Applicable for VJNT only"]) == {"vjnt"}
    res_vjnt = _restricted_social_categories("", "", ["Belonging to Vimukta Jati / Nomadic Tribes"])
    assert "vjnt" in res_vjnt or "dnt" in res_vjnt
    assert _restricted_social_categories("", "", ["Applicable for SBC only"]) == {"sbc"}
    assert _restricted_social_categories("", "", ["Special Backward Class category candidates"]) == {"sbc"}


def test_parser_extracts_affirmative_special_status_and_disability():
    """Verify affirmative detection of disability, minority, and special status."""
    crit_disability = derive_eligibility_criteria(
        name="Scholarship Scheme",
        eligibility_lines=["Applicant must be a Divyang student with valid disability certificate."],
    )
    assert crit_disability is not None
    assert crit_disability.requires_disability is True

    crit_minority = derive_eligibility_criteria(
        name="State Scholarship Scheme",
        eligibility_lines=["Applicable for students belonging to minority communities (Muslim, Christian, Buddhist)."],
    )
    assert crit_minority is not None
    assert crit_minority.minority_communities is not None

    crit_ex_servicemen = derive_eligibility_criteria(
        name="State Education Scheme",
        eligibility_lines=["The applicant must be a son/daughter of an Ex-Serviceman."],
    )
    assert crit_ex_servicemen is not None
    assert crit_ex_servicemen.requires_special_status == ["ex_servicemen"]

    crit_freedom_fighter = derive_eligibility_criteria(
        name="State Education Scheme",
        eligibility_lines=["Financial assistance to children of freedom fighters."],
    )
    assert crit_freedom_fighter is not None
    assert crit_freedom_fighter.requires_special_status == ["freedom_fighter"]


# ---------------------------------------------------------------------------
# 2. Matching Engine Hard Compatibility Tests
# ---------------------------------------------------------------------------


def test_general_open_student_excludes_reserved_category_schemes(mahadbt_schemes):
    """General/Open student -> SC/ST/OBC/VJNT/SBC restricted schemes are excluded."""
    profile = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
    )
    results = match_schemes(profile, mahadbt_schemes)
    matched_scheme_ids = {r.scheme.id for r in results}

    for r in results:
        crit = r.scheme.eligibility_criteria
        if crit and crit.social_categories:
            valid_cats = {c.lower() for c in crit.social_categories}
            # Must overlap with general / open / ebc
            assert valid_cats & {"general", "open", "ebc"}, (
                f"Scheme {r.scheme.id} with cats {valid_cats} improperly matched General profile"
            )


def test_general_open_student_excludes_affirmative_minority_and_disability(mahadbt_schemes):
    """General/Open student -> minority/disability schemes excluded when status is unknown."""
    profile = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="general",
        is_minority=None,   # Unknown
        disability=None,    # Unknown
        needs=["education", "scholarship"],
    )
    results = match_schemes(profile, mahadbt_schemes)

    for r in results:
        crit = r.scheme.eligibility_criteria
        if crit:
            assert crit.requires_disability is not True, (
                f"Disability-only scheme {r.scheme.id} should be excluded when disability status is unknown"
            )
            assert not crit.minority_communities, (
                f"Minority-only scheme {r.scheme.id} should be excluded when minority status is unknown"
            )
            assert not crit.requires_special_status, (
                f"Special-status scheme {r.scheme.id} should be excluded when special status is unknown"
            )


def test_general_open_student_excludes_gender_conflict(mahadbt_schemes):
    """General/Open student -> gender-specific scheme excluded when gender conflicts."""
    # Profile explicitly male
    profile_male = CitizenProfile(
        state="maharashtra",
        gender="male",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
    )
    results_male = match_schemes(profile_male, mahadbt_schemes)
    for r in results_male:
        crit = r.scheme.eligibility_criteria
        if crit and crit.gender:
            assert crit.gender != "female", f"Female-restricted scheme {r.scheme.id} matched male student"

    # Profile explicitly female
    profile_female = CitizenProfile(
        state="maharashtra",
        gender="female",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
    )
    results_female = match_schemes(profile_female, mahadbt_schemes)
    has_girls_scheme = any(
        r.scheme.eligibility_criteria and r.scheme.eligibility_criteria.gender == "female"
        for r in results_female
    )
    assert has_girls_scheme, "Female student should match female-specific open schemes"


def test_general_open_student_retains_rajarshi_panjabrao_ebc_schemes(mahadbt_schemes):
    """General/Open student -> Rajarshi/Panjabrao-type Open/EBC schemes remain eligible candidates."""
    profile = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
    )
    results = match_schemes(profile, mahadbt_schemes)
    result_names = [r.scheme.name["en"].lower() for r in results]

    # Must contain Rajarshi Chhatrapati Shahu Maharaj schemes
    assert any("rajarshi" in name for name in result_names)
    # Must contain Dr. Panjabrao Deshmukh schemes
    assert any("panjabrao" in name or "punjabrao" in name for name in result_names)
    # Must contain Open Merit scholarship
    assert any("open merit" in name for name in result_names)


def test_explicit_sc_student_receives_sc_specific_schemes(mahadbt_schemes):
    """Student with explicit SC category can still receive matching category-specific schemes."""
    profile_sc = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="sc",
        needs=["education", "scholarship"],
    )
    results_sc = match_schemes(profile_sc, mahadbt_schemes)
    sc_specific = [
        r for r in results_sc
        if r.scheme.eligibility_criteria and "sc" in (r.scheme.eligibility_criteria.social_categories or [])
    ]
    assert len(sc_specific) >= 3, "SC student should match multiple SC-specific schemes"


def test_unknown_social_category_does_not_exclude_reserved_schemes(mahadbt_schemes):
    """Unknown social category does not incorrectly exclude reserved-category schemes."""
    profile_unknown = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category=None,
        needs=["education", "scholarship"],
    )
    results_unknown = match_schemes(profile_unknown, mahadbt_schemes)

    # When social category is unknown, reserved schemes remain candidate schemes with missing_information noted
    reserved_matches = [
        r for r in results_unknown
        if r.scheme.eligibility_criteria
        and any(cat in {"sc", "st", "obc", "vjnt", "sbc"} for cat in (r.scheme.eligibility_criteria.social_categories or []))
    ]
    assert len(reserved_matches) > 0, "Unknown social category should retain reserved schemes as candidates"

    # Missing information must prompt for social category
    for r in reserved_matches:
        missing_text = " ".join(r.missing_information if isinstance(r.missing_information, list) else r.missing_information.get("en", []))
        assert "social category" in missing_text.lower()


def test_no_hardcoded_scheme_names():
    """Verify that neither eligibility_parser.py nor matching.py hardcode scheme names."""
    import inspect
    from services.web_scheme_discovery import eligibility_parser
    import app.matching as matching

    parser_src = inspect.getsource(eligibility_parser)
    matching_src = inspect.getsource(matching)

    forbidden_names = ["rajarshi", "panjabrao", "punjabrao", "shahu maharaj", "ladki bahin scholarship"]
    for name in forbidden_names:
        assert name not in parser_src.lower(), f"Found hardcoded scheme name '{name}' in eligibility_parser.py"
        assert name not in matching_src.lower(), f"Found hardcoded scheme name '{name}' in matching.py"


# ---------------------------------------------------------------------------
# 3. Granular Criteria Extraction & Ranking Tier Tests
# ---------------------------------------------------------------------------


def test_parser_extracts_granular_requirements_generically():
    """Verify generic extraction of hostel, institution, merit rank, min %, and course types."""
    # Hostel requirement
    crit_hostel = derive_eligibility_criteria(
        name="Hostel Allowance Scheme",
        eligibility_lines=["Applicant should be hosteller in government or private hostel."],
    )
    assert crit_hostel is not None
    assert crit_hostel.requires_hostel is True

    # Specific institution requirement
    crit_inst = derive_eligibility_criteria(
        name="University Research Scheme",
        eligibility_lines=["Maharashtrian students who studied in JNU."],
    )
    assert crit_inst is not None
    assert crit_inst.requires_specific_institution is True

    # Merit / board rank requirement
    crit_rank = derive_eligibility_criteria(
        name="Merit Scholarship",
        eligibility_lines=["Students from 11 & 12th class who gets top rank in secondary examinations."],
    )
    assert crit_rank is not None
    assert crit_rank.requires_merit_rank is True

    # Min percentage
    crit_pct = derive_eligibility_criteria(
        name="Merit Scholarship",
        eligibility_lines=["Applicant must secure a minimum of 60 percent marks in the SSC examination."],
    )
    assert crit_pct is not None
    assert crit_pct.min_percentage == 60.0

    # Male-only / boys restriction
    crit_boys = derive_eligibility_criteria(
        name="Boys Scholarship",
        eligibility_lines=["Invites applications from students for boys - only students of Class 11 and 12."],
    )
    assert crit_boys is not None
    assert crit_boys.gender == "male"

    # Education level & course types
    crit_med = derive_eligibility_criteria(
        name="Health Sciences Fee Reimbursement",
        eligibility_lines=["Students admitted for MBBS, BDS, BAMS in government aided colleges."],
    )
    assert crit_med is not None
    assert "medical" in (crit_med.course_types or [])
    assert "undergraduate" in (crit_med.education_level or [])


def test_confirmed_compatible_schemes_rank_highest(mahadbt_schemes):
    """Confirmed compatible schemes rank highest; unconfirmed prerequisites rank below."""
    profile = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
    )
    results = match_schemes(profile, mahadbt_schemes)

    # Top results must have higher score than schemes with unconfirmed heavy conditions
    top_score = results[0].relevance_score
    top_names = [r.scheme.name["en"].lower() for r in results if r.relevance_score == top_score]

    # Flagship confirmed Open/General schemes must be in top tier
    assert any("rajarshi" in name for name in top_names)
    assert any("open merit" in name for name in top_names)

    # Specific institution schemes must be excluded
    matched_names = [r.scheme.name["en"].lower() for r in results]
    assert not any("jawaharlal nehru university" in name for name in matched_names)
    assert not any("vidyaniketan" in name for name in matched_names)

    # Hostel schemes must rank strictly below the top tier
    for r in results:
        if r.scheme.eligibility_criteria and r.scheme.eligibility_criteria.requires_hostel:
            assert r.relevance_score < top_score, (
                f"Unconfirmed hostel scheme {r.scheme.id} should rank below confirmed matches"
            )


def test_unmet_known_conditions_excluded(mahadbt_schemes):
    """Schemes with known unmet conditions (hostel, education level, income) are excluded."""
    # Undergraduate day-scholar with 4L income
    profile = CitizenProfile(
        state="maharashtra",
        is_student=True,
        social_category="general",
        needs=["education", "scholarship"],
        education_level="undergraduate",
        is_hosteller=False,
        annual_income=400000.0,
    )
    results = match_schemes(profile, mahadbt_schemes)

    for r in results:
        crit = r.scheme.eligibility_criteria
        if crit:
            # Hostel schemes must be excluded for day-scholar
            assert crit.requires_hostel is not True, (
                f"Hostel scheme {r.scheme.id} should be excluded for confirmed day-scholar"
            )
            # Higher-secondary-only schemes must be excluded for undergraduate
            if crit.education_level:
                assert not (crit.education_level == ["higher_secondary"]), (
                    f"Junior college scheme {r.scheme.id} should be excluded for undergraduate"
                )
            # Postgraduate/doctorate-only schemes must be excluded for undergraduate
            if crit.education_level:
                assert not (set(crit.education_level) <= {"postgraduate", "doctorate"}), (
                    f"PG/Doctorate scheme {r.scheme.id} should be excluded for undergraduate"
                )

