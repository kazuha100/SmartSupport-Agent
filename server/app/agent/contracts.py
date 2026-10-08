from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """统一的子 Agent 输出；业务写操作必须由审批后的执行层完成。"""

    agent: str
    intent: str
    status: Literal["completed", "blocked", "waiting", "failed"] = "completed"
    summary: str = ""
    answer: str = ""
    findings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0
    needs_human: bool = False
    next_action: str | None = None
    order_id: str | None = None
    appeal_id: str | None = None
    response: Any | None = Field(default=None, exclude=True)
