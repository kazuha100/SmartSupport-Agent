from pathlib import Path

from app.database import Database
from app.documents import DocumentService
from app.rag.retriever import KnowledgeBase
from app.repository import Repository


class ColdEmbeddingProvider:
    model_name = "cold-test-model"
    dimension = 512
    ready = False

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("cold embedding provider must not block keyword retrieval")


def make_service(tmp_path: Path, database: Database) -> tuple[DocumentService, Repository]:
    repository = Repository(database)
    return DocumentService(repository, tmp_path / "uploads"), repository


def test_upload_disable_and_delete_document(tmp_path: Path, postgres_database: Database) -> None:
    service, repository = make_service(tmp_path, postgres_database)
    document = service.upload(
        "warranty.md",
        "# 延长保修政策\n\n购买延保服务后，保修期增加十二个月。".encode(),
        "延长保修政策",
        "1.0",
        "public",
    )

    assert document["chunk_count"] == 1
    assert any(chunk["doc_id"] == document["doc_id"] for chunk in repository.active_chunks())

    repository.set_document_status(document["doc_id"], "disabled")
    assert all(chunk["doc_id"] != document["doc_id"] for chunk in repository.active_chunks())

    existing = repository.get_document(document["doc_id"])
    assert existing is not None
    deleted = repository.delete_document(document["doc_id"])
    service.delete_source(existing)
    assert deleted is not None
    assert repository.get_document(document["doc_id"]) is None


def test_rejects_unsupported_upload(tmp_path: Path, postgres_database: Database) -> None:
    service, _ = make_service(tmp_path, postgres_database)

    try:
        service.upload("script.exe", b"not allowed", None, "1.0", "public")
    except ValueError as exc:
        assert "仅支持" in str(exc)
    else:
        raise AssertionError("unsupported file should be rejected")


def test_uploaded_document_enters_and_leaves_retrieval(tmp_path: Path, postgres_database: Database) -> None:
    service, repository = make_service(tmp_path, postgres_database)
    document = service.upload(
        "special-policy.txt",
        "火星配送服务需要提前九十天预约。".encode(),
        "火星配送政策",
        "1.0",
        "public",
    )
    knowledge_base = KnowledgeBase(tmp_path, repository)

    assert knowledge_base.search("火星配送怎么预约？")[0].doc_id == document["doc_id"]

    repository.set_document_status(document["doc_id"], "disabled")
    knowledge_base.reload()
    assert knowledge_base.search("火星配送怎么预约？") == []


def test_pgvector_search_returns_embedded_chunk(tmp_path: Path, postgres_database: Database) -> None:
    service, repository = make_service(tmp_path, postgres_database)
    document = service.upload(
        "vector-policy.txt",
        "耳机支持基础防泼溅，但不能浸泡。".encode(),
        "耳机防水政策",
        "1.0",
        "public",
    )
    chunk = next(item for item in repository.active_chunks() if item["doc_id"] == document["doc_id"])
    vector = [1.0] + [0.0] * 511
    repository.save_embeddings("fake-bge-512", [(chunk["chunk_id"], vector)])

    results = repository.postgres_vector_search(vector, 3)

    assert results
    assert results[0]["doc_id"] == document["doc_id"]
    assert results[0]["vector_score"] == 1.0


def test_cold_embedding_provider_falls_back_to_keyword_retrieval() -> None:
    root = Path(__file__).resolve().parents[2] / "knowledge-base"
    knowledge_base = KnowledgeBase(root, embedding_provider=ColdEmbeddingProvider())

    results = knowledge_base.search("七天无理由退货有什么要求？")

    assert results
    assert results[0].doc_id == "refund_001"
