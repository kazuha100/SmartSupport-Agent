from __future__ import annotations

from app.agent.contracts import AgentResult
from app.models import ChatResponse, TraceStep

from .base import BusinessAgent


class RiskAgent(BusinessAgent):
    key = "risk"
    label = "Risk Agent"

    def run(self, message: str, user_id: str, order_id: str | None = None) -> AgentResult:
        answer = "已识别到账号、支付或安全风险。请立即停止相关操作并保护账户信息，我已为你升级人工审核。"
        response = ChatResponse(
            answer=answer,
            intent="human_handoff",
            confidence=0.98,
            needs_human=True,
            trace=[TraceStep(name="Risk Agent", detail="高风险场景使用确定性规则阻断，未调用模型。", status="waiting")],
        )
        return AgentResult(
            agent=self.key,
            intent="risk_review",
            status="waiting",
            summary=answer,
            answer=answer,
            findings=["高风险场景禁止自动执行"],
            confidence=0.98,
            needs_human=True,
            next_action="human_review",
            order_id=order_id,
            response=response,
        )

    def assess(self, message: str, base: AgentResult | None = None) -> AgentResult:
        high_risk_terms = ("账号被盗", "账户被盗", "盗号", "异地登录", "重复扣款", "人身安全", "起火", "漏电", "投诉", "维权")
        reasons = ["问题包含账号、支付或安全风险关键词"] if any(term in message for term in high_risk_terms) else []
        if base and base.needs_human:
            reasons.append("业务 Agent 判断需要人工接管")
        high = bool(reasons)
        return AgentResult(
            agent=self.key,
            intent="risk_review",
            status="waiting" if high else "completed",
            summary="识别到高风险，需要人工审核。" if high else "未发现需要立即升级的风险。",
            findings=reasons or ["当前问题可由业务 Agent 继续处理"],
            confidence=0.96 if high else 0.88,
            needs_human=high,
            next_action="human_review" if high else None,
        )
