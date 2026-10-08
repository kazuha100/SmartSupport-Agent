import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.routing import Match


HTTP_REQUESTS = Counter(
    "smart_support_http_requests_total",
    "HTTP requests processed by SmartSupport Agent",
    ("method", "path", "status"),
)
HTTP_LATENCY = Histogram(
    "smart_support_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "path"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_IN_PROGRESS = Gauge(
    "smart_support_http_requests_in_progress",
    "HTTP requests currently being processed",
    ("method", "path"),
)

AGENT_RUNS = Counter(
    "smart_support_agent_runs_total",
    "LangGraph agent runs",
    ("route", "outcome"),
)
AGENT_LATENCY = Histogram(
    "smart_support_agent_duration_seconds",
    "LangGraph agent run latency",
    ("route",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
AGENT_CONFIDENCE = Histogram(
    "smart_support_agent_confidence",
    "Confidence reported by completed agent runs",
    ("route",),
    buckets=(0.25, 0.5, 0.65, 0.75, 0.85, 0.9, 0.95, 0.99, 1.0),
)
AGENT_HANDOFFS = Counter(
    "smart_support_agent_handoffs_total",
    "Agent runs requiring human intervention",
    ("route",),
)

LLM_CALLS = Counter(
    "smart_support_llm_calls_total",
    "Language model calls",
    ("model", "operation", "stream", "status"),
)
LLM_LATENCY = Histogram(
    "smart_support_llm_duration_seconds",
    "Language model call latency",
    ("model", "operation", "stream"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60),
)
LLM_TTFT = Histogram(
    "smart_support_llm_time_to_first_token_seconds",
    "Time to first token for streaming language model calls",
    ("model", "operation"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30),
)
LLM_TOKENS = Counter(
    "smart_support_llm_tokens_total",
    "Language model tokens reported by the provider",
    ("model", "type"),
)

RAG_SEARCHES = Counter(
    "smart_support_rag_searches_total",
    "Knowledge-base searches",
    ("mode", "outcome"),
)
RAG_LATENCY = Histogram(
    "smart_support_rag_duration_seconds",
    "Knowledge-base search latency",
    ("mode",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
RAG_RESULTS = Histogram(
    "smart_support_rag_results",
    "Knowledge chunks returned by a search",
    ("mode",),
    buckets=(0, 1, 2, 3, 4, 5, 10, 20),
)

TOOL_CALLS = Counter(
    "smart_support_tool_calls_total",
    "Executed business tool calls",
    ("tool", "status"),
)
TOOL_LATENCY = Histogram(
    "smart_support_tool_duration_seconds",
    "Executed business tool latency",
    ("tool",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

EXCLUDED_HTTP_PATHS = frozenset(("/metrics", "/health", "/health/ready"))


def _route_template(request) -> str:
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", "unmatched")
    return "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = _route_template(request)
        if path in EXCLUDED_HTTP_PATHS:
            return await call_next(request)

        method = request.method
        started = time.perf_counter()
        status = "500"
        HTTP_IN_PROGRESS.labels(method, path).inc()
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            elapsed = time.perf_counter() - started
            HTTP_IN_PROGRESS.labels(method, path).dec()
            HTTP_REQUESTS.labels(method, path, status).inc()
            HTTP_LATENCY.labels(method, path).observe(elapsed)


def observe_agent(
    route: str,
    outcome: str,
    duration_seconds: float,
    confidence: float | None = None,
    needs_human: bool = False,
) -> None:
    AGENT_RUNS.labels(route, outcome).inc()
    AGENT_LATENCY.labels(route).observe(duration_seconds)
    if confidence is not None:
        AGENT_CONFIDENCE.labels(route).observe(max(0.0, min(1.0, confidence)))
    if needs_human:
        AGENT_HANDOFFS.labels(route).inc()


def observe_llm(
    model: str,
    operation: str,
    stream: bool,
    status: str,
    duration_seconds: float,
    *,
    time_to_first_token_seconds: float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    stream_label = "true" if stream else "false"
    LLM_CALLS.labels(model, operation, stream_label, status).inc()
    LLM_LATENCY.labels(model, operation, stream_label).observe(duration_seconds)
    if time_to_first_token_seconds is not None:
        LLM_TTFT.labels(model, operation).observe(time_to_first_token_seconds)
    if prompt_tokens is not None:
        LLM_TOKENS.labels(model, "prompt").inc(max(0, prompt_tokens))
    if completion_tokens is not None:
        LLM_TOKENS.labels(model, "completion").inc(max(0, completion_tokens))


def observe_rag(mode: str, outcome: str, duration_seconds: float, result_count: int) -> None:
    RAG_SEARCHES.labels(mode, outcome).inc()
    RAG_LATENCY.labels(mode).observe(duration_seconds)
    RAG_RESULTS.labels(mode).observe(max(0, result_count))


def observe_tool(tool: str, status: str, duration_seconds: float) -> None:
    TOOL_CALLS.labels(tool, status).inc()
    TOOL_LATENCY.labels(tool).observe(duration_seconds)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
