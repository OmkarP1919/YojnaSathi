from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, computed_field

LocalizedString = Union[str, Dict[str, str]]
LocalizedList = Union[List[str], Dict[str, List[str]]]


class SchemeEligibilityCriteria(BaseModel):
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    income_max: Optional[float] = None
    gender: Optional[str] = None
    requires_farmer: Optional[bool] = None
    requires_land: Optional[bool] = None
    requires_student: Optional[bool] = None
    social_categories: Optional[List[str]] = None
    rural_or_urban: Optional[str] = None
    requires_no_pucca_house: Optional[bool] = None


class OnlineApplication(BaseModel):
    available: bool = False
    portal_name: Optional[str] = None
    portal_url: Optional[str] = None


class ApplicationLocation(BaseModel):
    id: str
    scheme_ids: List[str]
    categories: List[str] = Field(default_factory=list)
    state: str
    district: Optional[str] = None
    taluka: Optional[str] = None
    office_name: LocalizedString
    office_type: str
    address: LocalizedString
    contact_phone: Optional[str] = None
    working_hours: Optional[LocalizedString] = None
    source_url: Optional[str] = None
    scheme_authorization_url: Optional[str] = None
    application_method: str = "scheme_designated_application_center"


class OfflineApplication(BaseModel):
    available: bool = False
    authorized_channel: Optional[str] = None
    instructions: Optional[str] = None
    locations: List[ApplicationLocation] = Field(default_factory=list)


class ApplicationGuidance(BaseModel):
    documents_required: Optional[LocalizedList] = None
    online_application: OnlineApplication = Field(default_factory=OnlineApplication)
    offline_application: OfflineApplication = Field(default_factory=OfflineApplication)


class Scheme(BaseModel):
    id: str
    name: LocalizedString
    description: LocalizedString
    category: str
    target_groups: List[str]
    benefits: LocalizedList
    eligibility: LocalizedList
    required_information: LocalizedList
    state: str
    department: LocalizedString
    application_url: str
    source_url: str
    last_verified: str
    eligibility_criteria: Optional[SchemeEligibilityCriteria] = None
    custom_application_guidance: Optional[ApplicationGuidance] = Field(default=None, exclude=True)

    @computed_field(
        return_type=ApplicationGuidance,
        description=(
            "Application guidance derived only from the verified scheme data "
            "fields above. Never fabricates channels: offline stays unavailable "
            "until an offline channel is recorded in the scheme data."
        ),
    )
    @property
    def application_guidance(self) -> ApplicationGuidance:
        if self.custom_application_guidance is not None:
            return self.custom_application_guidance
        url = (self.application_url or "").strip()
        portal_name = None
        if url:
            host = url.split("//")[-1].split("/")[0].lower()
            if host.startswith("www."):
                host = host[len("www."):]
            portal_name = host or None
        return ApplicationGuidance(
            documents_required=self.required_information if self.required_information else None,
            online_application=OnlineApplication(
                available=bool(url),
                portal_name=portal_name,
                portal_url=url or None,
            ),
            offline_application=OfflineApplication(available=False),
        )


class SchemeListResponse(BaseModel):
    success: bool = True
    count: int
    schemes: List[Scheme]


class SingleSchemeResponse(BaseModel):
    success: bool = True
    scheme: Scheme


class ErrorResponse(BaseModel):
    success: bool = False
    error: str


class CitizenProfile(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    taluka: Optional[str] = None
    occupation: Optional[str] = None
    annual_income: Optional[float] = None
    is_student: Optional[bool] = None
    is_farmer: Optional[bool] = None
    marital_status: Optional[str] = None
    owns_land: Optional[bool] = None
    owns_house: Optional[bool] = None
    social_category: Optional[str] = None
    rural_or_urban: Optional[str] = None
    needs: Optional[List[str]] = None


class ReasonCodeItem(BaseModel):
    code: str
    params: Dict[str, Any] = Field(default_factory=dict)


class SchemeMatchResult(BaseModel):
    scheme: Scheme
    relevance_score: int
    matched_reasons: List[str]
    reason_codes: List[ReasonCodeItem] = Field(default_factory=list)
    missing_information: LocalizedList = Field(default_factory=list)
    locations: List[ApplicationLocation] = Field(default_factory=list)
    is_web_discovered: bool = False
    discovery_confidence: Optional[float] = None
    discovery_source_type: Optional[str] = None
    validation_reasons: List[str] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    profile: CitizenProfile = Field(default_factory=CitizenProfile)
    category: Optional[str] = None


DISCLAIMER_MAP = {
    "en": "These schemes are potentially relevant based on the information provided. Final eligibility is determined by the relevant government authority.",
    "hi": "ये योजनाएँ प्रदान की गई जानकारी के आधार पर संभावित रूप से प्रासंगिक हैं। अंतिम पात्रता संबंधित सरकारी प्राधिकरण द्वारा निर्धारित की जाती है।",
    "mr": "दिलेल्या माहितीच्या आधारे या योजना संभाव्यतः उपयुक्त असू शकतात. अंतिम पात्रता संबंधित सरकारी प्राधिकरणाद्वारे निश्चित केली जाते।"
}


class LocationRequirement(BaseModel):
    state_required_for_eligibility: bool = False
    has_physical_offices: bool = False
    next_needed_level: Optional[str] = None
    supported_districts: List[str] = Field(default_factory=list)
    supported_talukas: List[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    success: bool = True
    count: int
    disclaimer: Union[str, Dict[str, str]] = Field(default_factory=lambda: dict(DISCLAIMER_MAP))
    results: List[SchemeMatchResult]
    location_requirement: Optional[LocationRequirement] = None


class ApplicationOptionsResult(BaseModel):
    scheme_id: str
    state: str
    district: Optional[str] = None
    taluka: Optional[str] = None
    online_application: OnlineApplication = Field(default_factory=OnlineApplication)
    physical_locations: List[ApplicationLocation] = Field(default_factory=list)
    source_type: str = "none"  # "live_official_source" | "local_catalog_fallback" | "none"
    official_source_url: Optional[str] = None
    verification_status: str = "none"  # "live_verified" | "catalog_fallback" | "none"


class LocationDirectoryItem(BaseModel):
    name: str
    source_url: Optional[str] = None
    verified: bool = True


class StateDirectoryResponse(BaseModel):
    states: List[LocationDirectoryItem] = Field(default_factory=list)
    source_type: str = "authoritative_reference"
    available: bool = True
    message: Optional[str] = None


class DistrictDirectoryResponse(BaseModel):
    state: str
    districts: List[LocationDirectoryItem] = Field(default_factory=list)
    source_type: str = "official_government_portal"
    source_url: Optional[str] = None
    available: bool = True
    message: Optional[str] = None


class TalukaDirectoryResponse(BaseModel):
    state: str
    district: str
    talukas: List[LocationDirectoryItem] = Field(default_factory=list)
    source_type: str = "official_district_portal"
    source_url: Optional[str] = None
    available: bool = True
    message: Optional[str] = None


class ChatSchemeItem(BaseModel):
    id: str
    name: str
    relevance_score: int
    matched_reasons: List[str]
    missing_information: List[str]


class ChatRequest(BaseModel):
    message: str
    profile: Optional[CitizenProfile] = None


class ChatResponse(BaseModel):
    success: bool = True
    message: str
    profile: CitizenProfile
    needs_more_information: bool = False
    question: Optional[str] = None
    schemes: List[ChatSchemeItem] = Field(default_factory=list)
    disclaimer: str = (
        "These schemes are potentially relevant based on the information provided. "
        "Final eligibility is determined by the relevant government authority."
    )


class VoiceProcessRequest(BaseModel):
    session_id: str
    message: str = ""
    language: Optional[str] = None


class VoiceStartRequest(BaseModel):
    """Agent-first conversation start. A session ID is generated if omitted."""

    session_id: Optional[str] = None
    language: Optional[str] = None


class VoiceResetRequest(BaseModel):
    session_id: str
