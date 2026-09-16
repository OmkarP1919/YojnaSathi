from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas import Scheme
from services.voice_agent.extractor import ProfileExtractor
from services.voice_agent.graph import build_graph
from services.voice_agent.state import AgentState, new_agent_state


class VoiceAgent:
    """Text-first multilingual agent with in-memory session state."""

    def __init__(self, schemes: Optional[List[Scheme]] = None):
        self.schemes = schemes or []
        self.sessions: Dict[str, AgentState] = {}
        self.extractor = ProfileExtractor()
        self.graph = build_graph(self.schemes, self.extractor)

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
