from __future__ import annotations


def review_plan(message: str, plan: dict) -> dict:
    reasons = ["申诉包含可能影响退款、维修或发票责任的高风险写操作"]
    if any(term in message for term in ("安全", "起火", "漏电", "爆炸")):
        reasons.append("涉及人身或财产安全，必须人工升级")
    return {"risk_level": "high", "passed": False, "requires_approval": True, "reasons": reasons}

