from __future__ import annotations

from uuid import uuid4

from app.agent.contracts import AgentResult
from app.agent.case_workflow.investigators import run_investigations
from app.agent.case_workflow.planner import plan_resolution
from app.agent.case_workflow.risk import review_plan

from .base import BusinessAgent


class AppealAgent(BusinessAgent):
    key = "appeal"
    label = "Appeal Agent"

    def run_workflow(self, message: str, user_id: str, order_id: str | None = None) -> list[AgentResult]:
        appeal_id = f"AP-{uuid4().hex[:10].upper()}"
        investigations = run_investigations(message, order_id)
        plan = plan_resolution(message, investigations)
        review = review_plan(message, plan)
        intake = AgentResult(
            agent=self.key,
            intent="appeal",
            status="completed",
            summary="已创建申诉并分派四个只读调查节点。",
            answer="已为你创建售后申诉。我们正在核对订单、售后政策、维修记录和支付发票信息，处理结果需要人工审核。",
            findings=["申诉已绑定当前会话", "调查 Agent 仅拥有只读工具权限"],
            evidence_ids=[evidence for item in investigations for evidence in item.evidence_ids],
            confidence=min(item.confidence for item in investigations),
            needs_human=True,
            next_action="human_approval",
            order_id=order_id,
            appeal_id=appeal_id,
        )
        planner = AgentResult(
            agent="resolution_planner",
            intent="appeal_plan",
            summary=plan["title"],
            findings=plan["rationale"],
            confidence=0.87,
            needs_human=True,
            next_action="risk_review",
            order_id=order_id,
            appeal_id=appeal_id,
        )
        risk = AgentResult(
            agent="risk",
            intent="risk_review",
            status="waiting",
            summary="风险审核已阻断自动执行，等待人工审批。",
            findings=review["reasons"],
            confidence=0.96,
            needs_human=True,
            next_action="human_approval",
            order_id=order_id,
            appeal_id=appeal_id,
        )
        return [intake, *investigations, planner, risk]

    def run(self, message: str, user_id: str, order_id: str | None = None) -> AgentResult:
        return self.run_workflow(message, user_id, order_id)[0]
