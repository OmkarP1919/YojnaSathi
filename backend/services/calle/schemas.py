from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import SchemeMatchResult


class CitizenCallProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    language: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    farmer: Optional[bool] = None
    student: Optional[bool] = None
    annual_income: Optional[str] = None
    social_category: Optional[str] = None
    disability: Optional[bool] = None
    need: Optional[str] = None
    specific_need: Optional[str] = None


class CalleCallRequest(BaseModel):
    phone_number: str
    language: Optional[str] = None
    initial_context: Optional[Dict[str, Any]] = None


class CalleCallResponse(BaseModel):
    success: bool = True
    call_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    provider_response: Optional[Dict[str, Any]] = None


class CalleCallStatus(BaseModel):
    call_id: str
    status: Optional[str] = None
    task: Optional[str] = None
    summary: Optional[str] = None
    task_completed: Optional[bool] = None
    completion_confidence: Optional[Dict[str, Any]] = None
    structured_result: Optional[Dict[str, Any]] = None
    raw_response: Optional[Dict[str, Any]] = None
    matched_schemes: List[SchemeMatchResult] = Field(default_factory=list)


class CalleWebhookEvent(BaseModel):
    id: str
    type: str
    created_at: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def call_id(self) -> Optional[str]:
        return (self.data or {}).get("id")
