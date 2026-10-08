import json

import httpx
import pytest

from app.llm import DeepSeekClient, ModelError
from app.models import Citation


def test_deepseek_client_builds_grounded_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-chat"
        assert "七天无理由退货政策" in payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "可以申请退货。[资料1]"}}]},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-chat",
        http_client=http_client,
    )
    citation = Citation(
        doc_id="refund_001",
        title="七天无理由退货政策",
        section="概述",
        version="1.2",
        excerpt="商品签收后七日内可以申请。",
        score=1.0,
    )

    assert model.answer_with_sources("可以退货吗？", [citation]) == "可以申请退货。[资料1]"
    http_client.close()


def test_deepseek_client_streams_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        body = (
            'data: {"choices":[{"delta":{"content":"可以"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"退货"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-chat",
        http_client=http_client,
    )
    citation = Citation(
        doc_id="refund_001",
        title="退货政策",
        section="概述",
        version="1.0",
        excerpt="七日内可以退货。",
        score=1.0,
    )

    assert "".join(model.stream_answer_with_sources("能退货吗？", [citation])) == "可以退货"
    http_client.close()


def test_deepseek_client_returns_structured_intent_prediction() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert "refund_request" in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({
                    "route": "service",
                    "intent": "policy_question",
                    "confidence": 0.97,
                    "entities": {},
                    "candidate_intents": [],
                    "requires_clarification": False,
                    "clarification_question": None,
                    "reason": "用户只咨询政策",
                }, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 12},
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-chat",
        http_client=http_client,
    )

    prediction = model.classify_intent("我不想退款，只想了解退款政策")
    assert prediction.intent == "policy_question"
    assert prediction.route == "service"
    assert prediction.confidence == 0.97
    assert prediction.reason == "用户只咨询政策"
    http_client.close()


def test_deepseek_client_rejects_invalid_intent_json() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
    ))
    model = DeepSeekClient(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-chat",
        http_client=http_client,
    )

    with pytest.raises(ModelError):
        model.classify_intent("测试")
    http_client.close()
