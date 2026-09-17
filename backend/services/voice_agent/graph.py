from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from langgraph.graph import END, StateGraph

from app.matching import AGE_BOUNDS, CATEGORY_FILTER_MAP, match_schemes
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

    # Stage bookkeeping: a session created by process() (no start()) begins in
    # discovery as soon as the first user turn arrives. FREE_QA remains FREE_QA.
    in_free_qa = state.get("stage") == "free_qa"
    if not in_free_qa:
        state["stage"] = "discovery"

    if "conversation_history" not in state or state["conversation_history"] is None:
        state["conversation_history"] = []
    state["conversation_history"].append({"role": "user", "content": text, "language": language})
    if in_free_qa:
        # FREE_QA questions are answered from the already retrieved scheme data;
        # they must not mutate the citizen profile further.
        state["extracted_user_info"] = ExtractedUserInfo()
    else:
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


_AGE_MATERIAL_MIN = 18
_ANNUAL_INCOME_CATEGORIES = {"education", "women"}

# Recommended question order per category. Fields not listed here are only
# queried when a candidate scheme's criteria actually reference them.
_FIELD_ORDER = [
    "owns_land",
    "social_category",
    "rural_or_urban",
    "owns_house",
    "gender",
    "age",
    "annual_income",
]
_FIELD_ORDER_OVERRIDE = {
    "employment": ["age", "rural_or_urban"],
}


def _referenced_fields(scheme: Scheme) -> set[str]:
    """Fields that genuinely matter for a scheme (criteria + material age bounds)."""
    fields: set[str] = set()
    crit = scheme.eligibility_criteria
    if crit is None:
        return fields
    if crit.requires_farmer is True or crit.requires_land is True:
        fields.update({"is_farmer", "owns_land"})
    if crit.requires_student is True:
        fields.add("is_student")
    if crit.social_categories:
        fields.add("social_category")
    if crit.rural_or_urban:
        fields.add("rural_or_urban")
    if crit.requires_no_pucca_house is True:
        fields.add("owns_house")
    if crit.gender:
        fields.add("gender")
    mat_age = False
    if crit.age_min is not None or crit.age_max is not None:
        mat_age = crit.age_max is not None or (crit.age_min is not None and crit.age_min >= _AGE_MATERIAL_MIN)
    if not mat_age and scheme.id in AGE_BOUNDS:
        bounds_min, bounds_max, is_exclusive = AGE_BOUNDS[scheme.id]
        mat_age = is_exclusive and (bounds_max is not None or (bounds_min is not None and bounds_min >= _AGE_MATERIAL_MIN))
    if mat_age:
        fields.add("age")
    if crit.income_max is not None:
        fields.add("annual_income")
    return fields


def _next_missing_field(state: AgentState, schemes: List[Scheme]) -> Optional[str]:
    profile = state["user_profile"]
    category = (state.get("category") or state.get("user_intent") or "").strip().lower()
    known_state = profile.state.strip().lower() if profile.state else None

    allowed = CATEGORY_FILTER_MAP.get(category, {category})
    candidates = []
    for scheme in schemes:
        s_category = (scheme.category or "").strip().lower()
        if s_category not in allowed:
            continue
        s_state = scheme.state.strip().lower() if scheme.state else None
        if s_state not in (None, "all-india") and known_state is not None and s_state != known_state:
            continue
        candidates.append(scheme)

    referenced: set[str] = set()
    for scheme in candidates:
        referenced |= _referenced_fields(scheme)
    if category not in _ANNUAL_INCOME_CATEGORIES:
        referenced.discard("annual_income")

    missing = {
        "owns_land": profile.owns_land is None,
        "social_category": profile.social_category is None,
        "rural_or_urban": profile.rural_or_urban is None,
        "owns_house": profile.owns_house is None,
        "gender": profile.gender is None,
        "age": profile.age is None,
        "annual_income": profile.annual_income is None,
    }
    order = _FIELD_ORDER_OVERRIDE.get(category, _FIELD_ORDER)
    for field in order:
        if field in referenced and missing.get(field):
            return field
    return None


def determine_missing_information(state: AgentState, schemes: List[Scheme]) -> AgentState:
    """Ask only the criteria-aware questions any candidate scheme actually needs."""
    profile = state["user_profile"]
    category = state.get("category") or state.get("user_intent")

    if not category:
        state["current_question"] = "need"
    elif not profile.state:
        state["current_question"] = "state"
    else:
        state["current_question"] = _next_missing_field(state, schemes)
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


def _get_localized_list(field: Any, language: str) -> list:
    if not field:
        return []
    if isinstance(field, dict):
        return field.get(language) or field.get("en") or field.get("hi") or field.get("mr") or []
    if isinstance(field, list):
        return field
    return [str(field)]


def _scheme_summary(result: SchemeMatchResult, language: str) -> str:
    scheme = result.scheme
    name = _get_localized_text(scheme.name, language)
    benefit = _get_localized_benefit(scheme.benefits, language) or _get_localized_text(scheme.description, language)
    return f"{name} — {benefit}"


# The single discovery questions the agent asks, in conversation order, one at
# a time. The next question is always derived from the citizen profile and this
# fixed discovery logic (never a hard-coded questionnaire).
DISCOVERY_QUESTIONS = {
    "need": {
        "mr": "तुम्हाला कोणत्या प्रकारच्या योजनेची गरज आहे? शेती, शिक्षण, आरोग्य किंवा घरासाठी?",
        "hi": "आपको किस तरह की योजना चाहिए? खेती, पढ़ाई, इलाज या घर के लिए?",
        "en": "What kind of scheme do you need: farming, education, health, or housing?",
    },
    "state": {
        "mr": "तुम्ही कोणत्या राज्यात राहता?",
        "hi": "आप किस राज्य में रहते हैं?",
        "en": "Which state do you live in?",
    },
    "owns_land": {
        "mr": "तुमच्या नावावर शेतीची जमीन आहे का?",
        "hi": "क्या आपके नाम पर खेती की जमीन है?",
        "en": "Do you own agricultural land?",
    },
    "social_category": {
        "mr": "तुम्ही कोणत्या सामाजिक प्रवर्गात मोडता: खुला (General), अनुसूचित जाती (SC), अनुसूचित जमाती (ST), इतर मागासवर्गीय (OBC), ईबीसी (EBC), किंवा डीएनटी (DNT)?",
        "hi": "आप किस सामाजिक वर्ग में आते हैं: सामान्य (General), अनुसूचित जाति (SC), अनुसूचित जनजाति (ST), अन्य पिछड़ा वर्ग (OBC), ईबीसी (EBC), या डीएनटी (DNT)?",
        "en": "Which social category do you belong to: General, SC, ST, OBC, EBC, or DNT?",
    },
    "rural_or_urban": {
        "mr": "तुम्ही ग्रामीण भागात राहता की शहरी भागात?",
        "hi": "आप ग्रामीण क्षेत्र में रहते हैं या शहरी क्षेत्र में?",
        "en": "Do you reside in a rural village or an urban city area?",
    },
    "owns_house": {
        "mr": "तुमच्याकडे स्वतःचे पक्के घर आहे का?",
        "hi": "क्या आपके पास अपना पक्का मकान है?",
        "en": "Do you or your family own a permanent pucca house?",
    },
    "gender": {
        "mr": "तुम्ही पुरुष आहात की महिला?",
        "hi": "आप पुरुष हैं या महिला?",
        "en": "Are you a man or a woman?",
    },
    "age": {
        "mr": "तुमचे वय किती आहे?",
        "hi": "आपकी उम्र क्या है?",
        "en": "What is your age?",
    },
    "annual_income": {
        "mr": "तुमच्या कुटुंबाचे वार्षिक उत्पन्न अंदाजे किती आहे?",
        "hi": "आपके परिवार की सालाना आय लगभग कितनी है?",
        "en": "About how much does your family earn in a year?",
    },
}


def discovery_question_text(question: Optional[str], language: str) -> str:
    """Return the localized discovery question for ``question`` or '' if unknown."""
    lang = language if language in {"en", "hi", "mr"} else "en"
    if not question:
        return ""
    return DISCOVERY_QUESTIONS.get(question, {}).get(lang, "")


# Asked right after the scheme results so the user can pick the next step
# (apply / required documents) or ask a free-form question about the schemes.
SCHEME_DETAIL_FOLLOWUP = {
    "mr": "तुम्हाला पुढील प्रक्रिया किंवा आवश्यक कागदपत्रे जाणून घ्यायची आहेत का?",
    "hi": "क्या आप आगे की प्रक्रिया या आवश्यक दस्तावेज़ सुनना चाहते हैं?",
    "en": "Would you like to hear the next steps or the required documents?",
}

FREE_QA_MESSAGES = {
    "no_schemes": {
        "mr": "सध्या माझ्याकडे उपलब्ध योजना नाहीत. तुम्हाला कोणत्या प्रकारच्या योजनेची गरज आहे ते सांगा.",
        "hi": "अभी मेरे पास कोई योजना नहीं है। बताएं कि आपको किस प्रकार की योजना चाहिए।",
        "en": "I don't have scheme results yet. Tell me what kind of scheme you need and I can find them.",
    },
    "benefit_header": {
        "mr": "प्रत्येक योजनेचा मुख्य फायदा:",
        "hi": "हर योजना का मुख्य लाभ:",
        "en": "The main benefit of each scheme:",
    },
    "apply_header": {
        "mr": "या योजनांसाठी अर्ज कसे करावे:",
        "hi": "इन योजनाओं के लिए आवेदन कैसे करें:",
        "en": "Where to apply for these schemes:",
    },
    "eligibility_header": {
        "mr": "प्रत्येक योजनेची पात्रता:",
        "hi": "हर योजना की पात्रता:",
        "en": "Eligibility for each scheme:",
    },
    "documents_header": {
        "mr": "प्रत्येक योजनेसाठी आवश्यक माहिती:",
        "hi": "हर योजना के लिए आवश्यक जानकारी:",
        "en": "Information you may need for each scheme:",
    },
    "documents_none": {
        "mr": "सध्या उपलब्ध डेटामध्ये या योजनेसाठी आवश्यक माहिती नाही.",
        "hi": "मौजूदा डेटा में इस योजना के लिए आवश्यक जानकारी उपलब्ध नहीं है।",
        "en": "Required information is not available in the current scheme data.",
    },
    "apply_online_template": {
        "mr": "ऑनलाइन अर्ज करा: {url}",
        "hi": "ऑनलाइन आवेदन करें: {url}",
        "en": "Apply online: {url}",
    },
    "apply_offline_template": {
        "mr": "ऑफलाइन अर्ज: {channel}. {instructions}",
        "hi": "ऑफलाइन आवेदन: {channel}. {instructions}",
        "en": "Offline application: {channel}. {instructions}",
    },
    "apply_not_available": {
        "mr": "सध्या उपलब्ध डेटामध्ये या योजनेच्या अर्जाचे तपशील उपलब्ध नाहीत.",
        "hi": "फिलहाल उपलब्ध डेटा में इस योजना के आवेदन विवरण उपलब्ध नहीं हैं।",
        "en": "Application details for this scheme are not available in the current scheme data.",
    },
    "apply_help_note": {
        "mr": "मदतीसाठी संपर्क करा: {department}",
        "hi": "मदद के लिए संपर्क करें: {department}",
        "en": "For help, contact: {department}",
    },
    "eligibility_note": {
        "mr": "अंतिम पात्रता संबंधित सरकारी कार्यालयानुसार तपासा.",
        "hi": "अंतिम पात्रता संबंधित सरकारी कार्यालय के अनुसार जांचें।",
        "en": "Check final eligibility with the relevant government authority.",
    },
    "default_intro": {
        "mr": "मी तुम्हाला या योजना सुचवू शकतो: {names}",
        "hi": "मैं आपको ये योजनाएं बता सकता हूँ: {names}",
        "en": "I can tell you about these schemes: {names}",
    },
    "default_hint": {
        "mr": "प्रत्येक योजनेचे फायदे, पात्रता किंवा अर्जाची पद्धत विचारा.",
        "hi": "हर योजना के लाभ, पात्रता या आवेदन की विधि पूछें।",
        "en": "Ask me about the benefits, eligibility, or how to apply for any of them.",
    },
    "eligibility_final_note": {
        "mr": "कृपया अंतिम पात्रता संबंधित सरकारी कार्यालयासह तपासा.",
        "hi": "कृपया अंतिम पात्रता संबंधित सरकारी कार्यालय से जांचें।",
        "en": "Please confirm final eligibility with the relevant government authority.",
    },
}

_QA_APPLY_KEYWORDS = (
    "where", "apply", "applic", "form", "footer", "kahan", "kaha", "kuthe",
    "next steps", "next step", "steps", "step",
    "how to apply", "help me apply", "how do i apply", "how can i apply",
    "process", "proceed", "proced",
    # Hindi
    "आवेदन", "अर्ज", "फॉर्म", "कुठे", "कहां", "कहाँ",
    "प्रक्रिया", "आगे", "अगली", "अगला", "अगले", "कदम",
    # Marathi
    "पुढील", "पुढे", "प्रक्रिया",
)
_QA_ELIGIBILITY_KEYWORDS = (
    "eligib", "am i", "who can", "qualified", "आप पात्र", "पात्र", "कौन",
    "मी पात्र", "क्या मैं",
)
_QA_BENEFIT_KEYWORDS = (
    "how much", "money", "benefit", "amount", "financial", "पैसा", "पैसे",
    "रकम", "लाभ", "कितना", "कितने", "किती", "फायदा", "mitla", "kitna",
)
_QA_DOCUMENTS_KEYWORDS = (
    "document", "docs", "paper", "कागद", "कागदपत्र", "दस्तावेज", "दस्तऐवज",
)


def _qa_message(language: str, key: str) -> str:
    return FREE_QA_MESSAGES[key].get(language, FREE_QA_MESSAGES[key]["en"])


def _classify_qa_question(question: str) -> str:
    filtered = re.sub(r"[^\w\u0900-\u097F ]+", " ", question).lower()
    if any(keyword in filtered for keyword in _QA_APPLY_KEYWORDS):
        return "apply"
    if any(keyword in filtered for keyword in _QA_ELIGIBILITY_KEYWORDS):
        return "eligibility"
    if any(keyword in filtered for keyword in _QA_BENEFIT_KEYWORDS):
        return "benefit"
    if any(keyword in filtered for keyword in _QA_DOCUMENTS_KEYWORDS):
        return "documents"
    return "list"


def answer_free_qa(state: AgentState, language: str) -> AgentState:
    question = state.get("input_text", "")
    qa_intent = _classify_qa_question(question)
    results = state.get("retrieved_schemes", [])

    if not results:
        state["response_text"] = FREE_QA_MESSAGES["no_schemes"].get(language, FREE_QA_MESSAGES["no_schemes"]["en"])
        state["next_action"] = "ask_question"
        return _finalize_response(state, language)

    lines = []
    if qa_intent == "benefit":
        lines.append(FREE_QA_MESSAGES["benefit_header"].get(language, FREE_QA_MESSAGES["benefit_header"]["en"]))
        for result in results:
            name = _get_localized_text(result.scheme.name, language)
            benefit = _get_localized_benefit(result.scheme.benefits, language) or _get_localized_text(result.scheme.description, language)
            lines.append(f"• {name}: {benefit}")
    elif qa_intent == "apply":
        lines.append(FREE_QA_MESSAGES["apply_header"].get(language, FREE_QA_MESSAGES["apply_header"]["en"]))
        for result in results:
            guidance = result.scheme.application_guidance
            name = _get_localized_text(result.scheme.name, language)
            online = guidance.online_application
            offline = guidance.offline_application
            department = _get_localized_text(result.scheme.department, language)
            if online.available and online.portal_url:
                lines.append(f"• {name}: {_qa_message(language, 'apply_online_template').format(url=online.portal_url)}")
            else:
                lines.append(f"• {name}: {_qa_message(language, 'apply_not_available')}")
            if offline.available:
                channel = offline.authorized_channel or ""
                instructions = offline.instructions or ""
                lines.append(f"  {_qa_message(language, 'apply_offline_template').format(channel=channel, instructions=instructions)}")
            if department:
                lines.append(f"  {_qa_message(language, 'apply_help_note').format(department=department)}")
    elif qa_intent == "eligibility":
        lines.append(FREE_QA_MESSAGES["eligibility_header"].get(language, FREE_QA_MESSAGES["eligibility_header"]["en"]))
        for result in results:
            name = _get_localized_text(result.scheme.name, language)
            criteria = _get_localized_list(result.scheme.eligibility, language)
            detail = criteria[0] if criteria else FREE_QA_MESSAGES["eligibility_note"].get(language, FREE_QA_MESSAGES["eligibility_note"]["en"])
            lines.append(f"• {name}: {detail}")
        lines.append(FREE_QA_MESSAGES["eligibility_final_note"].get(language, FREE_QA_MESSAGES["eligibility_final_note"]["en"]))
    elif qa_intent == "documents":
        lines.append(FREE_QA_MESSAGES["documents_header"].get(language, FREE_QA_MESSAGES["documents_header"]["en"]))
        for result in results:
            name = _get_localized_text(result.scheme.name, language)
            documents = _get_localized_list(result.scheme.required_information, language)
            if documents:
                lines.append(f"• {name}:")
                for document in documents:
                    lines.append(f"   - {document}")
            else:
                lines.append(f"• {name}: {_qa_message(language, 'documents_none')}")
    else:
        names = ", ".join(_get_localized_text(result.scheme.name, language) for result in results)
        lines.append(FREE_QA_MESSAGES["default_intro"].get(language, FREE_QA_MESSAGES["default_intro"]["en"]).format(names=names))
        lines.append(FREE_QA_MESSAGES["default_hint"].get(language, FREE_QA_MESSAGES["default_hint"]["en"]))

    state["response_text"] = "\n".join(lines)
    state["next_action"] = "free_qa"
    return _finalize_response(state, language)


def _finalize_response(state: AgentState, language: str) -> AgentState:
    if "conversation_history" not in state or state["conversation_history"] is None:
        state["conversation_history"] = []
    state["conversation_history"].append({"role": "assistant", "content": state["response_text"], "language": language})
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    return state


def generate_response(state: AgentState) -> AgentState:
    language = state.get("language", "en")
    if language not in {"en", "hi", "mr"}:
        language = "en"

    # FREE_QA: the user is past discovery; answer their question from the
    # already retrieved scheme data instead of asking the next profile question.
    if state.get("stage") == "free_qa":
        return answer_free_qa(state, language)

    question = state.get("current_question")
    if question:
        state["response_text"] = discovery_question_text(question, language)
        state["next_action"] = "ask_question"
        state["stage"] = "discovery"
    elif not state.get("retrieved_schemes"):
        messages = {
            "mr": "उपलब्ध सरकारी योजनांमध्ये तुमच्यासाठी थेट जुळणारी योजना सापडली नाही.",
            "hi": "उपलब्ध सरकारी योजनाओं में आपके लिए सीधे मेल खाती कोई योजना नहीं मिली।",
            "en": "No suitable scheme was found in the available government scheme data.",
        }
        state["response_text"] = messages[language]
        state["next_action"] = "completed"
        state["completed"] = True
        state["stage"] = "completed"
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
        lines.append(SCHEME_DETAIL_FOLLOWUP[language])
        state["response_text"] = "\n".join(lines)
        state["next_action"] = "completed"
        state["completed"] = True
        # The citizen has reached the results stage. Expose FREE_QA so the agent
        # answers arbitrary questions about the returned schemes from here on.
        state["stage"] = "free_qa"

    return _finalize_response(state, language)


def build_graph(schemes: List[Scheme], extractor: Optional[ProfileExtractor] = None):
    extractor = extractor or ProfileExtractor()

    async def understand_node(state: AgentState) -> AgentState:
        return await understand_input(state, extractor)

    workflow = StateGraph(AgentState)
    workflow.add_node("understand_input", understand_node)
    workflow.add_node("update_user_profile", update_user_profile)
    workflow.add_node("determine_missing_information", lambda state: determine_missing_information(state, schemes))
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
