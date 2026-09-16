from typing import List, Optional
from pydantic import BaseModel, Field


class Scheme(BaseModel):
    id: str
    name: str
    description: str
    category: str
    target_groups: List[str]
    benefits: List[str]
    eligibility: List[str]
    required_information: List[str]
    state: str
    department: str
    application_url: str
    source_url: str
    last_verified: str


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
    needs: Optional[List[str]] = None


class SchemeMatchResult(BaseModel):
    scheme: Scheme
    relevance_score: int
    matched_reasons: List[str]
    missing_information: List[str]


class RecommendationRequest(BaseModel):
    profile: CitizenProfile = Field(default_factory=CitizenProfile)


class RecommendationResponse(BaseModel):
    success: bool = True
    count: int
    disclaimer: str = (
        "These schemes are potentially relevant based on the information provided. "
        "Final eligibility is determined by the relevant government authority."
    )
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


