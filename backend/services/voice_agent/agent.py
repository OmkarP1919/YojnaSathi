from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.schemas import Scheme
from services.voice_agent.extractor import ProfileExtractor
from services.voice_agent.graph import build_graph, determine_missing_information, discovery_question_text
from services.voice_agent.state import AgentState, new_agent_state


GREETING_MESSAGES = {
    "en": "Hello! I am YojnaSathi, and I can help you find government schemes. I will ask you a few simple questions first.",
    "hi": "नमस्ते! मैं योजनासाथी हूँ, और मैं आपको सरकारी योजनाएँ खोजने में मदद कर सकता हूँ। पहले मैं कुछ आसान सवाल पूछूँगा।",
    "mr": "नमस्कार! मी योजना साथी आहे, आणि मी तुम्हाला सरकारी योजना शोधण्यात मदत करू शकतो. आधी मी काही सोपे प्रश्न विचारतो.",
}


class VoiceAgent:
    """Multilingual voice conversation agent with in-memory session state.

    The agent is conversation-first: ``start()`` initiates a session with a
    localized greeting plus the first discovery question (no user input needed).
    ``process()`` then drives guided discovery one question at a time, matching,
    and a FREE_QA stage once schemes have been returned.
    """

    def __init__(self, schemes: Optional[List[Scheme]] = None):
        self.schemes = schemes or []
        self.sessions: Dict[str, AgentState] = {}
        self.extractor = ProfileExtractor()
        self.graph = build_graph(self.schemes, self.extractor)

    async def start(self, session_id: str, language: Optional[str] = None) -> dict:
        """Begin a new conversation: greeting + the first discovery question.

        The first question is derived from the existing discovery logic against
        an empty profile (which always yields the scheme-need question), so the
        agent initiates the conversation without any user input.
        """
        lang = language if language in {"en", "hi", "mr"} else "en"

        state = new_agent_state(session_id)
        state["language"] = lang
        state["language_hint"] = lang
        state["stage"] = "greeting"

        try:
            determine_missing_information(state)
        except Exception:  # pragma: no cover - the discovery logic is stable.
            state["current_question"] = "need"
        question = state.get("current_question") or "need"

        greeting = GREETING_MESSAGES.get(lang, GREETING_MESSAGES["en"])
        question_text = discovery_question_text(question, lang)
        message = f"{greeting}\n\n{question_text}".strip()
        state["response_text"] = message
        state["next_action"] = "ask_question"
        state["conversation_history"].append({"role": "assistant", "content": message, "language": lang})
        state["last_updated"] = datetime.now(timezone.utc).isoformat()

        self.sessions[session_id] = state
        return self._public_result(state)

    async def process(self, session_id: str, user_text: str, language_hint: Optional[str] = None) -> dict:
        state = self.sessions.get(session_id, new_agent_state(session_id))
        if language_hint in {"en", "hi", "mr"}:
            state["language_hint"] = language_hint
        else:
            state["language_hint"] = None

        text = (user_text or "").strip()
        if not text:
            lang = state.get("language_hint") or state.get("language", "en")
            prompts = {
                "mr": "कृपया तुम्हाला कोणत्या सरकारी योजनेची माहिती हवी आहे ते सांगा.",
                "hi": "कृपया बताएं कि आपको किस प्रकार की सरकारी योजना चाहिए।",
                "en": "Please tell me what kind of government scheme you need.",
            }
            return {
                "session_id": session_id,
                "response_text": prompts.get(lang, prompts["en"]),
                "language": lang,
                "next_action": "ask_question",
                "should_send_sms": False,
                "schemes": [],
            }

        state["input_text"] = text
        result = await self.graph.ainvoke(state)
        self.sessions[session_id] = result
        return self._public_result(result)

    def reset(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    @staticmethod
    def _public_result(state: AgentState) -> dict:
        lang = state.get("language", "en")

        def _localize_text(field: Any) -> str:
            if not field:
                return ""
            if isinstance(field, dict):
                return field.get(lang) or field.get("en") or field.get("hi") or field.get("mr") or ""
            return str(field)

        def _localize_list(field: Any) -> list:
            if not field:
                return []
            if isinstance(field, dict):
                return field.get(lang) or field.get("en") or field.get("hi") or field.get("mr") or []
            if isinstance(field, list):
                return field
            return [str(field)]

        return {
            "session_id": state["session_id"],
            "response_text": state.get("response_text", ""),
            "language": lang,
            "next_action": state.get("next_action", "ask_question"),
            "stage": state.get("stage", "discovery"),
            "should_send_sms": False,
            "profile": state.get("user_profile", {}).model_dump() if hasattr(state.get("user_profile"), "model_dump") else {},
            "schemes": [
                {
                    "id": result.scheme.id,
                    "name": _localize_text(result.scheme.name),
                    "description": _localize_text(result.scheme.description),
                    "benefits": _localize_list(result.scheme.benefits),
                    "category": result.scheme.category,
                    "relevance_score": result.relevance_score,
                    "matched_reasons": result.matched_reasons,
                    "reason_codes": [rc.model_dump() for rc in (result.reason_codes or [])],
                    "application_url": result.scheme.application_url,
                }
                for result in state.get("retrieved_schemes", [])
            ],
        }
