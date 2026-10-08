from __future__ import annotations

from app.agent.contracts import AgentResult


def plan_resolution(message: str, investigations: list[AgentResult]) -> dict:
    return {
        "title": "形成售后处理方案：补充证据后进行退款或维修责任复核",
        "rationale": [item.summary for item in investigations],
        "actions": ["补充订单和维修凭证", "由售后主管审核处理方案"],
    }

