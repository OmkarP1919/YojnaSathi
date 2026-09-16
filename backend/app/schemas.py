from typing import List
from pydantic import BaseModel


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
