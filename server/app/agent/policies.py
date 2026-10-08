from __future__ import annotations


AGENT_TOOL_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "service": ("knowledge.search", "product.read", "inventory.read", "order.read", "payment.read", "shipment.read"),
    "aftersales": ("order.read", "refund.evaluate", "warranty.read"),
    "appeal": ("conversation.read", "appeal.create"),
    "risk": ("risk_rules.read", "agent_results.read"),
    "order_investigator": ("order.read", "repair_history.read"),
    "policy_investigator": ("contract.read", "policy.read"),
    "technical_investigator": ("repair_history.read", "quality_report.read"),
    "finance_investigator": ("payment.read", "invoice.read"),
    "resolution_planner": ("agent_results.read",),
}


def tools_for(agent: str) -> tuple[str, ...]:
    return AGENT_TOOL_PERMISSIONS.get(agent, ())


def ensure_read_only(agent: str) -> None:
    denied = [tool for tool in tools_for(agent) if not tool.endswith((".read", ".search", ".evaluate"))]
    if denied:
        raise PermissionError(f"{agent} has write tools in an investigation stage: {', '.join(denied)}")
