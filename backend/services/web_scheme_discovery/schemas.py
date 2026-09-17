"""Pydantic schemas for the web-scheme-discovery pipeline.

Confidence means: "confidence that the discovered scheme information is
sufficiently supported by evidence" — it NEVER means probability of
citizen eligibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WebDiscoveryProfile(BaseModel):
    """Permissive citizen profile for web discovery.

    All fields optional so the endpoint never rejects a profile that the
    local matcher would accept. Unknown extra fields are ignored.
    """

    model_config = {"extra": "ignore"}

    language: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    farmer: Optional[bool] = None
    student: Optional[bool] = None
    annual_income: Optional[float] = None
    social_category: Optional[str] = None
    disability: Optional[bool] = None
    need: Optional[str] = None
    specific_need: Optional[str] = None


class TavilyResultItem(BaseModel):
    model_config = {"extra": "ignore"}

    title: str = ""
    url: str = ""
    content: str = ""
    score: float = 0.0


class EvidenceItem(BaseModel):
    field: str
    source_url: str
    evidence: str = Field(max_length=500)


class ValidationResult(BaseModel):
    validation_status: Literal["verified", "partially_verified", "rejected"]
    reasons: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    active_status: Literal["active", "inactive", "unknown"] = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiscoveredScheme(BaseModel):
    scheme_name: str
    normalized_name: str = ""
    aliases: List[str] = Field(default_factory=list)
    scheme_type: Optional[Literal["central", "state"]] = None
    government_level: Optional[Literal["central", "state"]] = None
    state: Optional[str] = None
    description: Optional[str] = None
    benefits: List[str] = Field(default_factory=list)
    eligibility: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    application_process: List[str] = Field(default_factory=list)
    documents_required: List[str] = Field(default_factory=list)
    application_url: Optional[str] = None
    source_url: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list)
    source_type: str = "secondary"
    active_status: Literal["active", "inactive", "unknown"] = "unknown"
    validation_status: Literal["verified", "partially_verified", "rejected"] = "rejected"
    validation_reasons: List[str] = Field(default_factory=list)
    last_verified: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class WebSchemeSearchRequest(BaseModel):
    model_config = {"extra": "ignore"}

    profile: WebDiscoveryProfile = Field(default_factory=WebDiscoveryProfile)
    # Optional per-request overrides (bounded by service for safety).
    max_candidates: Optional[int] = None


class SearchMetadata(BaseModel):
    queries_used: int = 0
    queries: List[str] = Field(default_factory=list)
    candidates_found: int = 0
    candidates_validated: int = 0
    candidates_rejected: int = 0
    elapsed_seconds: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cache_hit: bool = False


class WebSchemeSearchResponse(BaseModel):
    status: Literal["success", "partial", "empty"] = "success"
    query_summary: str = ""
    validated_schemes: List[DiscoveredScheme] = Field(default_factory=list)
    rejected_candidates: List[DiscoveredScheme] = Field(default_factory=list)
    metadata: SearchMetadata = Field(default_factory=SearchMetadata)
    errors: List[str] = Field(default_factory=list)


class DiscoveryMetadata(BaseModel):
    model_config = {"extra": "ignore"}

    is_web_discovered: bool = True
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    validation_reasons: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None


class MergerInput(BaseModel):
    """Clean interface reserved for the FUTURE merger (not implemented)."""

    local_matches: List[Dict[str, Any]] = Field(default_factory=list)
    web_matches: List[DiscoveredScheme] = Field(default_factory=list)
    citizen_profile: Dict[str, Any] = Field(default_factory=dict)
