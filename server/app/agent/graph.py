from __future__ import annotations

import re
import time
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.agents.aftersales import AfterSalesAgent
from app.agent.agents.appeal import AppealAgent
from app.agent.agents.risk import RiskAgent
from app.agent.agents.service import ServiceAgent
from app.agent.contracts import AgentResult
from app.agent.service import SupportAgent
from app.agent.state import SupportState
from app.models import ChatResponse, TraceStep
from app.observability import observe_agent
from app.routing import SemanticRouter


ORDER_PATTERN = re.compile(r"(?:XY\d{8}|SC\d{8,18})", re.IGNORECASE)
Route = Literal["general", "service", "aftersales", "appeal", "risk", "handoff", "clarify", "missing_order"]

ROUTE_LABELS: dict[Route, str] = {
    "general": "总 Agent 通用对话",
    "service": "Service Agent",
    "aftersales": "AfterSales Agent",
    "appeal": "Appeal Agent",
    "risk": "Risk Agent",
    "handoff": "人工转接",
    "clarify": "意图澄清",
    "missing_order": "订单参数检查",
}


class SupportGraph:
    """Support Orchestrator: one entry point, bounded agents, auditable state."""

    def __init__(self, agent: SupportAgent, checkpointer=None, intent_router_min_confidence: float = 0.65):
        self.agent = agent
        self.checkpointer = checkpointer or InMemorySaver()
        self.service = ServiceAgent(agent)
        self.aftersales = AfterSalesAgent(agent)
        self.appeal = AppealAgent(agent)
        self.risk = RiskAgent(agent)
        classifier = agent.chat_model if agent.chat_model and hasattr(agent.chat_model, "classify_intent") else None
        self.router = SemanticRouter(classifier, intent_router_min_confidence)
        builder = StateGraph(SupportState)
        builder.add_node("orchestrate", self._prepare_context)
        for route in ROUTE_LABELS:
            builder.add_node(route, self._run_route)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "orchestrate")
        builder.add_conditional_edges("orchestrate", lambda state: state["route"], {route: route for route in ROUTE_LABELS})
        for route in ROUTE_LABELS:
            builder.add_edge(route, "finalize")
        builder.add_edge("finalize", END)
        self.graph = builder.compile(checkpointer=self.checkpointer)

    def respond(self, message: str, user_id: str, session_id: str) -> ChatResponse:
        started = time.perf_counter()
        route = self.detect_route(message)
        try:
            result = self.graph.invoke(
                {"message": message, "user_id": user_id, "session_id": session_id},
                config={"configurable": {"thread_id": self._thread_id(user_id, session_id)}},
            )
            response = result["response"]
            route = response.route or route
            statuses = [item.get("status") for item in response.agent_results]
            outcome = statuses[-1] if statuses else "completed"
            if response.needs_human:
                outcome = "human_required"
            observe_agent(
                route,
                outcome,
                time.perf_counter() - started,
                response.confidence,
                response.needs_human,
            )
            return response
        except Exception:
            observe_agent(route, "error", time.perf_counter() - started)
            raise

    def session_state(self, user_id: str, session_id: str) -> dict:
        snapshot = self.graph.get_state(config={"configurable": {"thread_id": self._thread_id(user_id, session_id)}})
        values = snapshot.values
        return {
            "session_id": session_id,
            "user_id": user_id,
            "turn_count": values.get("turn_count", 0),
            "last_order_id": values.get("last_order_id"),
            "last_route": values.get("route"),
            "current_stage": values.get("current_stage", "idle"),
            "agent_results": [item.model_dump(exclude={"response"}) for item in values.get("agent_results", [])],
        }

    @staticmethod
    def _thread_id(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    @staticmethod
    def detect_route(message: str) -> Route:
        decision = SemanticRouter().classify(message)
        if decision.requires_order and ORDER_PATTERN.search(message.upper()) is None:
            return "missing_order"
        return decision.route  # type: ignore[return-value]

    def _prepare_context(self, state: SupportState) -> dict:
        message = state["message"].strip()
        match = ORDER_PATTERN.search(message.upper())
        explicit_order_id = match.group(0) if match else None
        decision = self.router.classify(message)
        route = decision.route
        entity_order_id = decision.entities.get("order_id", "").upper()
        if entity_order_id and ORDER_PATTERN.fullmatch(entity_order_id) is None:
            entity_order_id = ""
        remembered = state.get("last_order_id")
        order_id = explicit_order_id or entity_order_id or None
        used_memory = False
        if not order_id and decision.requires_order and remembered:
            order_id = remembered
            used_memory = True
        if decision.requires_order and not order_id:
            route = "missing_order"
        return {
            "route": route,
            "intent": decision.intent,
            "routing_source": decision.source,
            "routing_reason": decision.reason,
            "routing_confidence": decision.confidence,
            "extracted_entities": decision.entities,
            "clarification_question": decision.clarification_question,
            "resolved_message": f"{message} {order_id}" if used_memory and order_id else message,
            "order_id": order_id,
            "last_order_id": explicit_order_id or entity_order_id or remembered,
            "used_memory": used_memory,
            "turn_count": state.get("turn_count", 0) + 1,
            "current_stage": "routed",
            "agent_results": [],
        }

    def _run_route(self, state: SupportState) -> dict:
        route = state["route"]
        message = state["resolved_message"]
        user_id = state["user_id"]
        order_id = state.get("order_id")
        if route == "missing_order":
            requested = "退款或查询订单"
            result = AgentResult(agent="orchestrator", intent="missing_order", status="waiting", summary="缺少订单号", answer=f"请提供商城订单号，我才能{requested}。", confidence=0.98, next_action="collect_order_id")
            return {"agent_results": [result], "current_stage": "waiting_for_order"}
        if route == "clarify":
            question = state.get("clarification_question") or "请补充说明你最希望客服解决的问题。"
            result = AgentResult(
                agent="orchestrator",
                intent="clarification",
                status="waiting",
                summary="需要澄清主意图",
                answer=question,
                confidence=state.get("routing_confidence", 0),
                next_action="collect_intent",
            )
            return {"agent_results": [result], "current_stage": "waiting_for_clarification"}
        if route == "handoff":
            result = AgentResult(
                agent="orchestrator",
                intent="human_handoff",
                status="waiting",
                summary="需要人工客服复核",
                answer="这个问题需要人工客服进一步确认，我已为你转接人工服务。",
                confidence=state.get("routing_confidence", 0),
                needs_human=True,
                next_action="human_review",
            )
            return {"agent_results": [result], "needs_human": True, "current_stage": "awaiting_human"}
        if route == "appeal":
            results = self.appeal.run_workflow(message, user_id, order_id)
            result = results[0]
        elif route == "risk":
            base = self.risk.run(message, user_id, order_id)
            result = self.risk.assess(message, base)
            result.response = base.response
            results = [base, result]
        elif route == "service":
            result = self.service.run(message, user_id, order_id)
        elif route == "aftersales":
            result = self.aftersales.run(message, user_id, order_id)
        else:
            result = self.agent_result_from_response(self.agent.respond(message, user_id), "orchestrator", "general_chat", order_id)
        if route not in {"appeal", "risk"}:
            results = [result]
        return {
            "agent_results": results,
            "appeal_id": result.appeal_id,
            "needs_human": result.needs_human,
            "current_stage": "awaiting_human" if result.needs_human else "answered",
        }

    @staticmethod
    def agent_result_from_response(response: ChatResponse, agent: str, intent: str, order_id: str | None) -> AgentResult:
        return AgentResult(
            agent=agent,
            intent=intent,
            status="completed" if response.trace[-1].status != "blocked" else "blocked",
            summary=response.answer,
            answer=response.answer,
            findings=[item.detail for item in response.trace],
            evidence_ids=[item.doc_id for item in response.citations],
            citations=[item.doc_id for item in response.citations],
            tool_calls=[item.model_dump(mode="json") for item in response.tool_calls],
            confidence=response.confidence,
            needs_human=response.needs_human,
            order_id=order_id,
            response=response,
        )

    @staticmethod
    def _finalize(state: SupportState) -> dict:
        results = state.get("agent_results", [])
        result = next((item for item in results if item.response is not None), None)
        result = result or next((item for item in results if item.agent == "appeal"), None)
        result = result or (results[-1] if results else AgentResult(agent="orchestrator", intent="general_chat", answer="暂时无法处理这个问题。"))
        workflow_result = results[-1] if results else result
        response = result.response or ChatResponse(
            answer=result.answer,
            intent="human_handoff" if result.needs_human else ("general_chat" if result.intent == "general" else result.intent),
            confidence=result.confidence,
            needs_human=result.needs_human,
            tool_calls=result.tool_calls,
        )
        trace = [TraceStep(name="Support Orchestrator", detail=f"已路由至 {ROUTE_LABELS[state['route']] }。")]
        trace.append(TraceStep(
            name="三级混合路由",
            detail=(
                f"主意图 {state.get('intent', state['route'])}，来源 {state.get('routing_source', 'rule_fallback')}，"
                f"置信度 {state.get('routing_confidence', 0):.2f}；{state.get('routing_reason', '已完成路由判断')}。"
            ),
        ))
        if state.get("used_memory") and state.get("order_id"):
            trace.append(TraceStep(name="会话记忆", detail=f"已从当前会话恢复订单号 {state['order_id']}。"))
        if result.agent == "appeal":
            trace.append(TraceStep(name="申诉调查流程", detail="订单、政策、技术和财税调查节点已并行启动。", status="waiting"))
        response = response.model_copy(update={
            "trace": trace + response.trace,
            "needs_human": workflow_result.needs_human,
            "route": state["route"],
            "current_stage": state.get("current_stage"),
            "agent_results": [item.model_dump(exclude={"response"}) for item in results],
            "appeal_id": result.appeal_id,
            "risk_review": {"requires_approval": workflow_result.needs_human, "agent": "risk"} if workflow_result.needs_human else None,
        })
        return {"response": response}
