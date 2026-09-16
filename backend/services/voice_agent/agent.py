from __future__ import annotations

from typing import Dict, List, Optional

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

    async def process(self, session_id: str, user_text: str) -> dict:
        text = user_text.strip()
        if not text:
            return {
                "session_id": session_id,
                "response_text": "Please tell me what kind of government scheme you need.",
                "language": "en",
                "next_action": "ask_question",
"should_send_sms": bool(state.get("completed") and state.get("retrieved_schemes")),
                "schemes": [],
            }

        state = self.sessions.get(session_id, new_agent_state(session_id))
        state["input_text"] = text
        result = await self.graph.ainvoke(state)
        self.sessions[session_id] = result
        return self._public_result(result)

    def reset(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    @staticmethod
    def _public_result(state: AgentState) -> dict:
        return {
            "session_id": state["session_id"],
            "response_text": state.get("response_text", ""),
            "language": state.get("language", "en"),
            "next_action": state.get("next_action", "ask_question"),
            "should_send_sms": False,
            "schemes": [
                {
                    "id": result.scheme.id,
                    "name": result.scheme.name,
                    "category": result.scheme.category,
                    "relevance_score": result.relevance_score,
                    "matched_reasons": result.matched_reasons,
                    "application_url": result.scheme.application_url,
                }
                for result in state.get("retrieved_schemes", [])
            ],
        }
