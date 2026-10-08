import re
import time
from dataclasses import dataclass
from math import fsum
from pathlib import Path

import frontmatter

from app.models import Citation
from app.observability import observe_rag
from app.rag.embeddings import EmbeddingProvider
from app.repository import Repository


STOP_BIGRAMS = {
    "请问", "您好", "你好", "谢谢", "帮我", "看看", "一下", "咨询", "我想",
    "了解", "麻烦", "确认", "有个", "问题", "方便", "说明", "详细", "应该",
    "怎么", "处理", "能帮", "说说", "什么", "如何",
}


@dataclass
class KnowledgeChunk:
    chunk_id: int | None
    doc_id: str
    title: str
    section: str
    version: str
    content: str
    product_id: str | None = None
    embedding: list[float] | None = None


def _terms(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    bigrams = {"".join(chinese[i : i + 2]) for i in range(max(0, len(chinese) - 1))}
    words = set(re.findall(r"[a-z0-9_-]{2,}", normalized))
    return (bigrams - STOP_BIGRAMS) | words


class KnowledgeBase:
    def __init__(
        self,
        root: Path,
        repository: Repository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.root = root
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.chunks: list[KnowledgeChunk] = []
        self.reload()

    def reload(self) -> None:
        self.chunks = []
        if self.repository is not None:
            rows = self.repository.active_chunks()
            if self.embedding_provider is not None:
                missing = [
                    item for item in rows
                    if item["embedding"] is None or item["embedding_model"] != self.embedding_provider.model_name
                ]
                if self.repository.database.is_postgres:
                    missing = rows
                vectors = self.embedding_provider.encode(
                    [f"{item['title']}\n{item['section']}\n{item['content']}" for item in missing]
                )
                self.repository.save_embeddings(
                    self.embedding_provider.model_name,
                    [(item["chunk_id"], vector) for item, vector in zip(missing, vectors)],
                )
                if not self.repository.database.is_postgres and missing:
                    rows = self.repository.active_chunks()
            self.chunks = [
                KnowledgeChunk(
                    chunk_id=item["chunk_id"],
                    doc_id=item["doc_id"],
                    title=item["title"],
                    section=item["section"],
                    version=item["version"],
                    content=item["content"],
                    product_id=item.get("product_id"),
                    embedding=item["embedding"],
                )
                for item in rows
            ]
            return
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*.md")):
            post = frontmatter.load(path)
            metadata = post.metadata
            title = str(metadata.get("title", path.stem))
            doc_id = str(metadata.get("doc_id", path.stem))
            version = str(metadata.get("version", "1.0"))
            sections = re.split(r"(?m)^##\s+", post.content)
            intro = sections[0].replace(f"# {title}", "").strip()
            if intro:
                self.chunks.append(KnowledgeChunk(None, doc_id, title, "概述", version, intro, post.metadata.get("product_id")))
            for section in sections[1:]:
                lines = section.strip().splitlines()
                if lines:
                    self.chunks.append(
                        KnowledgeChunk(None, doc_id, title, lines[0].strip(), version, "\n".join(lines[1:]).strip(), post.metadata.get("product_id"))
                    )

    def search(self, query: str, limit: int = 4, product_id: str | None = None) -> list[Citation]:
        mode = "hybrid" if self.embedding_provider is not None and getattr(self.embedding_provider, "ready", True) else "keyword"
        started = time.perf_counter()
        try:
            results = self._search(query, limit, product_id)
        except Exception:
            observe_rag(mode, "error", time.perf_counter() - started, 0)
            raise
        observe_rag(mode, "hit" if results else "miss", time.perf_counter() - started, len(results))
        return results

    def _search(self, query: str, limit: int = 4, product_id: str | None = None) -> list[Citation]:
        candidates = [chunk for chunk in self.chunks if not product_id or chunk.product_id == product_id]
        query_terms = _terms(query)
        keyword_scores: dict[int, float] = {}
        for chunk in candidates:
            title_terms = _terms(f"{chunk.title}{chunk.section}")
            content_terms = _terms(chunk.content)
            score = len(query_terms & content_terms) + 2 * len(query_terms & title_terms)
            if score > 0:
                keyword_scores[id(chunk)] = float(score)

        if self.embedding_provider is None or not getattr(self.embedding_provider, "ready", True):
            scored = [
                (score, chunk)
                for chunk in candidates
                if (score := keyword_scores.get(id(chunk), 0)) >= 2
            ]
            return self._citations(scored, limit)

        query_vector = self.embedding_provider.encode([query])[0]
        vector_scores: dict[tuple[str, str, str], float] = {}
        if self.repository is not None and self.repository.database.is_postgres:
            vector_scores = {
                (item["doc_id"], item["section"], item["content"]): float(item["vector_score"])
                for item in self.repository.postgres_vector_search(query_vector, max(limit * 4, 16))
            }

        max_keyword = max(keyword_scores.values(), default=1.0)
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in candidates:
            key = (chunk.doc_id, chunk.section, chunk.content)
            if chunk.embedding is not None:
                vector_score = fsum(left * right for left, right in zip(query_vector, chunk.embedding))
            else:
                vector_score = vector_scores.get(key, 0.0)
            keyword_score = keyword_scores.get(id(chunk), 0.0) / max_keyword
            combined = 0.72 * max(0.0, vector_score) + 0.28 * keyword_score
            if combined >= 0.34 or keyword_score >= 0.5:
                scored.append((combined, chunk))
        return self._citations(scored, limit)

    @staticmethod
    def _citations(scored: list[tuple[float, KnowledgeChunk]], limit: int) -> list[Citation]:
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return []
        max_score = scored[0][0]
        return [
            Citation(
                doc_id=chunk.doc_id,
                title=chunk.title,
                section=chunk.section,
                version=chunk.version,
                excerpt=chunk.content[:180],
                score=round(score / max_score, 2),
            )
            for score, chunk in scored[:limit]
        ]
