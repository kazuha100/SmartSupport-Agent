from __future__ import annotations

import json
import math
from collections import Counter
from datetime import timezone
from uuid import uuid4

from sqlalchemy import select, text

from app.database import (
    ConversationRecord,
    KnowledgeGapClusterRecord,
    KnowledgeGapMemberRecord,
    MessageRecord,
    UserRecord,
)
from app.rag.embeddings import EmbeddingProvider
from app.repository import Repository
from app.routing import is_general_chat


def is_knowledge_gap(question: str, metadata: dict) -> bool:
    return (
        metadata.get("intent") in {"knowledge_qa", "general_chat"}
        and not is_general_chat(question)
        and not metadata.get("citations")
    )


class KnowledgeGapService:
    def __init__(self, repository: Repository, embedding_provider: EmbeddingProvider, threshold: float = 0.82):
        self.repository = repository
        self.database = repository.database
        self.embedding_provider = embedding_provider
        self.threshold = threshold

    def cluster_message(self, message_id: int, question: str, product_id: str | None) -> str:
        contextualized = f"商品：{product_id or '通用'}\n问题：{question.strip()}"
        vector = self.embedding_provider.encode([contextualized])[0]
        partition = product_id or "__general__"

        with self.database.session_factory() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:partition))"),
                {"partition": f"knowledge-gap:{partition}"},
            )
            existing = session.scalar(
                select(KnowledgeGapMemberRecord).where(KnowledgeGapMemberRecord.message_id == message_id)
            )
            if existing is not None:
                return existing.cluster_id

            message = session.get(MessageRecord, message_id)
            if message is None:
                raise ValueError(f"Message {message_id} does not exist")

            distance = KnowledgeGapClusterRecord.embedding.cosine_distance(vector)
            query = select(KnowledgeGapClusterRecord, (1 - distance).label("similarity")).where(
                KnowledgeGapClusterRecord.status == "open",
                KnowledgeGapClusterRecord.product_id == product_id,
            ).order_by(distance).limit(1)
            candidate = session.execute(query).first()

            similarity = float(candidate.similarity) if candidate else 0.0
            if candidate and similarity >= self.threshold:
                cluster = candidate[0]
                cluster.embedding = self._updated_centroid(
                    list(cluster.embedding), vector, cluster.occurrence_count
                )
                cluster.occurrence_count += 1
                cluster.last_seen_at = message.created_at
            else:
                cluster = KnowledgeGapClusterRecord(
                    cluster_id=f"KGC-{uuid4().hex[:16].upper()}",
                    product_id=product_id,
                    representative_question=question.strip(),
                    embedding=vector,
                    embedding_model=self.embedding_provider.model_name,
                    occurrence_count=1,
                    first_seen_at=message.created_at,
                    last_seen_at=message.created_at,
                )
                session.add(cluster)
                similarity = 1.0

            session.add(KnowledgeGapMemberRecord(
                cluster_id=cluster.cluster_id,
                message_id=message_id,
                original_question=question.strip(),
                similarity=similarity,
            ))
            session.commit()
            return cluster.cluster_id

    def backfill(self, limit: int = 200) -> int:
        pending = self._unclustered_gaps(limit)
        for item in pending:
            self.cluster_message(item["message_id"], item["question"], item["product_id"])
        return len(pending)

    def clusters(self, limit: int = 12) -> list[dict]:
        with self.database.session_factory() as session:
            clusters = session.scalars(
                select(KnowledgeGapClusterRecord)
                .where(KnowledgeGapClusterRecord.status == "open")
                .order_by(
                    KnowledgeGapClusterRecord.occurrence_count.desc(),
                    KnowledgeGapClusterRecord.last_seen_at.desc(),
                )
                .limit(limit)
            ).all()
            user_names = {item.user_id: item.display_name for item in session.scalars(select(UserRecord)).all()}
            results = []
            for cluster in clusters:
                rows = session.execute(
                    select(KnowledgeGapMemberRecord, MessageRecord, ConversationRecord)
                    .join(MessageRecord, MessageRecord.id == KnowledgeGapMemberRecord.message_id)
                    .join(ConversationRecord, ConversationRecord.id == MessageRecord.conversation_id)
                    .where(KnowledgeGapMemberRecord.cluster_id == cluster.cluster_id)
                    .order_by(MessageRecord.created_at.desc())
                ).all()
                variants = Counter(member.original_question for member, _, _ in rows)
                occurrences = []
                for member, message, conversation in rows:
                    created_at = message.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    occurrences.append({
                        "message_id": message.id,
                        "session_id": conversation.session_id,
                        "user_id": conversation.user_id,
                        "display_name": user_names.get(conversation.user_id, conversation.user_id),
                        "product_id": conversation.product_id,
                        "order_id": conversation.order_id,
                        "conversation_status": conversation.status,
                        "question": member.original_question,
                        "similarity": round(member.similarity, 4),
                        "asked_at": created_at.isoformat(),
                    })
                last_seen_at = cluster.last_seen_at
                if last_seen_at.tzinfo is None:
                    last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
                results.append({
                    "cluster_id": cluster.cluster_id,
                    "question": cluster.representative_question,
                    "product_id": cluster.product_id,
                    "count": cluster.occurrence_count,
                    "last_asked_at": last_seen_at.isoformat(),
                    "variants": [
                        {"question": question, "count": count}
                        for question, count in variants.most_common()
                    ],
                    "occurrences": occurrences,
                })
            return results

    def _unclustered_gaps(self, limit: int) -> list[dict]:
        with self.database.session_factory() as session:
            clustered_ids = select(KnowledgeGapMemberRecord.message_id)
            messages = session.scalars(
                select(MessageRecord)
                .where(MessageRecord.id.not_in(clustered_ids))
                .order_by(MessageRecord.conversation_id, MessageRecord.id)
            ).all()
            pending: dict[int, MessageRecord] = {}
            result: list[dict] = []
            for message in messages:
                if message.role == "user":
                    pending[message.conversation_id] = message
                    continue
                question = pending.pop(message.conversation_id, None)
                if question is None or message.role != "assistant" or not message.metadata_json:
                    continue
                try:
                    metadata = json.loads(message.metadata_json)
                except json.JSONDecodeError:
                    continue
                if not is_knowledge_gap(question.content, metadata):
                    continue
                conversation = question.conversation
                result.append({
                    "message_id": question.id,
                    "question": question.content,
                    "product_id": conversation.product_id,
                })
                if len(result) >= limit:
                    break
            return result

    @staticmethod
    def _updated_centroid(current: list[float], incoming: list[float], count: int) -> list[float]:
        combined = [((left * count) + right) / (count + 1) for left, right in zip(current, incoming)]
        norm = math.sqrt(sum(value * value for value in combined)) or 1.0
        return [value / norm for value in combined]
