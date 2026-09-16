from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from app.schemas import CitizenProfile, Scheme, SchemeMatchResult


class ConversationMessage(TypedDict):
    role: str
    content: str
    language: str


class AgentState(TypedDict, total=False):
    session_id: str
    input_text: str
    language: str
    language_hint: Optional[str]
    conversation_history: List[ConversationMessage]
    user_intent: Optional[str]
    extracted_user_info: Any
    user_profile: CitizenProfile
    location: Optional[str]
    occupation: Optional[str]
    age_group: Optional[str]
    gender: Optional[str]
    category: Optional[str]
    income_information: Optional[float]
    student_status: Optional[bool]
    farmer_status: Optional[bool]
    business_status: Optional[bool]
    land_information: Optional[bool]
    required_documents: List[str]
    retrieved_schemes: List[SchemeMatchResult]
    selected_scheme: Optional[Scheme]
    eligibility_information: Dict[str, Any]
    current_question: Optional[str]
    completed: bool
    response_text: str
    next_action: str
    last_updated: str


def new_agent_state(session_id: str) -> AgentState:
    return AgentState(
        session_id=session_id,
        language="en",
        conversation_history=[],
        user_intent=None,
        user_profile=CitizenProfile(),
        location=None,
        occupation=None,
        age_group=None,
        gender=None,
        category=None,
        income_information=None,
        student_status=None,
        farmer_status=None,
        business_status=None,
        land_information=None,
        required_documents=[],
        retrieved_schemes=[],
        selected_scheme=None,
        eligibility_information={},
        current_question=None,
        completed=False,
        response_text="",
        next_action="ask_question",
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
