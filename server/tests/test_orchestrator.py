from pathlib import Path

from app.agent.case_workflow.executor import execute_approved_actions
from app.agent.graph import SupportGraph
from app.agent.service import SupportAgent
from app.rag.retriever import KnowledgeBase


ROOT = Path(__file__).resolve().parents[2]


def make_graph() -> SupportGraph:
    return SupportGraph(SupportAgent(KnowledgeBase(ROOT / "knowledge-base")))


def test_orchestrator_routes_to_one_bounded_business_agent() -> None:
    graph = make_graph()
    knowledge = graph.respond("星云耳机支持降噪吗？", "demo-user", "route-knowledge")
    commerce = graph.respond("查询订单 XY20260702", "demo-user", "route-commerce")
    aftersales = graph.respond("退款 XY20260701", "demo-user", "route-aftersales")

    assert knowledge.route == "service"
    assert knowledge.intent == "knowledge_qa"
    assert [item["agent"] for item in knowledge.agent_results] == ["service"]
    assert commerce.route == "service"
    assert commerce.intent == "order_query"
    assert [item["agent"] for item in commerce.agent_results] == ["service"]
    assert aftersales.route == "aftersales"
    assert [item["agent"] for item in aftersales.agent_results] == ["aftersales"]


def test_complex_appeal_runs_fixed_read_only_investigation_workflow() -> None:
    response = make_graph().respond(
        "耳机维修两次仍然坏了，我要维权",
        "demo-user",
        "appeal-workflow",
    )
    agents = [item["agent"] for item in response.agent_results]

    assert response.route == "appeal"
    assert response.appeal_id and response.appeal_id.startswith("AP-")
    assert response.needs_human is True
    assert agents == [
        "appeal",
        "order_investigator",
        "policy_investigator",
        "technical_investigator",
        "finance_investigator",
        "resolution_planner",
        "risk",
    ]
    investigation_tools = [call["name"] for item in response.agent_results[1:5] for call in item["tool_calls"]]
    assert investigation_tools
    assert all(name.endswith(".read") for name in investigation_tools)
    assert not any("write" in name for name in investigation_tools)
    assert response.risk_review == {"requires_approval": True, "agent": "risk"}


def test_security_risk_is_blocked_for_human_review() -> None:
    response = make_graph().respond("账号收到异地登录提醒", "demo-user", "risk-workflow")

    assert response.route == "risk"
    assert response.needs_human is True
    assert response.agent_results[-1]["agent"] == "risk"
    assert response.agent_results[-1]["next_action"] == "human_review"


def test_executor_cannot_run_before_approval() -> None:
    actions = [{"type": "create_refund", "amount": 599}]

    assert execute_approved_actions(actions, approved=False) == []
    assert execute_approved_actions(actions, approved=True) == [
        {"type": "create_refund", "amount": 599, "status": "submitted"}
    ]
