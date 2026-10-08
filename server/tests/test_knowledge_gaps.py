from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.database import (
    ConversationRecord,
    Database,
    KnowledgeGapClusterRecord,
    KnowledgeGapMemberRecord,
    MessageRecord,
)
from app.knowledge_gaps import KnowledgeGapService
from app.models import ChatResponse, Citation
from app.repository import Repository


class FakeEmbeddingProvider:
    model_name = "fake-bge-zh-512"
    dimension = 512
    ready = True

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            if any(word in text for word in ("防水", "碰到水", "进水")):
                vector[0] = 1.0
            elif any(word in text for word in ("续航", "电池")):
                vector[1] = 1.0
            else:
                vector[2] = 1.0
            vectors.append(vector)
        return vectors


def add_question(database: Database, session_id: str, question: str, product_id: str | None) -> int:
    with database.session_factory() as session:
        conversation = ConversationRecord(
            session_id=session_id,
            user_id="customer-1",
            product_id=product_id,
        )
        session.add(conversation)
        session.flush()
        message = MessageRecord(
            conversation_id=conversation.id,
            role="user",
            content=question,
            sender_type="customer",
            sender_id="customer-1",
            sender_name="测试用户",
        )
        session.add(message)
        session.commit()
        return message.id


def make_service(database: Database) -> KnowledgeGapService:
    return KnowledgeGapService(Repository(database), FakeEmbeddingProvider(), threshold=0.82)


def test_same_product_paraphrases_merge(postgres_database: Database) -> None:
    service = make_service(postgres_database)
    first = add_question(postgres_database, "gap-1", "P-C3 支持防水吗？", "P-C3")
    second = add_question(postgres_database, "gap-2", "这个耳机碰到水会坏吗？", "P-C3")

    assert service.cluster_message(first, "P-C3 支持防水吗？", "P-C3") == service.cluster_message(
        second, "这个耳机碰到水会坏吗？", "P-C3"
    )
    cluster = service.clusters()[0]
    assert cluster["count"] == 2
    assert cluster["product_id"] == "P-C3"
    assert {item["question"] for item in cluster["variants"]} == {
        "P-C3 支持防水吗？",
        "这个耳机碰到水会坏吗？",
    }
    assert {item["question"] for item in cluster["occurrences"]} == {
        "P-C3 支持防水吗？",
        "这个耳机碰到水会坏吗？",
    }


def test_product_partition_and_semantics_prevent_false_merges(postgres_database: Database) -> None:
    service = make_service(postgres_database)
    questions = [
        ("partition-1", "这款耳机防水吗？", "P-C3"),
        ("partition-2", "这款耳机防水吗？", "P-C5"),
        ("partition-3", "这款耳机续航多久？", "P-C3"),
    ]
    for session_id, question, product_id in questions:
        message_id = add_question(postgres_database, session_id, question, product_id)
        service.cluster_message(message_id, question, product_id)

    assert len(service.clusters()) == 3


def test_duplicate_message_is_idempotent(postgres_database: Database) -> None:
    service = make_service(postgres_database)
    message_id = add_question(postgres_database, "idempotent", "P-C3 防水吗？", "P-C3")

    first = service.cluster_message(message_id, "P-C3 防水吗？", "P-C3")
    second = service.cluster_message(message_id, "P-C3 防水吗？", "P-C3")

    assert first == second
    with postgres_database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeGapMemberRecord)) == 1
        assert session.scalar(select(KnowledgeGapClusterRecord.occurrence_count)) == 1


def test_concurrent_writes_create_one_cluster(postgres_database: Database) -> None:
    service = make_service(postgres_database)
    entries = [
        (add_question(postgres_database, f"concurrent-{index}", question, "P-C3"), question)
        for index, question in enumerate(("P-C3 支持防水吗？", "这个耳机碰到水会坏吗？"))
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        cluster_ids = list(executor.map(lambda item: service.cluster_message(item[0], item[1], "P-C3"), entries))

    assert len(set(cluster_ids)) == 1
    assert service.clusters()[0]["count"] == 2


def test_backfill_only_processes_uncovered_knowledge_questions(postgres_database: Database) -> None:
    repository = Repository(postgres_database)
    service = make_service(postgres_database)
    uncovered = ChatResponse(answer="暂无资料", intent="knowledge_qa", confidence=0.4)
    covered = ChatResponse(
        answer="支持 IPX4 防水",
        intent="knowledge_qa",
        confidence=0.95,
        citations=[Citation(doc_id="product-c3", title="C3", section="规格", version="1", excerpt="IPX4", score=0.9)],
    )
    first = repository.record_chat_turn("backfill-1", "customer-1", "测试用户", "P-C3 防水吗？", uncovered)
    repository.record_chat_turn("backfill-2", "customer-1", "测试用户", "P-C3 支持降噪吗？", covered)

    assert service.backfill() == 1
    assert service.clusters()[0]["occurrences"][0]["message_id"] == first["message_id"]


def test_product_id_recovers_from_request_text_and_conversation(postgres_database: Database) -> None:
    repository = Repository(postgres_database)
    response = ChatResponse(answer="暂无资料", intent="knowledge_qa", confidence=0.4)

    explicit = repository.record_chat_turn(
        "product-explicit", "customer-1", "测试用户", "它防水吗？", response, product_id="P-C3"
    )
    parsed = repository.record_chat_turn(
        "product-parsed", "customer-1", "测试用户", "P-S8 防水吗？", response
    )
    repository.record_chat_turn(
        "product-context", "customer-1", "测试用户", "P-C65 有保修吗？", response
    )
    contextual = repository.record_chat_turn(
        "product-context", "customer-1", "测试用户", "碰到水会坏吗？", response
    )

    assert explicit["product_id"] == "P-C3"
    assert parsed["product_id"] == "P-S8"
    assert contextual["product_id"] == "P-C65"
