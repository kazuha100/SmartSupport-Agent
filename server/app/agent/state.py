from __future__ import annotations

from typing import TypedDict

from app.models import ChatResponse

from .contracts import AgentResult


class SupportState(TypedDict, total=False):
    user_id: str
    session_id: str
    message: str
    resolved_message: str
    order_id: str | None
    last_order_id: str | None
    used_memory: bool
    turn_count: int
    intent: str
    route: str
    routing_source: str
    routing_reason: str
    routing_confidence: float
    extracted_entities: dict[str, str]
    clarification_question: str | None
    current_stage: str
    agent_results: list[AgentResult]
    citations: list[str]
    appeal_id: str | None
    needs_human: bool
    response: ChatResponse
