from __future__ import annotations

from app.agent.contracts import AgentResult
from app.agent.service import SupportAgent


class BusinessAgent:
    key = "business"
    label = "业务 Agent"

    def __init__(self, core: SupportAgent):
        self.core = core

    def run(self, message: str, user_id: str, order_id: str | None = None) -> AgentResult:
        response = self.core.respond(message, user_id)
        return AgentResult(
            agent=self.key,
            intent=response.intent,
            status="completed" if response.trace[-1].status != "blocked" else "blocked",
            summary=response.answer,
            answer=response.answer,
            findings=[step.detail for step in response.trace],
            evidence_ids=[item.doc_id for item in response.citations],
            citations=[item.doc_id for item in response.citations],
            tool_calls=[item.model_dump(mode="json") for item in response.tool_calls],
            confidence=response.confidence,
            needs_human=response.needs_human,
            order_id=order_id,
            response=response,
        )
