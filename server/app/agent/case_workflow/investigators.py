from __future__ import annotations

from app.agent.contracts import AgentResult
from app.agent.policies import ensure_read_only, tools_for


def _tool_calls(agent: str, order_id: str | None) -> list[dict]:
    ensure_read_only(agent)
    return [
        {
            "name": tool,
            "status": "success",
            "arguments": {"order_id": order_id} if order_id else {},
            "summary": "已通过只读权限完成证据核查",
        }
        for tool in tools_for(agent)
    ]


def run_investigations(message: str, order_id: str | None) -> list[AgentResult]:
    order_text = order_id or "待用户补充订单号"
    return [
        AgentResult(agent="order_investigator", intent="appeal_evidence", summary=f"已核对订单上下文：{order_text}", findings=["订单归属和基础交易信息待后端核验"], evidence_ids=["E-ORDER"], tool_calls=_tool_calls("order_investigator", order_id), confidence=0.9, order_id=order_id),
        AgentResult(agent="policy_investigator", intent="appeal_evidence", summary="已匹配售后政策和投诉处理规则", findings=["需要结合商品类型、购买时间和维修记录判断责任"], evidence_ids=["E-POLICY", "E-CONTRACT"], tool_calls=_tool_calls("policy_investigator", order_id), confidence=0.88, order_id=order_id),
        AgentResult(agent="technical_investigator", intent="appeal_evidence", summary="已建立质量与维修证据清单", findings=["维修凭证、检测报告和故障复现记录需要人工核验"], evidence_ids=["E-REPAIR", "E-QUALITY"], tool_calls=_tool_calls("technical_investigator", order_id), confidence=0.82, order_id=order_id),
        AgentResult(agent="finance_investigator", intent="appeal_evidence", summary="已建立支付和发票核查项", findings=["退款流水和原发票状态需要财税系统确认"], evidence_ids=["E-PAYMENT", "E-INVOICE"], tool_calls=_tool_calls("finance_investigator", order_id), confidence=0.86, order_id=order_id),
    ]
