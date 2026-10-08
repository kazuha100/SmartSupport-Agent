from pathlib import Path

from app.agent.graph import SupportGraph
from app.agent.service import SupportAgent
from app.rag.retriever import KnowledgeBase
from app.routing import IntentPrediction, SemanticRouter


ROOT = Path(__file__).resolve().parents[2]


def make_graph() -> SupportGraph:
    return SupportGraph(SupportAgent(KnowledgeBase(ROOT / "knowledge-base")))


def test_graph_uses_order_from_previous_turn() -> None:
    graph = make_graph()
    order_id = "SC202607211234560001"
    first = graph.respond(f"查询订单 {order_id}", "registered-user", "memory-test")
    follow_up = graph.respond("它到哪里了？", "registered-user", "memory-test")

    assert first.intent == "order_query"
    assert follow_up.intent == "shipment_query"
    assert follow_up.tool_calls[0].arguments["order_id"] == order_id
    assert any(step.name == "会话记忆" for step in follow_up.trace)


def test_graph_isolates_sessions() -> None:
    graph = make_graph()
    graph.respond("查询订单 SC202607211234560001", "registered-user", "session-a")
    response = graph.respond("它到哪里了？", "registered-user", "session-b")

    assert not response.tool_calls
    assert "订单号" in response.answer


def test_graph_isolates_users_with_same_session_id() -> None:
    graph = make_graph()
    graph.respond("查询订单 SC202607211234560001", "registered-user", "shared-session")
    response = graph.respond("它到哪里了？", "other-user", "shared-session")

    assert not response.tool_calls
    assert "订单号" in response.answer


def test_refund_policy_question_routes_to_service() -> None:
    graph = make_graph()
    response = graph.respond("七天无理由退货有什么要求？", "demo-user", "policy-question")

    assert response.intent == "knowledge_qa"
    assert response.route == "service"
    assert response.agent_results[0]["agent"] == "service"
    assert response.citations


def test_refund_negation_is_policy_question_not_refund_action() -> None:
    response = make_graph().respond(
        "我不想退款，只想了解退款政策",
        "demo-user",
        "refund-negation",
    )

    assert response.route == "service"
    assert response.intent == "knowledge_qa"
    assert not response.tool_calls


def test_repeated_repair_failure_routes_to_formal_appeal() -> None:
    response = make_graph().respond(
        "维修两次还是坏了，我该怎么办",
        "demo-user",
        "repeated-repair",
    )

    assert response.route == "appeal"
    assert response.needs_human is True


def test_conflicting_logistics_refund_and_complaint_prioritizes_appeal() -> None:
    response = make_graph().respond(
        "物流一直没更新，我还要退款并正式投诉商家",
        "demo-user",
        "multi-intent-appeal",
    )

    assert response.route == "appeal"
    assert response.needs_human is True
    assert any(step.name == "三级混合路由" for step in response.trace)


class GraphClassifier:
    def __init__(self, prediction: IntentPrediction):
        self.prediction = prediction

    def classify_intent(self, message: str) -> IntentPrediction:
        return self.prediction


def test_graph_returns_clarification_for_unresolved_multi_intent() -> None:
    graph = make_graph()
    graph.router = SemanticRouter(GraphClassifier(IntentPrediction(
        intent="shipment_query",
        route="service",
        confidence=0.83,
        candidate_intents=("refund_request",),
        requires_clarification=True,
        clarification_question="你希望先查询物流，还是先申请退款？",
    )))

    response = graph.respond("东西还没收到，我也在考虑不要了", "demo-user", "clarify-graph")

    assert response.route == "clarify"
    assert response.intent == "clarification"
    assert response.current_stage == "waiting_for_clarification"
    assert response.answer == "你希望先查询物流，还是先申请退款？"
    assert response.needs_human is False


def test_graph_hands_low_confidence_risk_to_human() -> None:
    graph = make_graph()
    graph.router = SemanticRouter(GraphClassifier(IntentPrediction(
        intent="risk_report",
        route="risk",
        confidence=0.5,
        reason="可能存在安全问题",
    )))

    response = graph.respond("设备表现有些异常", "demo-user", "risk-low-confidence")

    assert response.route == "handoff"
    assert response.intent == "human_handoff"
    assert response.current_stage == "awaiting_human"
    assert response.needs_human is True
