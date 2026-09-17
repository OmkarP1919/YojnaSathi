"""Unit tests for the DiscoveredScheme -> Scheme adapter and curated deduplication."""
import pytest
from app.main import load_schemes_data
from app.schemas import Scheme, SchemeMatchResult
from services.web_scheme_discovery.adapter import discovered_to_canonical_scheme
from services.web_scheme_discovery.deduplicator import is_duplicate_of_curated
from services.web_scheme_discovery.schemas import DiscoveredScheme


@pytest.fixture
def curated_schemes():
    """Load canonical schemes.json seed dataset."""
    return load_schemes_data()


def test_valid_discovered_scheme_converts_to_canonical_scheme():
    """Requirement A: Valid verified + active DiscoveredScheme converts cleanly."""
    cand = DiscoveredScheme(
        scheme_name="National Apprenticeship Promotion Scheme",
        normalized_name="national apprenticeship promotion",
        aliases=["NAPS"],
        scheme_type="central",
        government_level="central",
        state=None,
        description="A scheme to promote apprenticeship training across India.",
        benefits=["Stipend support of Rs 1500 per month paid directly."],
        eligibility=["Must be 15 years of age and completed basic education."],
        application_process=["Apply online at apprenticeshipindia.gov.in portal."],
        documents_required=["Aadhaar card", "Bank passbook", "Education mark sheet"],
        application_url="https://apprenticeshipindia.gov.in/",
        source_url="https://apprenticeshipindia.gov.in/",
        active_status="active",
        validation_status="verified",
        confidence=0.85,
    )

    scheme = discovered_to_canonical_scheme(cand)

    assert isinstance(scheme, Scheme)
    assert scheme.id.startswith("web-")
    assert "national-apprenticeship" in scheme.id
    assert scheme.name["en"] == "National Apprenticeship Promotion Scheme"
    assert scheme.application_url == "https://apprenticeshipindia.gov.in/"
    assert scheme.source_url == "https://apprenticeshipindia.gov.in/"
    assert scheme.application_guidance.online_application.available is True
    assert scheme.application_guidance.online_application.portal_name == "apprenticeshipindia.gov.in"


def test_missing_optional_fields_do_not_crash_conversion():
    """Requirement B: Missing optional fields fall back safely."""
    cand = DiscoveredScheme(
        scheme_name="State Youth Skill Program",
        normalized_name="state youth skill program",
        description=None,
        benefits=[],
        eligibility=[],
        documents_required=[],
        application_url=None,
        source_url="https://skill.gov.in",
        active_status="active",
        validation_status="verified",
    )

    scheme = discovered_to_canonical_scheme(cand)

    assert isinstance(scheme, Scheme)
    assert scheme.description["en"] == ""
    assert scheme.benefits["en"] == []
    assert scheme.eligibility == []
    assert scheme.required_information["en"] == []
    assert scheme.source_url == "https://skill.gov.in"
    assert scheme.state == "all-india"


def test_central_scheme_becomes_all_india():
    """Requirement C: Central scheme maps to state='all-india'."""
    cand = DiscoveredScheme(
        scheme_name="Central Skill Development Initiative",
        normalized_name="central skill development",
        scheme_type="central",
        government_level="central",
        state=None,
        active_status="active",
        validation_status="verified",
    )

    scheme = discovered_to_canonical_scheme(cand)
    assert scheme.state == "all-india"


def test_state_specific_scheme_preserves_normalized_state():
    """Requirement D: State-specific scheme preserves normalized lowercase state."""
    cand = DiscoveredScheme(
        scheme_name="Maharashtra Swadhar Yojana",
        normalized_name="maharashtra swadhar yojana",
        scheme_type="state",
        government_level="state",
        state="Maharashtra",
        active_status="active",
        validation_status="verified",
    )

    scheme = discovered_to_canonical_scheme(cand)
    assert scheme.state == "maharashtra"


def test_explicit_evidence_mapped_to_target_groups_and_category():
    """Requirement E: Evidence keywords map to target_groups and category."""
    # 1. Farmer evidence
    farmer_cand = DiscoveredScheme(
        scheme_name="State Kisan Krishi Sahayata",
        normalized_name="state kisan krishi sahayata",
        benefits=["Financial assistance for small and marginal farmers buying seeds."],
        eligibility=["Cultivators with agricultural landholding."],
        active_status="active",
        validation_status="verified",
    )
    farmer_scheme = discovered_to_canonical_scheme(farmer_cand)
    assert farmer_scheme.category == "agriculture"
    assert "farmers" in farmer_scheme.target_groups
    assert "rural citizens" in farmer_scheme.target_groups

    # 2. Student evidence
    student_cand = DiscoveredScheme(
        scheme_name="Post-Matric Scholarship for Backward Classes",
        normalized_name="post matric scholarship backward classes",
        benefits=["College tuition assistance and scholarship."],
        eligibility=["Regular students enrolled in recognized universities."],
        active_status="active",
        validation_status="verified",
    )
    student_scheme = discovered_to_canonical_scheme(student_cand)
    assert student_scheme.category == "education"
    assert "students" in student_scheme.target_groups

    # 3. Women evidence
    women_cand = DiscoveredScheme(
        scheme_name="Kanya Utthan Protsahan",
        normalized_name="kanya utthan protsahan",
        benefits=["Incentive for girl child education and mother healthcare."],
        eligibility=["Female resident of state."],
        active_status="active",
        validation_status="verified",
    )
    women_scheme = discovered_to_canonical_scheme(women_cand)
    assert women_scheme.category == "women"
    assert "women" in women_scheme.target_groups


def test_no_unsupported_eligibility_criteria_fabricated():
    """Requirement F: eligibility_criteria remains None (never fabricated)."""
    cand = DiscoveredScheme(
        scheme_name="Test Citizen Welfare",
        normalized_name="test citizen welfare",
        benefits=["Grant of Rs 5000"],
        eligibility=["Must have income below Rs 200000 and age 18 to 40"],
        active_status="active",
        validation_status="verified",
    )

    scheme = discovered_to_canonical_scheme(cand)
    # The adapter MUST NOT guess or fabricate structured numeric boundaries
    assert scheme.eligibility_criteria is None


def test_unverified_or_inactive_candidate_rejected_by_adapter():
    """Safety Gate: Adapter refuses unverified or inactive candidates."""
    unverified = DiscoveredScheme(
        scheme_name="Unverified Scheme",
        active_status="active",
        validation_status="partially_verified",
    )
    with pytest.raises(ValueError, match="Only verified and active"):
        discovered_to_canonical_scheme(unverified)

    inactive = DiscoveredScheme(
        scheme_name="Closed Scheme",
        active_status="inactive",
        validation_status="verified",
    )
    with pytest.raises(ValueError, match="Only verified and active"):
        discovered_to_canonical_scheme(inactive)


def test_pm_kisan_candidate_recognized_as_duplicate(curated_schemes):
    """Requirement G: PM-KISAN candidate is recognized as duplicate of curated schemes."""
    cand = DiscoveredScheme(
        scheme_name="Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
        normalized_name="pmkisan",
        application_url="https://pmkisan.gov.in/",
        source_url="https://pmkisan.gov.in/",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand, curated_schemes) is True

    # Check variation in name
    cand2 = DiscoveredScheme(
        scheme_name="PM Kisan Samman Nidhi Yojana",
        normalized_name="pm kisan samman nidhi",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand2, curated_schemes) is True


def test_majhi_ladki_bahin_candidate_recognized_as_duplicate(curated_schemes):
    """Requirement H: Majhi Ladki Bahin candidate is recognized as duplicate."""
    cand = DiscoveredScheme(
        scheme_name="Mukhyamantri Majhi Ladki Bahin Yojana",
        normalized_name="majhi ladki bahin",
        application_url="https://ladakibahin.maharashtra.gov.in/",
        source_url="https://ladakibahin.maharashtra.gov.in/",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand, curated_schemes) is True

    # Short alias
    cand2 = DiscoveredScheme(
        scheme_name="Ladki Bahin Yojana",
        normalized_name="ladki bahin",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand2, curated_schemes) is True


def test_genuinely_new_scheme_not_marked_duplicate(curated_schemes):
    """Requirement I: A genuinely new scheme is NOT marked duplicate."""
    cand = DiscoveredScheme(
        scheme_name="Maharashtra Swadhar Yojana",
        normalized_name="maharashtra swadhar",
        application_url="https://sjsa.maharashtra.gov.in/swadhar",
        source_url="https://sjsa.maharashtra.gov.in/swadhar",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand, curated_schemes) is False

    cand2 = DiscoveredScheme(
        scheme_name="PM Vishwakarma Kaushal Samman",
        normalized_name="pm vishwakarma",
        application_url="https://pmvishwakarma.gov.in/",
        source_url="https://pmvishwakarma.gov.in/",
        active_status="active",
        validation_status="verified",
    )
    assert is_duplicate_of_curated(cand2, curated_schemes) is False


def test_discovery_metadata_on_scheme_match_result():
    """Requirement J: Discovery metadata can be attached to SchemeMatchResult."""
    # 1. Default curated match result
    curated = load_schemes_data()[0]
    res_curated = SchemeMatchResult(
        scheme=curated,
        relevance_score=8,
        matched_reasons=["Matches farming"],
    )
    assert res_curated.is_web_discovered is False
    assert res_curated.discovery_confidence is None
    assert res_curated.discovery_source_type is None
    assert res_curated.validation_reasons == []

    # 2. Web-discovered match result with provenance
    cand = DiscoveredScheme(
        scheme_name="New Central Skill Initiative",
        normalized_name="new central skill",
        benefits=["Free skill training"],
        eligibility=["Youth 18-35"],
        active_status="active",
        validation_status="verified",
        confidence=0.88,
        source_type="official_government",
        validation_reasons=["Official government source found", "Benefits information present"],
    )
    scheme = discovered_to_canonical_scheme(cand)

    res_discovered = SchemeMatchResult(
        scheme=scheme,
        relevance_score=6,
        matched_reasons=["Relevant for students and youth"],
        is_web_discovered=True,
        discovery_confidence=cand.confidence,
        discovery_source_type=cand.source_type,
        validation_reasons=cand.validation_reasons,
    )
    assert res_discovered.is_web_discovered is True
    assert res_discovered.discovery_confidence == 0.88
    assert res_discovered.discovery_source_type == "official_government"
    assert len(res_discovered.validation_reasons) == 2
