from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

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


class RecommendationRequest(BaseModel):
    profile: CitizenProfile = Field(default_factory=CitizenProfile)
    category: Optional[str] = None


DISCLAIMER_MAP = {
    "en": "These schemes are potentially relevant based on the information provided. Final eligibility is determined by the relevant government authority.",
    "hi": "ये योजनाएँ प्रदान की गई जानकारी के आधार पर संभावित रूप से प्रासंगिक हैं। अंतिम पात्रता संबंधित सरकारी प्राधिकरण द्वारा निर्धारित की जाती है।",
    "mr": "दिलेल्या माहितीच्या आधारे या योजना संभाव्यतः उपयुक्त असू शकतात. अंतिम पात्रता संबंधित सरकारी प्राधिकरणाद्वारे निश्चित केली जाते।"
}


class RecommendationResponse(BaseModel):
    success: bool = True
    count: int
    disclaimer: Union[str, Dict[str, str]] = Field(default_factory=lambda: dict(DISCLAIMER_MAP))
    results: List[SchemeMatchResult]


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


class VoiceResetRequest(BaseModel):
    session_id: str
