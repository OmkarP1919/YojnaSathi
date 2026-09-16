from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from langgraph.graph import END, StateGraph

from app.matching import match_schemes
from app.schemas import CitizenProfile, Scheme, SchemeMatchResult
from services.voice_agent.extractor import ExtractedUserInfo, ProfileExtractor
from services.voice_agent.graph_compat import detect_language_fallback
from services.voice_agent.state import AgentState

logger = logging.getLogger("yojnasathi.voice_agent")


def detect_language(
    text: str,
    client_hint: Optional[str] = None,
    session_lang: Optional[str] = None,
) -> str:
    return detect_language_fallback(text, client_hint=client_hint, session_lang=session_lang)


async def understand_input(state: AgentState, extractor: ProfileExtractor) -> AgentState:
    text = state.get("input_text", "")
    client_hint = state.get("language_hint")
    session_lang = state.get("language")
    language = detect_language(text, client_hint=client_hint, session_lang=session_lang)
    state["language"] = language
    if "conversation_history" not in state or state["conversation_history"] is None:
        state["conversation_history"] = []
    state["conversation_history"].append({"role": "user", "content": text, "language": language})
    state["extracted_user_info"] = await extractor.extract(
        text,
        current_profile=state["user_profile"].model_dump(exclude_none=True),
        current_question=state.get("current_question"),
    )
    return state


def update_user_profile(state: AgentState) -> AgentState:
    extracted: ExtractedUserInfo = state.get("extracted_user_info", ExtractedUserInfo())
    profile = state["user_profile"]
    values = extracted.model_dump(exclude_none=True)
    intent_category = extracted.category or extracted.intent
    if intent_category and intent_category != "find_schemes":
        values["needs"] = sorted(set(profile.needs or []) | {intent_category})
    values.pop("intent", None)
    values.pop("category", None)
    values.pop("language", None)
    values.pop("confidence", None)
    values.pop("source", None)
    values.pop("is_business", None)
    if values:
        state["user_profile"] = profile.model_copy(update=values)
    if extracted.intent and extracted.intent != "find_schemes":
        state["user_intent"] = extracted.intent
    if extracted.category:
        state["category"] = extracted.category
        state["user_intent"] = extracted.category
    state["location"] = state["user_profile"].state
    state["occupation"] = state["user_profile"].occupation
    state["age_group"] = str(state["user_profile"].age) if state["user_profile"].age is not None else None
    state["gender"] = state["user_profile"].gender
    state["income_information"] = state["user_profile"].annual_income
    state["student_status"] = state["user_profile"].is_student
    state["farmer_status"] = state["user_profile"].is_farmer
    state["business_status"] = extracted.is_business
    state["land_information"] = state["user_profile"].owns_land
    logger.info("PROFILE UPDATED: %s", state["user_profile"].model_dump(exclude_none=True))
    return state


def determine_missing_information(state: AgentState) -> AgentState:
    profile = state["user_profile"]
    category = state.get("category") or state.get("user_intent")

    if not category:
        state["current_question"] = "need"
    elif not profile.state:
        state["current_question"] = "state"
    elif (category in {"agriculture", "farmer", "farming"} or profile.is_farmer is True) and profile.owns_land is None:
        state["current_question"] = "owns_land"
    elif (category in {"education", "student", "scholarship"} or profile.is_student is True) and profile.social_category is None:
        state["current_question"] = "social_category"
    elif category == "housing" and profile.rural_or_urban is None:
        state["current_question"] = "rural_or_urban"
    elif category == "housing" and profile.owns_house is None:
        state["current_question"] = "owns_house"
    else:
        state["current_question"] = None
    return state


def retrieve_schemes(state: AgentState, schemes: List[Scheme]) -> AgentState:
    if state.get("current_question"):
        return state
    category = state.get("category") or state.get("user_intent")
    state["retrieved_schemes"] = match_schemes(
        state["user_profile"],
        schemes,
        category=category,
    )[:3]
    logger.info(
        "MATCHING RESULT: %s",
        [
            {"scheme_id": result.scheme.id, "score": result.relevance_score}
            for result in state["retrieved_schemes"]
        ],
    )
    return state


def check_eligibility(state: AgentState) -> AgentState:
    state["eligibility_information"] = {
        result.scheme.id: {
            "relevance_score": result.relevance_score,
            "matched_reasons": result.matched_reasons,
            "missing_information": result.missing_information,
        }
        for result in state.get("retrieved_schemes", [])
    }
    return state


def _get_localized_text(field: Any, language: str) -> str:
    if not field:
        return ""
    if isinstance(field, dict):
        return field.get(language) or field.get("en") or field.get("hi") or field.get("mr") or ""
    return str(field)


def _get_localized_benefit(benefits: Any, language: str) -> str:
    if not benefits:
        return ""
    if isinstance(benefits, dict):
        b_list = benefits.get(language) or benefits.get("en") or benefits.get("hi") or benefits.get("mr") or []
        return b_list[0] if b_list else ""
    if isinstance(benefits, list):
        return str(benefits[0]) if benefits else ""
    return str(benefits)


def _scheme_summary(result: SchemeMatchResult, language: str) -> str:
    scheme = result.scheme
    name = _get_localized_text(scheme.name, language)
    benefit = _get_localized_benefit(scheme.benefits, language) or _get_localized_text(scheme.description, language)
    return f"{name} — {benefit}"


def generate_response(state: AgentState) -> AgentState:
    language = state.get("language", "en")
    if language not in {"en", "hi", "mr"}:
        language = "en"
    question = state.get("current_question")
    if question == "need":
        messages = {
            "mr": "तुम्हाला कोणत्या प्रकारच्या योजनेची गरज आहे? शेती, शिक्षण, आरोग्य किंवा घरासाठी?",
            "hi": "आपको किस तरह की योजना चाहिए? खेती, पढ़ाई, इलाज या घर के लिए?",
            "en": "What kind of scheme do you need: farming, education, health, or housing?",
        }
        state["response_text"] = messages[language]
    elif question == "state":
        messages = {
            "mr": "तुम्ही कोणत्या राज्यात राहता?",
            "hi": "आप किस राज्य में रहते हैं?",
            "en": "Which state do you live in?",
        }
        state["response_text"] = messages[language]
    elif question == "owns_land":
        messages = {
            "mr": "तुमच्या नावावर शेतीची जमीन आहे का?",
            "hi": "क्या आपके नाम पर खेती की जमीन है?",
            "en": "Do you own agricultural land?",
        }
        state["response_text"] = messages[language]
    elif question == "social_category":
        messages = {
            "mr": "तुम्ही कोणत्या सामाजिक प्रवर्गात मोडता: खुला (General), अनुसूचित जाती (SC), अनुसूचित जमाती (ST), इतर मागासवर्गीय (OBC), ईबीसी (EBC), किंवा डीएनटी (DNT)?",
            "hi": "आप किस सामाजिक वर्ग में आते हैं: सामान्य (General), अनुसूचित जाति (SC), अनुसूचित जनजाति (ST), अन्य पिछड़ा वर्ग (OBC), ईबीसी (EBC), या डीएनटी (DNT)?",
            "en": "Which social category do you belong to: General, SC, ST, OBC, EBC, or DNT?",
        }
        state["response_text"] = messages[language]
    elif question == "rural_or_urban":
        messages = {
            "mr": "तुम्ही ग्रामीण भागात राहता की शहरी भागात?",
            "hi": "आप ग्रामीण क्षेत्र में रहते हैं या शहरी क्षेत्र में?",
            "en": "Do you reside in a rural village or an urban city area?",
        }
        state["response_text"] = messages[language]
    elif question == "owns_house":
        messages = {
            "mr": "तुमच्याकडे स्वतःचे पक्के घर आहे का?",
            "hi": "क्या आपके पास अपना पक्का मकान है?",
            "en": "Do you or your family own a permanent pucca house?",
        }
        state["response_text"] = messages[language]
    elif not state.get("retrieved_schemes"):
        messages = {
            "mr": "उपलब्ध सरकारी योजनांमध्ये तुमच्यासाठी थेट जुळणारी योजना सापडली नाही.",
            "hi": "उपलब्ध सरकारी योजनाओं में आपके लिए सीधे मेल खाती कोई योजना नहीं मिली।",
            "en": "No suitable scheme was found in the available government scheme data.",
        }
        state["response_text"] = messages[language]
        state["next_action"] = "completed"
        state["completed"] = True
    else:
        results = state["retrieved_schemes"]
        intro = {
            "mr": f"तुमच्यासाठी {len(results)} उपयुक्त योजना सापडल्या.",
            "hi": f"आपके लिए {len(results)} उपयुक्त योजनाएं मिलीं।",
            "en": f"I found {len(results)} potentially relevant schemes for you.",
        }[language]
        lines = [intro]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {_scheme_summary(result, language)}")
        lines.append({
            "mr": "अंतिम पात्रता संबंधित सरकारी कार्यालयाच्या नियमांनुसार तपासा.",
            "hi": "अंतिम पात्रता संबंधित सरकारी नियमों के अनुसार जांचें।",
            "en": "Please confirm final eligibility with the relevant government authority.",
        }[language])
        state["response_text"] = "\n".join(lines)
        state["next_action"] = "completed"
        state["completed"] = True

    if question:
        state["next_action"] = "ask_question"
    if "conversation_history" not in state or state["conversation_history"] is None:
        state["conversation_history"] = []
    state["conversation_history"].append({"role": "assistant", "content": state["response_text"], "language": language})
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    return state


def build_graph(schemes: List[Scheme], extractor: Optional[ProfileExtractor] = None):
    extractor = extractor or ProfileExtractor()

    async def understand_node(state: AgentState) -> AgentState:
        return await understand_input(state, extractor)

    workflow = StateGraph(AgentState)
    workflow.add_node("understand_input", understand_node)
    workflow.add_node("update_user_profile", update_user_profile)
    workflow.add_node("determine_missing_information", determine_missing_information)
    workflow.add_node("retrieve_schemes", lambda state: retrieve_schemes(state, schemes))
    workflow.add_node("check_eligibility", check_eligibility)
    workflow.add_node("generate_response", generate_response)
    workflow.set_entry_point("understand_input")
    workflow.add_edge("understand_input", "update_user_profile")
    workflow.add_edge("update_user_profile", "determine_missing_information")
    workflow.add_edge("determine_missing_information", "retrieve_schemes")
    workflow.add_edge("retrieve_schemes", "check_eligibility")
    workflow.add_edge("check_eligibility", "generate_response")
    workflow.add_edge("generate_response", END)
    return workflow.compile()
