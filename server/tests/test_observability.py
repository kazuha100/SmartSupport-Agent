import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.agent.graph import SupportGraph
from app.agent.service import SupportAgent
from app.commerce_repository import CommerceError
from app.llm import DeepSeekClient, ModelError
from app.models import Citation
from app.observability import MetricsMiddleware, metrics_response
from app.rag.retriever import KnowledgeBase
from app.tools import business


ROOT = Path(__file__).resolve().parents[2]


def metric(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_http_metrics_use_route_templates_and_exclude_monitoring_endpoints() -> None:
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict:
        return {"item_id": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    @app.get("/metrics")
    def metrics():
        return metrics_response()

    client = TestClient(app, raise_server_exceptions=False)
    request_labels = {"method": "GET", "path": "/items/{item_id}", "status": "200"}
    before = metric("smart_support_http_requests_total", request_labels)
    assert client.get("/items/one").status_code == 200
    assert client.get("/items/two").status_code == 200
    assert metric("smart_support_http_requests_total", request_labels) == before + 2
    assert metric("smart_support_http_requests_total", {"method": "GET", "path": "/items/one", "status": "200"}) == 0

    error_labels = {"method": "GET", "path": "/boom", "status": "500"}
    error_before = metric("smart_support_http_requests_total", error_labels)
    assert client.get("/boom").status_code == 500
    assert metric("smart_support_http_requests_total", error_labels) == error_before + 1

    metrics_labels = {"method": "GET", "path": "/metrics", "status": "200"}
    metrics_before = metric("smart_support_http_requests_total", metrics_labels)
    assert client.get("/metrics").status_code == 200
    assert metric("smart_support_http_requests_total", metrics_labels) == metrics_before


def test_llm_metrics_capture_usage_success_error_and_streaming() -> None:
    responses = [
        httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "grounded answer"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        ),
        httpx.Response(500, text="failed"),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="metrics-model",
        http_client=http_client,
    )
    citation = Citation(doc_id="doc", title="Policy", section="General", version="1", excerpt="Evidence", score=1)
    success_labels = {"model": "metrics-model", "operation": "grounded", "stream": "false", "status": "success"}
    success_before = metric("smart_support_llm_calls_total", success_labels)
    prompt_before = metric("smart_support_llm_tokens_total", {"model": "metrics-model", "type": "prompt"})
    completion_before = metric("smart_support_llm_tokens_total", {"model": "metrics-model", "type": "completion"})
    assert model.answer_with_sources("question", [citation]) == "grounded answer"
    assert metric("smart_support_llm_calls_total", success_labels) == success_before + 1
    assert metric("smart_support_llm_tokens_total", {"model": "metrics-model", "type": "prompt"}) == prompt_before + 11
    assert metric("smart_support_llm_tokens_total", {"model": "metrics-model", "type": "completion"}) == completion_before + 7

    error_labels = {"model": "metrics-model", "operation": "general", "stream": "false", "status": "error"}
    error_before = metric("smart_support_llm_calls_total", error_labels)
    with pytest.raises(ModelError):
        model.answer_general("question")
    assert metric("smart_support_llm_calls_total", error_labels) == error_before + 1
    http_client.close()

    stream_body = (
        'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )
    stream_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=stream_body)))
    stream_model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="metrics-stream-model",
        http_client=stream_client,
    )
    stream_labels = {"model": "metrics-stream-model", "operation": "general", "stream": "true", "status": "success"}
    stream_before = metric("smart_support_llm_calls_total", stream_labels)
    ttft_before = metric(
        "smart_support_llm_time_to_first_token_seconds_count",
        {"model": "metrics-stream-model", "operation": "general"},
    )
    assert "".join(stream_model.stream_general("hello")) == "first"
    assert metric("smart_support_llm_calls_total", stream_labels) == stream_before + 1
    assert metric(
        "smart_support_llm_time_to_first_token_seconds_count",
        {"model": "metrics-stream-model", "operation": "general"},
    ) == ttft_before + 1
    assert metric("smart_support_llm_tokens_total", {"model": "metrics-stream-model", "type": "prompt"}) == 5
    assert metric("smart_support_llm_tokens_total", {"model": "metrics-stream-model", "type": "completion"}) == 2
    stream_client.close()


def test_rag_metrics_record_hits_and_misses(tmp_path: Path) -> None:
    title = "\u9000\u6b3e\u653f\u7b56"
    content = "\u9000\u6b3e\u653f\u7b56\u5141\u8bb8\u9000\u8d27"
    (tmp_path / "policy.md").write_text(
        f"---\ntitle: {title}\ndoc_id: refund\nversion: '1'\n---\n# {title}\n## Rules\n{content}",
        encoding="utf-8",
    )
    knowledge = KnowledgeBase(tmp_path)
    hit_labels = {"mode": "keyword", "outcome": "hit"}
    miss_labels = {"mode": "keyword", "outcome": "miss"}
    hit_before = metric("smart_support_rag_searches_total", hit_labels)
    miss_before = metric("smart_support_rag_searches_total", miss_labels)
    assert knowledge.search(title)
    assert knowledge.search("unrelated quantum topic") == []
    assert metric("smart_support_rag_searches_total", hit_labels) == hit_before + 1
    assert metric("smart_support_rag_searches_total", miss_labels) == miss_before + 1


def test_tool_metrics_distinguish_success_and_policy_blocks(monkeypatch) -> None:
    class RepositoryStub:
        def tool_order(self, order_id: str, user_id: str) -> dict:
            if order_id == "blocked":
                raise CommerceError("not allowed")
            return {"order_id": order_id, "user_id": user_id}

    monkeypatch.setattr(business, "_repository", RepositoryStub())
    success_labels = {"tool": "get_order", "status": "success"}
    blocked_labels = {"tool": "get_order", "status": "blocked"}
    success_before = metric("smart_support_tool_calls_total", success_labels)
    blocked_before = metric("smart_support_tool_calls_total", blocked_labels)
    assert business.get_order("allowed", "user")["order_id"] == "allowed"
    with pytest.raises(business.BusinessRuleError):
        business.get_order("blocked", "user")
    assert metric("smart_support_tool_calls_total", success_labels) == success_before + 1
    assert metric("smart_support_tool_calls_total", blocked_labels) == blocked_before + 1


def test_graph_records_route_and_human_intervention(tmp_path: Path) -> None:
    graph = SupportGraph(SupportAgent(KnowledgeBase(tmp_path)))
    labels = {"route": "handoff", "outcome": "human_required"}
    handoff_labels = {"route": "handoff"}
    runs_before = metric("smart_support_agent_runs_total", labels)
    handoffs_before = metric("smart_support_agent_handoffs_total", handoff_labels)
    response = graph.respond("\u6211\u8981\u4eba\u5de5\u5ba2\u670d", "user", "session")
    assert response.needs_human is True
    assert metric("smart_support_agent_runs_total", labels) == runs_before + 1
    assert metric("smart_support_agent_handoffs_total", handoff_labels) == handoffs_before + 1


def test_grafana_dashboard_and_provisioning_are_wired() -> None:
    dashboard_path = ROOT / "ops" / "grafana" / "dashboards" / "smart-support-agent-overview.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "smart-support-agent-overview"
    assert dashboard["title"] == "SmartSupport Agent Overview"
    assert len(dashboard["panels"]) >= 15
    assert all(panel["datasource"]["uid"] == "prometheus" for panel in dashboard["panels"])

    datasource = (ROOT / "ops" / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text(encoding="utf-8")
    provider = (ROOT / "ops" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml").read_text(encoding="utf-8")
    prometheus = (ROOT / "ops" / "prometheus.yml").read_text(encoding="utf-8")
    assert "uid: prometheus" in datasource
    assert "url: http://prometheus:9090" in datasource
    assert "/var/lib/grafana/dashboards" in provider
    assert "/etc/prometheus/rules/*.yml" in prometheus
