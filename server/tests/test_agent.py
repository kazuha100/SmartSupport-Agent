from pathlib import Path

from app.agent.service import SupportAgent
from app.rag.retriever import KnowledgeBase


ROOT = Path(__file__).resolve().parents[2]
agent = SupportAgent(KnowledgeBase(ROOT / "knowledge-base"))


def test_knowledge_answer_has_citation() -> None:
    response = agent.respond("七天无理由退货有什么要求？", "demo-user")
    assert response.intent == "knowledge_qa"
    assert response.citations
    assert response.needs_human is False


def test_product_answer_uses_matching_document() -> None:
    response = agent.respond("商品 P-C3 支持主动降噪吗？", "registered-user")
    assert response.intent == "knowledge_qa"
    assert any(item.doc_id == "product_c3" for item in response.citations)
    assert "主动降噪" in response.answer


def test_small_talk_does_not_create_handoff() -> None:
    greeting = agent.respond("客服你好啊", "demo-user")
    handoff = agent.respond("帮我转人工客服", "demo-user")

    assert greeting.intent == "general_chat"
    assert greeting.needs_human is False
    assert "很高兴" in greeting.answer
    assert len(greeting.answer) > 25
    assert handoff.intent == "human_handoff"
    assert handoff.needs_human is True
