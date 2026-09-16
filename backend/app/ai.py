"""
AI service module for YojnaSathi using LangChain and Google Gemini.

Responsible for:
1. Extracting structured CitizenProfile from citizen natural-language input.
2. Merging new profile information with existing profile without overwriting
   non-null values with null values.
3. Generating citizen-friendly, grounded explanations based solely on verified
   scheme facts from matching results.
4. Generating concise clarifying follow-up questions when input is too vague.
"""
import os
import re
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import HTTPException, status
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.schemas import (
    CitizenProfile,
    ChatResponse,
    ChatSchemeItem,
    Scheme,
    SchemeMatchResult,
)
from app.matching import match_schemes

# Load environment variables
load_dotenv()


class GeminiConfigurationError(Exception):
    """Raised when the Gemini API key or configuration is missing or invalid."""
    pass


def get_gemini_api_key() -> str:
    """
    Retrieve Gemini API key from environment, checking GEMINI_API_KEY
    and falling back to GOOGLE_API_KEY.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or not api_key.strip() or api_key.strip() == "your_gemini_api_key_here":
        raise GeminiConfigurationError(
            "Gemini API key is not configured. Please set GEMINI_API_KEY in your environment or .env file."
        )
    return api_key.strip()


def get_gemini_model_name() -> str:
    """Retrieve Gemini model name from environment, defaulting to gemini-2.5-flash."""
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()


def get_chat_model(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """Instantiate and return ChatGoogleGenerativeAI using configured model and key."""
    api_key = get_gemini_api_key()
    model_name = get_gemini_model_name()
    return ChatGoogleGenerativeAI(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
    )


def merge_profiles(
    existing: Optional[CitizenProfile],
    new_extracted: CitizenProfile,
) -> CitizenProfile:
    """
    Merges newly extracted profile data into an existing profile.
    
    Correction 2 Rule:
    Profile merging MUST NOT overwrite existing non-null profile values with
    null values returned by Gemini.
    If the user explicitly stated a new non-null value, it updates the field.
    Needs lists are merged without duplicates.
    """
    if existing is None:
        return new_extracted

    merged_data = {}
    scalar_fields = [
        "age",
        "gender",
        "state",
        "occupation",
        "annual_income",
        "is_student",
        "is_farmer",
        "marital_status",
        "owns_land",
        "owns_house",
    ]

    for field in scalar_fields:
        new_val = getattr(new_extracted, field)
        existing_val = getattr(existing, field)
        if new_val is not None:
            merged_data[field] = new_val
        else:
            merged_data[field] = existing_val

    # Handle needs merging
    existing_needs = existing.needs or []
    new_needs = new_extracted.needs or []
    if not existing_needs and not new_needs:
        merged_data["needs"] = None
    else:
        # Merge preserving order, case-insensitive deduplication
        seen = set()
        merged_needs = []
        for item in existing_needs + new_needs:
            if item and isinstance(item, str) and item.strip():
                clean = item.strip()
                lower_key = clean.lower()
                if lower_key not in seen:
                    seen.add(lower_key)
                    merged_needs.append(clean)
        merged_data["needs"] = merged_needs if merged_needs else None

    return CitizenProfile(**merged_data)


EXTRACTION_SYSTEM_PROMPT = """You are an expert profile extraction assistant for YojnaSathi, an Indian government welfare schemes platform.
Your task is to extract structured citizen profile attributes from the user's message.

STRICT EXTRACTION RULES:
1. Extract ONLY facts that are explicitly stated or strongly implied by the user's message.
2. Do NOT guess, assume, or fabricate any missing information. If a field is not mentioned, leave it as null.
3. For 'state', normalize the Indian state name to lowercase (e.g., 'maharashtra', 'bihar', 'gujarat').
4. For 'gender', normalize to 'female', 'male', or null.
5. If the user mentions they are a farmer, cultivate crops, or work in agriculture: set 'is_farmer' to true, and 'occupation' to 'farmer'.
6. If the user mentions they are a student or studying: set 'is_student' to true, and 'occupation' to 'student'.
7. For 'needs', extract a list of specific needs, assistance, or benefits requested by the user in lowercase (e.g., ['crop insurance'], ['scholarship'], ['financial assistance'], ['health treatment'], ['housing'], ['loan']).
8. For 'age' and 'annual_income', extract exact numerical values if specified.
"""


def extract_profile(
    message: str,
    existing_profile: Optional[CitizenProfile] = None,
) -> CitizenProfile:
    """
    Extracts structured CitizenProfile from natural-language message using Gemini
    and merges it with any existing profile without overwriting non-null values with nulls.
    """
    if not message or not message.strip():
        return existing_profile or CitizenProfile()

    llm = get_chat_model(temperature=0.0)
    structured_extractor = llm.with_structured_output(CitizenProfile)

    messages = [
        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=message.strip()),
    ]

    try:
        extracted: CitizenProfile = structured_extractor.invoke(messages)
    except GeminiConfigurationError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI profile extraction service error: {str(e)}",
        )

    return merge_profiles(existing_profile, extracted)


EXPLANATION_SYSTEM_PROMPT = """You are YojnaSathi's empathetic and helpful citizen welfare advisor.
Your objective is to provide a clear, concise, citizen-friendly explanation of why the supplied government schemes may be relevant to the citizen.

CRITICAL GROUNDING AND SAFETY RULES:
1. Use ONLY the supplied scheme facts below. Do NOT use outside knowledge or extrapolate.
2. Do NOT invent benefits, eligibility criteria, application URLs, or departments.
3. If a fact is not supplied in the scheme data, DO NOT state it.
4. NEVER claim final or confirmed eligibility. Do NOT use phrases such as:
   - "You are eligible"
   - "Eligibility confirmed"
   - "You qualify"
   Instead use phrasing such as:
   - "Based on the information you provided, these schemes may be relevant to you:"
   - "You may be interested in the following schemes:"
   - "These programs offer support for..."
5. Explain WHY each scheme is potentially relevant using the provided matched reasons.
6. Mention the official application link or portal provided in the scheme data so the citizen knows where to apply.
7. Note any required documents or missing details from the scheme's required information.
8. State clearly that final eligibility is determined solely by the relevant government authority.
9. Keep the explanation warm, simple, and easy to read. Avoid dense bureaucratic jargon.
"""


def _format_schemes_context(matched_results: List[SchemeMatchResult]) -> str:
    """Formats verified scheme facts for grounded generation context."""
    lines = []
    for idx, item in enumerate(matched_results, 1):
        s = item.scheme
        lines.append(f"Scheme {idx}: {s.name} (ID: {s.id})")
        lines.append(f"- Category: {s.category}")
        lines.append(f"- State: {s.state}")
        lines.append(f"- Department: {s.department}")
        lines.append(f"- Key Benefits: {'; '.join(s.benefits)}")
        lines.append(f"- Eligibility Guidelines: {'; '.join(s.eligibility)}")
        lines.append(f"- Application URL: {s.application_url}")
        lines.append(f"- Why it matched your profile: {'; '.join(item.matched_reasons)}")
        lines.append(f"- Documents/Information needed: {'; '.join(item.missing_information)}")
        lines.append("")
    return "\n".join(lines)


def _enforce_safety_phrasing(text: str) -> str:
    """Guarantees strict absence of eligibility commitment phrases."""
    prohibited = [
        (re.compile(r"\byou are eligible\b", re.IGNORECASE), "these schemes may be relevant to you"),
        (re.compile(r"\beligibility confirmed\b", re.IGNORECASE), "potential relevance identified"),
        (re.compile(r"\byou qualify\b", re.IGNORECASE), "you may meet the preliminary criteria"),
    ]
    sanitized = text
    for pattern, replacement in prohibited:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def generate_chat_explanation(
    user_message: str,
    profile: CitizenProfile,
    matched_results: List[SchemeMatchResult],
) -> str:
    """
    Generates a citizen-friendly explanation strictly grounded in supplied scheme facts.
    """
    llm = get_chat_model(temperature=0.2)
    schemes_context = _format_schemes_context(matched_results)

    user_prompt = f"""Citizen query: "{user_message}"

Citizen Profile:
- State: {profile.state or 'Not specified'}
- Occupation: {profile.occupation or 'Not specified'}
- Needs: {', '.join(profile.needs) if profile.needs else 'Not specified'}
- Farmer status: {profile.is_farmer}
- Student status: {profile.is_student}
- Age: {profile.age or 'Not specified'}
- Gender: {profile.gender or 'Not specified'}

VERIFIED SCHEME FACTS (Use ONLY these facts; do NOT invent anything):
{schemes_context}

Please provide a warm, citizen-friendly explanation of these potentially relevant schemes."""

    try:
        response = llm.invoke([
            SystemMessage(content=EXPLANATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        return _enforce_safety_phrasing(content)
    except GeminiConfigurationError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI explanation generation error: {str(e)}",
        )


FOLLOWUP_SYSTEM_PROMPT = """You are YojnaSathi's empathetic citizen welfare assistant.
The citizen's query is too broad, vague, or minimal to identify specific government schemes (for example, they asked for 'government help' without specifying a category, state, or occupation).

RULES:
1. Politely ask a concise, welcoming clarifying question to narrow down their search.
2. Ask if they are seeking assistance for farming/agriculture, education/scholarship, healthcare, housing, employment, or small business/financial support.
3. Do NOT ask for every profile field at once. Keep the question focused and easy to answer.
4. Do NOT invent or assume any facts about the citizen.
5. Keep your response brief (1-3 sentences).
"""


def generate_followup_question(
    user_message: str,
    profile: CitizenProfile,
) -> str:
    """
    Generates a concise clarifying question when the profile lacks actionable signals.
    """
    llm = get_chat_model(temperature=0.2)

    user_prompt = f"""Citizen query: "{user_message}"
Current Profile: {profile.model_dump(exclude_none=True)}

Please ask a concise follow-up question to help identify relevant welfare categories."""

    try:
        response = llm.invoke([
            SystemMessage(content=FOLLOWUP_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        return _enforce_safety_phrasing(content.strip())
    except GeminiConfigurationError:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI follow-up question generation error: {str(e)}",
        )


def process_chat_message(
    message: str,
    profile: Optional[CitizenProfile] = None,
    schemes: Optional[List[Scheme]] = None,
) -> ChatResponse:
    """
    High-level chat orchestration service:
    1. Validates non-empty message and Gemini API key.
    2. Extracts/updates CitizenProfile with Gemini.
    3. Runs deterministic match_schemes().
    4. If no schemes match, generates a helpful follow-up question.
    5. If schemes match, generates grounded explanation using verified scheme facts.
    6. Returns validated ChatResponse.
    """
    if not message or not message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty",
        )

    # Validate Gemini API configuration early
    try:
        get_gemini_api_key()
    except GeminiConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    # 1. Extract and update profile
    updated_profile = extract_profile(message.strip(), existing_profile=profile)

    # 2. Load schemes if not provided
    if schemes is None:
        from app.main import load_schemes_data
        schemes = load_schemes_data()

    # 3. Deterministic matching engine decides candidates
    matched_results = match_schemes(updated_profile, schemes)

    # 4. Handle follow-up vs explanation
    if not matched_results:
        question = generate_followup_question(message.strip(), updated_profile)
        return ChatResponse(
            success=True,
            message=question,
            profile=updated_profile,
            needs_more_information=True,
            question=question,
            schemes=[],
            disclaimer=(
                "These schemes are potentially relevant based on the information provided. "
                "Final eligibility is determined by the relevant government authority."
            ),
        )

    # Schemes matched: generate grounded natural language explanation
    explanation = generate_chat_explanation(
        message.strip(),
        updated_profile,
        matched_results[:3],  # Ground top candidate schemes
    )

    chat_scheme_items = [
        ChatSchemeItem(
            id=res.scheme.id,
            name=res.scheme.name,
            relevance_score=res.relevance_score,
            matched_reasons=res.matched_reasons,
            missing_information=res.missing_information,
        )
        for res in matched_results
    ]

    return ChatResponse(
        success=True,
        message=explanation,
        profile=updated_profile,
        needs_more_information=False,
        question=None,
        schemes=chat_scheme_items,
        disclaimer=(
            "These schemes are potentially relevant based on the information provided. "
            "Final eligibility is determined by the relevant government authority."
        ),
    )
