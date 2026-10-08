import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import selectinload

from app.database import (
    AppealAttachmentRecord,
    AppealEventRecord,
    AppealMaterialRequestRecord,
    AppealRecord,
    AuditLogRecord,
    ConversationRecord,
    ConversationNoteRecord,
    ConversationRatingRecord,
    Database,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    MessageRecord,
    ModelObservationRecord,
    TicketRecord,
    TicketReplyRecord,
    QuickReplyRecord,
    UserRecord,
)
from app.models import ChatResponse
from app.routing import is_general_chat


class Repository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_document(self, document: dict, chunks: list[dict]) -> tuple[dict, bool]:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(KnowledgeDocumentRecord)
                .options(selectinload(KnowledgeDocumentRecord.chunks))
                .where(KnowledgeDocumentRecord.doc_id == document["doc_id"])
            )
            created = record is None
            if record is None:
                record = KnowledgeDocumentRecord(doc_id=document["doc_id"])
                session.add(record)
            elif record.content_hash == document["content_hash"]:
                return self._document_dict(record), False

            for key in (
                "title", "file_name", "source_type", "source_path", "version", "status",
                "visibility", "product_id", "document_category", "content_hash", "content_text", "size_bytes",
            ):
                setattr(record, key, document[key])
            record.updated_at = datetime.now(timezone.utc)
            for existing_chunk in list(record.chunks):
                session.delete(existing_chunk)
            session.flush()
            record.chunks.clear()
            record.chunks.extend(
                KnowledgeChunkRecord(section=item["section"], content=item["content"], position=index)
                for index, item in enumerate(chunks)
            )
            session.commit()
            session.refresh(record)
            return self._document_dict(record), created

    def create_user_if_missing(self, user: dict) -> dict:
        with self.database.session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.username == user["username"]))
            if record is None:
                record = UserRecord(**user)
                session.add(record)
                session.commit()
            return self._user_dict(record)

    def get_user_by_username(self, username: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.username == username))
            return self._user_dict(record) if record else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.user_id == user_id))
            return self._user_dict(record) if record else None

    def update_user_display_name(self, username: str, display_name: str) -> None:
        with self.database.session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.username == username))
            if record:
                record.display_name = display_name
                session.commit()

    def consolidate_staff_accounts(self, primary_username: str, legacy_usernames: tuple[str, ...]) -> None:
        with self.database.session_factory() as session:
            primary = session.scalar(select(UserRecord).where(UserRecord.username == primary_username))
            if not primary:
                return
            for username in legacy_usernames:
                legacy = session.scalar(select(UserRecord).where(UserRecord.username == username))
                if not legacy or legacy.user_id == primary.user_id:
                    continue
                legacy_id = legacy.user_id
                identity_updates = (
                    (ConversationRecord, ConversationRecord.assigned_to, {"assigned_to": primary.user_id}),
                    (TicketRecord, TicketRecord.assigned_to, {"assigned_to": primary.user_id}),
                    (AppealRecord, AppealRecord.assigned_to, {"assigned_to": primary.user_id, "assigned_name": primary.display_name}),
                    (AppealAttachmentRecord, AppealAttachmentRecord.reviewed_by, {"reviewed_by": primary.user_id, "reviewed_name": primary.display_name}),
                    (AppealMaterialRequestRecord, AppealMaterialRequestRecord.requested_by, {"requested_by": primary.user_id, "requested_name": primary.display_name}),
                    (AppealEventRecord, AppealEventRecord.actor_id, {"actor_id": primary.user_id, "actor_name": primary.display_name}),
                    (ConversationNoteRecord, ConversationNoteRecord.author_id, {"author_id": primary.user_id, "author_name": primary.display_name}),
                    (TicketReplyRecord, TicketReplyRecord.author_id, {"author_id": primary.user_id}),
                    (MessageRecord, MessageRecord.sender_id, {"sender_id": primary.user_id, "sender_name": primary.display_name}),
                    (AuditLogRecord, AuditLogRecord.actor_id, {"actor_id": primary.user_id}),
                )
                for model, field, values in identity_updates:
                    session.execute(update(model).where(field == legacy_id).values(**values))
                session.delete(legacy)
            session.commit()

    def list_documents(self) -> list[dict]:
        with self.database.session_factory() as session:
            records = session.scalars(
                select(KnowledgeDocumentRecord)
                .options(selectinload(KnowledgeDocumentRecord.chunks))
                .order_by(KnowledgeDocumentRecord.updated_at.desc())
            ).all()
            return [self._document_dict(record) for record in records]

    def get_document(self, doc_id: str, include_chunks: bool = False) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(KnowledgeDocumentRecord)
                .options(selectinload(KnowledgeDocumentRecord.chunks))
                .where(KnowledgeDocumentRecord.doc_id == doc_id)
            )
            if not record:
                return None
            result = self._document_dict(record)
            if include_chunks:
                result["content"] = record.content_text
                result["chunks"] = [
                    {"position": chunk.position, "section": chunk.section, "content": chunk.content}
                    for chunk in record.chunks
                ]
            return result

    def set_document_status(self, doc_id: str, status: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(KnowledgeDocumentRecord)
                .options(selectinload(KnowledgeDocumentRecord.chunks))
                .where(KnowledgeDocumentRecord.doc_id == doc_id)
            )
            if not record:
                return None
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._document_dict(record)

    def delete_document(self, doc_id: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(KnowledgeDocumentRecord)
                .options(selectinload(KnowledgeDocumentRecord.chunks))
                .where(KnowledgeDocumentRecord.doc_id == doc_id)
            )
            if not record:
                return None
            result = self._document_dict(record)
            session.delete(record)
            session.commit()
            return result

    def active_chunks(self) -> list[dict]:
        with self.database.session_factory() as session:
            rows = session.execute(
                select(KnowledgeDocumentRecord, KnowledgeChunkRecord)
                .select_from(KnowledgeDocumentRecord)
                .join(
                    KnowledgeChunkRecord,
                    KnowledgeChunkRecord.document_id == KnowledgeDocumentRecord.id,
                )
                .where(KnowledgeDocumentRecord.status == "active")
                .order_by(KnowledgeDocumentRecord.id, KnowledgeChunkRecord.position)
            ).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "doc_id": document.doc_id,
                    "title": document.title,
                    "product_id": document.product_id,
                    "version": document.version,
                    "section": chunk.section,
                    "content": chunk.content,
                    "embedding": list(chunk.embedding) if chunk.embedding is not None else None,
                    "embedding_model": chunk.embedding_model,
                }
                for document, chunk in rows
            ]

    def save_embeddings(self, model: str, values: list[tuple[int, list[float]]]) -> None:
        if not values:
            return
        with self.database.session_factory() as session:
            for chunk_id, vector in values:
                record = session.get(KnowledgeChunkRecord, chunk_id)
                if record is not None:
                    record.embedding = vector
                    record.embedding_model = model
            session.commit()

    def postgres_vector_search(self, vector: list[float], limit: int) -> list[dict]:
        vector_text = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
        sql = text(
            """
            SELECT d.doc_id, d.title, d.version, c.section, c.content,
                   1 - (c.embedding <=> CAST(:vector AS vector)) AS vector_score
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE d.status = 'active' AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:vector AS vector)
            LIMIT :limit
            """
        )
        with self.database.engine.connect() as connection:
            return [dict(row._mapping) for row in connection.execute(sql, {"vector": vector_text, "limit": limit})]

    def record_chat_turn(
        self,
        session_id: str,
        user_id: str,
        display_name: str,
        message: str,
        response: ChatResponse,
        product_id: str | None = None,
        order_id: str | None = None,
    ) -> dict:
        with self.database.session_factory() as session:
            conversation = session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.session_id == session_id,
                    ConversationRecord.user_id == user_id,
                )
            )
            if conversation is None:
                now = datetime.now(timezone.utc)
                high = response.needs_human or response.intent in {"refund_request", "human_handoff", "account_security"}
                conversation = ConversationRecord(
                    session_id=session_id,
                    user_id=user_id,
                    priority="high" if high else "normal",
                    status="waiting_human" if response.needs_human else "bot_active",
                    product_id=product_id,
                    order_id=order_id,
                    first_response_due_at=now + timedelta(minutes=5 if high else 15),
                    resolve_due_at=now + timedelta(hours=2 if high else 24),
                )
                session.add(conversation)
                session.flush()
            product_match = re.search(r"\bP-[A-Z0-9]+\b", message.upper())
            resolved_product_id = product_id or (product_match.group(0) if product_match else None) or conversation.product_id
            conversation.product_id = resolved_product_id
            conversation.order_id = order_id or conversation.order_id
            if response.needs_human and conversation.status != "human_active":
                conversation.status = "waiting_human"
                conversation.priority = "high"
            conversation.updated_at = datetime.now(timezone.utc)
            user_message = MessageRecord(
                conversation_id=conversation.id, role="user", content=message,
                sender_type="customer", sender_id=user_id, sender_name=display_name,
            )
            assistant_message = MessageRecord(
                conversation_id=conversation.id, role="assistant", content=response.answer,
                metadata_json=response.model_dump_json(),
                sender_type="ai", sender_id="support-orchestrator", sender_name="智能客服",
            )
            session.add_all([user_message, assistant_message])
            session.flush()
            result = {
                "message_id": user_message.id,
                "product_id": resolved_product_id,
                "order_id": conversation.order_id,
                "question": message,
            }
            session.commit()
            return result

    def record_customer_message(self, session_id: str, user_id: str, display_name: str, message: str) -> dict:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if conversation is None:
                raise ValueError("会话不存在")
            session.add(MessageRecord(
                conversation_id=conversation.id, role="user", content=message,
                sender_type="customer", sender_id=user_id, sender_name=display_name,
            ))
            conversation.suggested_reply = self._suggest_reply(message, conversation.product_id, conversation.order_id)
            conversation.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._conversation_summary(conversation, display_name, [])

    def record_product_share(
        self,
        session_id: str,
        user_id: str,
        display_name: str,
        product: dict,
    ) -> dict:
        product_id = product["product_id"]
        with self.database.session_factory() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"product-share:{user_id}:{session_id}:{product_id}"},
            )
            conversation = session.scalar(
                select(ConversationRecord)
                .options(selectinload(ConversationRecord.messages))
                .where(
                    ConversationRecord.session_id == session_id,
                    ConversationRecord.user_id == user_id,
                )
            )
            if conversation is None:
                now = datetime.now(timezone.utc)
                conversation = ConversationRecord(
                    session_id=session_id,
                    user_id=user_id,
                    status="bot_active",
                    priority="normal",
                    product_id=product_id,
                    first_response_due_at=now + timedelta(minutes=15),
                    resolve_due_at=now + timedelta(hours=24),
                )
                session.add(conversation)
                session.flush()

            for existing in conversation.messages:
                if not existing.metadata_json or existing.sender_type != "customer":
                    continue
                try:
                    metadata = json.loads(existing.metadata_json)
                except json.JSONDecodeError:
                    continue
                if metadata.get("type") == "product" and metadata.get("product", {}).get("product_id") == product_id:
                    return {"created": False, "message_id": existing.id, "product_id": product_id}

            snapshot = {
                "product_id": product_id,
                "name": product["name"],
                "category": product["category"],
                "description": product["description"],
                "price_cents": product["price_cents"],
                "image_url": product["image_url"],
            }
            message = MessageRecord(
                conversation_id=conversation.id,
                role="user",
                content=f"我想了解这款商品：{product['name']}",
                metadata_json=json.dumps({"type": "product", "product": snapshot}, ensure_ascii=False),
                sender_type="customer",
                sender_id=user_id,
                sender_name=display_name,
            )
            conversation.product_id = product_id
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(message)
            session.flush()
            result = {"created": True, "message_id": message.id, "product_id": product_id}
            session.commit()
            return result

    def conversation_messages(self, session_id: str, user_id: str) -> list[dict]:
        with self.database.session_factory() as session:
            conversation = session.scalar(
                select(ConversationRecord)
                .options(selectinload(ConversationRecord.messages))
                .where(
                    ConversationRecord.session_id == session_id,
                    ConversationRecord.user_id == user_id,
                )
            )
            if conversation is None:
                return []
            result = []
            for message in sorted(conversation.messages, key=lambda item: (item.created_at, item.id)):
                metadata = json.loads(message.metadata_json) if message.metadata_json else None
                result.append({
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "result": metadata if metadata and message.sender_type == "ai" else None,
                    "attachment": metadata if metadata and message.sender_type == "customer" and metadata.get("type") == "product" else None,
                    "sender_type": message.sender_type,
                    "sender_id": message.sender_id,
                    "sender_name": message.sender_name,
                    "created_at": (
                        message.created_at
                        if message.created_at.tzinfo
                        else message.created_at.replace(tzinfo=timezone.utc)
                    ).isoformat(),
                })
            return result

    def list_conversations(
        self,
        limit: int = 50,
        session_prefix: str | None = None,
        user_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        overdue: bool = False,
    ) -> list[dict]:
        with self.database.session_factory() as session:
            statement = (
                select(ConversationRecord, UserRecord)
                .join(UserRecord, UserRecord.user_id == ConversationRecord.user_id)
                .options(selectinload(ConversationRecord.messages))
                .where(UserRecord.role == "customer")
                .order_by(ConversationRecord.updated_at.desc())
                .limit(limit)
            )
            if session_prefix:
                statement = statement.where(ConversationRecord.session_id.startswith(session_prefix))
            if user_id:
                statement = statement.where(ConversationRecord.user_id == user_id)
            if status:
                statement = statement.where(ConversationRecord.status == status)
            rows = session.execute(statement).all()

            result = []
            for conversation, user in rows:
                messages = sorted(conversation.messages, key=lambda item: (item.created_at, item.id))
                summary = self._conversation_summary(conversation, user.display_name, messages, customer_view=bool(user_id))
                haystack = " ".join((
                    summary["display_name"], summary["session_id"], summary.get("order_id") or "",
                    summary["last_user_message"], summary["last_assistant_message"],
                )).lower()
                if query and query.strip().lower() not in haystack:
                    continue
                if overdue and not summary["is_overdue"]:
                    continue
                result.append(summary)
            return result

    def get_conversation(self, session_id: str, user_id: str) -> dict | None:
        with self.database.session_factory() as session:
            row = session.execute(
                select(ConversationRecord, UserRecord)
                .join(UserRecord, UserRecord.user_id == ConversationRecord.user_id)
                .options(selectinload(ConversationRecord.messages))
                .where(ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id)
            ).first()
            return self._conversation_summary(row[0], row[1].display_name, row[0].messages) if row else None

    def mark_conversation_read(self, session_id: str, user_id: str, viewer: str) -> None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if conversation:
                if viewer == "customer":
                    conversation.last_customer_read_at = datetime.now(timezone.utc)
                else:
                    conversation.last_agent_read_at = datetime.now(timezone.utc)
                session.commit()

    def takeover_conversation(self, session_id: str, user_id: str, agent_id: str) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation:
                return None
            conversation.status = "human_active"
            conversation.assigned_to = agent_id
            if not conversation.suggested_reply:
                last_message = session.scalar(select(MessageRecord).where(
                    MessageRecord.conversation_id == conversation.id,
                    MessageRecord.sender_type == "customer",
                ).order_by(MessageRecord.created_at.desc(), MessageRecord.id.desc()))
                if last_message:
                    conversation.suggested_reply = self._suggest_reply(
                        last_message.content, conversation.product_id, conversation.order_id,
                    )
            conversation.last_agent_read_at = datetime.now(timezone.utc)
            session.commit()
        return self.get_conversation(session_id, user_id)

    def release_conversation(self, session_id: str, user_id: str, agent_id: str) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation or (conversation.assigned_to and conversation.assigned_to != agent_id):
                return None
            conversation.status = "bot_active"
            conversation.assigned_to = None
            session.commit()
        return self.get_conversation(session_id, user_id)

    def resolve_conversation(self, session_id: str, user_id: str, code: str, summary: str) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation:
                return None
            conversation.status = "resolved"
            conversation.resolution_code = code
            conversation.resolution_summary = summary
            conversation.resolved_at = datetime.now(timezone.utc)
            session.commit()
        return self.get_conversation(session_id, user_id)

    def reply_conversation(self, session_id: str, user_id: str, agent_id: str, agent_name: str, content: str) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation or conversation.status != "human_active":
                return None
            session.add(MessageRecord(
                conversation_id=conversation.id, role="assistant", content=content,
                sender_type="agent", sender_id=agent_id, sender_name=agent_name,
            ))
            conversation.updated_at = datetime.now(timezone.utc)
            session.commit()
        return self.get_conversation(session_id, user_id)

    def record_service_message(self, session_id: str, user_id: str, content: str, sender_name: str = "售后服务") -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation:
                return None
            session.add(MessageRecord(
                conversation_id=conversation.id, role="assistant", content=content,
                sender_type="agent", sender_id="after-sales-service", sender_name=sender_name,
            ))
            conversation.updated_at = datetime.now(timezone.utc)
            session.commit()
        return self.get_conversation(session_id, user_id)

    def add_conversation_note(self, session_id: str, user_id: str, author_id: str, author_name: str, content: str) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation:
                return None
            record = ConversationNoteRecord(
                conversation_id=conversation.id, author_id=author_id, author_name=author_name, content=content,
            )
            session.add(record); session.commit(); session.refresh(record)
            return {"id": record.id, "author_name": record.author_name, "content": record.content, "created_at": record.created_at.isoformat()}

    def conversation_notes(self, session_id: str, user_id: str) -> list[dict]:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation:
                return []
            rows = session.scalars(select(ConversationNoteRecord).where(
                ConversationNoteRecord.conversation_id == conversation.id
            ).order_by(ConversationNoteRecord.created_at.desc())).all()
            return [{"id": row.id, "author_name": row.author_name, "content": row.content, "created_at": row.created_at.isoformat()} for row in rows]

    def rate_conversation(self, session_id: str, user_id: str, score: int, tags: list[str], comment: str | None) -> dict | None:
        with self.database.session_factory() as session:
            conversation = session.scalar(select(ConversationRecord).where(
                ConversationRecord.session_id == session_id, ConversationRecord.user_id == user_id,
            ))
            if not conversation or conversation.status != "resolved":
                return None
            existing = session.scalar(select(ConversationRatingRecord).where(
                ConversationRatingRecord.conversation_id == conversation.id,
                ConversationRatingRecord.user_id == user_id,
            ))
            if existing:
                existing.score, existing.tags_json, existing.comment = score, json.dumps(tags, ensure_ascii=False), comment
                record = existing
            else:
                record = ConversationRatingRecord(conversation_id=conversation.id, user_id=user_id, score=score, tags_json=json.dumps(tags, ensure_ascii=False), comment=comment)
                session.add(record)
            session.commit(); session.refresh(record)
            return {"score": record.score, "tags": json.loads(record.tags_json), "comment": record.comment}

    def seed_quick_replies(self) -> None:
        templates = (
            ("物流", "物流处理中", "您好，我正在核对最新物流节点，请稍候。"),
            ("退款", "退款材料", "请提供商品现状、问题照片和期望处理方式，我会继续核验退款条件。"),
            ("保修", "保修检测", "请提供订单号和故障现象，我们将依据保修政策安排检测。"),
            ("发票", "开票信息", "请确认发票抬头、税号和接收邮箱。"),
            ("账号安全", "安全处理", "请立即修改密码并检查绑定设备，我会同步核查异常记录。"),
        )
        with self.database.session_factory() as session:
            if session.scalar(select(func.count()).select_from(QuickReplyRecord)):
                return
            session.add_all(QuickReplyRecord(category=c, title=t, content=v) for c, t, v in templates)
            session.commit()

    def list_quick_replies(self) -> list[dict]:
        with self.database.session_factory() as session:
            rows = session.scalars(select(QuickReplyRecord).where(QuickReplyRecord.active == 1).order_by(QuickReplyRecord.category, QuickReplyRecord.id)).all()
            return [{"id": row.id, "category": row.category, "title": row.title, "content": row.content} for row in rows]

    @staticmethod
    def _suggest_reply(message: str, product_id: str | None, order_id: str | None) -> str:
        context = f"订单 {order_id}" if order_id else (f"商品 {product_id}" if product_id else "您的问题")
        if any(word in message for word in ("物流", "到哪", "快递")):
            return f"您好，我正在核对{context}的最新物流节点，确认后马上回复您。"
        if any(word in message for word in ("退款", "退货", "售后")):
            return f"您好，我已收到您关于{context}的售后诉求，正在核验订单状态和适用政策。"
        if any(word in message for word in ("投诉", "维权", "安全", "故障")):
            return f"您好，您的情况已被重点记录。我会核对{context}及相关证据，并持续同步进展。"
        return f"您好，您的问题我已接手。我正在核对{context}的相关信息，请稍候。"

    @staticmethod
    def _conversation_summary(
        conversation: ConversationRecord,
        display_name: str,
        messages: list[MessageRecord],
        customer_view: bool = False,
    ) -> dict:
        def utc_iso(value: datetime | None) -> str | None:
            if value is None:
                return None
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()

        ordered = sorted(messages, key=lambda item: (item.created_at, item.id))
        last_customer = next((item for item in reversed(ordered) if item.sender_type == "customer"), None)
        last_reply = next((item for item in reversed(ordered) if item.sender_type in {"ai", "agent"}), None)
        read_at = conversation.last_customer_read_at if customer_view else conversation.last_agent_read_at
        unread_types = {"ai", "agent"} if customer_view else {"customer"}
        unread = sum(1 for item in ordered if item.sender_type in unread_types and (read_at is None or item.created_at > read_at))
        now = datetime.now(timezone.utc)
        resolve_due = conversation.resolve_due_at
        if resolve_due and resolve_due.tzinfo is None:
            resolve_due = resolve_due.replace(tzinfo=timezone.utc)
        return {
            "session_id": conversation.session_id, "user_id": conversation.user_id, "display_name": display_name,
            "status": conversation.status, "priority": conversation.priority,
            "assigned_to": "专员" if customer_view and conversation.assigned_to else conversation.assigned_to,
            "product_id": conversation.product_id, "order_id": conversation.order_id,
            "first_response_due_at": utc_iso(conversation.first_response_due_at),
            "resolve_due_at": utc_iso(conversation.resolve_due_at),
            "resolved_at": utc_iso(conversation.resolved_at),
            "resolution_code": conversation.resolution_code, "resolution_summary": conversation.resolution_summary,
            "suggested_reply": conversation.suggested_reply, "tags": json.loads(conversation.tags_json or "[]"),
            "last_user_message": last_customer.content if last_customer else "",
            "last_assistant_message": last_reply.content if last_reply else "", "message_count": len(ordered),
            "unread_count": unread, "is_overdue": bool(resolve_due and resolve_due < now and conversation.status != "resolved"),
            "updated_at": (conversation.updated_at if conversation.updated_at.tzinfo else conversation.updated_at.replace(tzinfo=timezone.utc)).isoformat(),
        }

    def audit(self, actor_id: str, action: str, target_type: str, target_id: str, detail: dict) -> None:
        with self.database.session_factory() as session:
            session.add(
                AuditLogRecord(
                    actor_id=actor_id, action=action, target_type=target_type, target_id=target_id,
                    detail_json=json.dumps(detail, ensure_ascii=False),
                )
            )
            session.commit()

    def create_ticket(
        self,
        session_id: str,
        user_id: str,
        reason: str,
        summary: str,
        priority: str = "normal",
    ) -> dict:
        with self.database.session_factory() as session:
            existing = session.scalar(
                select(TicketRecord)
                .options(selectinload(TicketRecord.replies))
                .where(
                    TicketRecord.session_id == session_id,
                    TicketRecord.user_id == user_id,
                    TicketRecord.status.in_(("open", "assigned")),
                )
            )
            if existing:
                return self._ticket_dict(existing)
            record = TicketRecord(
                ticket_id=f"TK{uuid.uuid4().hex[:10].upper()}",
                session_id=session_id,
                user_id=user_id,
                status="open",
                priority=priority,
                reason=reason,
                summary=summary,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._ticket_dict(record)

    def list_tickets(self, user_id: str | None = None) -> list[dict]:
        with self.database.session_factory() as session:
            query = select(TicketRecord).options(selectinload(TicketRecord.replies))
            if user_id:
                query = query.where(TicketRecord.user_id == user_id)
            records = session.scalars(query.order_by(TicketRecord.updated_at.desc())).all()
            return [self._ticket_dict(record) for record in records]

    def get_ticket(self, ticket_id: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(TicketRecord)
                .options(selectinload(TicketRecord.replies))
                .where(TicketRecord.ticket_id == ticket_id)
            )
            return self._ticket_dict(record, include_replies=True) if record else None

    def assign_ticket(self, ticket_id: str, assignee_id: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(TicketRecord)
                .options(selectinload(TicketRecord.replies))
                .where(TicketRecord.ticket_id == ticket_id)
            )
            if not record:
                return None
            if record.status == "resolved":
                return self._ticket_dict(record)
            record.assigned_to = assignee_id
            record.status = "assigned"
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._ticket_dict(record)

    def reply_ticket(self, ticket_id: str, author_id: str, author_role: str, content: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(TicketRecord)
                .options(selectinload(TicketRecord.replies))
                .where(TicketRecord.ticket_id == ticket_id)
            )
            if not record or record.status == "resolved":
                return None
            record.replies.append(
                TicketReplyRecord(author_id=author_id, author_role=author_role, content=content)
            )
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._ticket_dict(record, include_replies=True)

    def resolve_ticket(self, ticket_id: str, resolver_id: str) -> dict | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(TicketRecord)
                .options(selectinload(TicketRecord.replies))
                .where(TicketRecord.ticket_id == ticket_id)
            )
            if not record:
                return None
            record.status = "resolved"
            record.assigned_to = record.assigned_to or resolver_id
            record.resolved_at = datetime.now(timezone.utc)
            record.updated_at = record.resolved_at
            session.commit()
            return self._ticket_dict(record, include_replies=True)

    def operational_metrics(self) -> dict:
        with self.database.session_factory() as session:
            documents = session.scalar(select(func.count()).select_from(KnowledgeDocumentRecord)) or 0
            chunks = session.scalar(select(func.count()).select_from(KnowledgeChunkRecord)) or 0
            conversations = session.scalar(select(func.count()).select_from(ConversationRecord)) or 0
            messages = session.scalar(select(func.count()).select_from(MessageRecord)) or 0
            tickets = {
                status: session.scalar(
                    select(func.count()).select_from(TicketRecord).where(TicketRecord.status == status)
                ) or 0
                for status in ("open", "assigned", "resolved")
            }
            assistant_rows = session.scalars(
                select(MessageRecord.metadata_json).where(
                    MessageRecord.role == "assistant", MessageRecord.metadata_json.is_not(None)
                )
            ).all()
            model_calls = session.scalar(select(func.count()).select_from(ModelObservationRecord)) or 0
            average_latency = session.scalar(select(func.avg(ModelObservationRecord.latency_ms))) or 0
            conversation_rows = session.scalars(select(ConversationRecord)).all()
            ratings = session.scalars(select(ConversationRatingRecord.score)).all()
        responses = [json.loads(value) for value in assistant_rows if value]
        confidence = [float(item.get("confidence", 0)) for item in responses]
        now = datetime.now(timezone.utc)
        resolved_count = sum(item.status == "resolved" for item in conversation_rows)
        overdue_count = 0
        first_response_seconds: list[float] = []
        with self.database.session_factory() as session:
            for item in conversation_rows:
                due = item.resolve_due_at
                if due and due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                overdue_count += bool(due and due < now and item.status != "resolved")
                first_customer = session.scalar(select(MessageRecord).where(
                    MessageRecord.conversation_id == item.id, MessageRecord.sender_type == "customer",
                ).order_by(MessageRecord.created_at, MessageRecord.id))
                first_reply = session.scalar(select(MessageRecord).where(
                    MessageRecord.conversation_id == item.id, MessageRecord.sender_type.in_(("ai", "agent")),
                ).order_by(MessageRecord.created_at, MessageRecord.id))
                if first_customer and first_reply:
                    start = first_customer.created_at.replace(tzinfo=timezone.utc) if first_customer.created_at.tzinfo is None else first_customer.created_at
                    end = first_reply.created_at.replace(tzinfo=timezone.utc) if first_reply.created_at.tzinfo is None else first_reply.created_at
                    first_response_seconds.append(max(0, (end - start).total_seconds()))
        return {
            "documents": documents,
            "chunks": chunks,
            "conversations": conversations,
            "messages": messages,
            "tickets": tickets,
            "average_confidence": round(sum(confidence) / len(confidence), 3) if confidence else 0,
            "human_handoff_rate": round(
                sum(bool(item.get("needs_human")) for item in responses) / len(responses), 3
            ) if responses else 0,
            "tool_call_rate": round(
                sum(bool(item.get("tool_calls")) for item in responses) / len(responses), 3
            ) if responses else 0,
            "model_calls": model_calls,
            "average_model_latency_ms": round(float(average_latency)),
            "average_first_response_seconds": round(sum(first_response_seconds) / len(first_response_seconds), 1) if first_response_seconds else 0,
            "overdue_rate": round(overdue_count / conversations, 3) if conversations else 0,
            "resolution_rate": round(resolved_count / conversations, 3) if conversations else 0,
            "average_satisfaction": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "rating_count": len(ratings),
        }

    def question_analytics(self, limit: int = 12, clustered_gaps: list[dict] | None = None) -> dict:
        with self.database.session_factory() as session:
            messages = session.scalars(
                select(MessageRecord).order_by(MessageRecord.conversation_id, MessageRecord.id)
            ).all()
            user_names = {
                user.user_id: user.display_name
                for user in session.scalars(select(UserRecord)).all()
            }

            frequent: dict[str, dict] = {}
            uncovered: dict[str, dict] = {}
            pending: dict[int, MessageRecord] = {}
            total_questions = 0
            knowledge_questions = 0
            uncovered_count = 0

            def add(counter: dict[str, dict], question: MessageRecord) -> None:
                normalized = re.sub(r"[\s，。！？,.!?、；;：:（）()\"'“”‘’]+", "", question.content.lower())
                key = normalized or question.content.strip().lower()
                created_at = (
                    question.created_at
                    if question.created_at.tzinfo
                    else question.created_at.replace(tzinfo=timezone.utc)
                ).isoformat()
                item = counter.setdefault(key, {
                    "question": question.content.strip(),
                    "count": 0,
                    "last_asked_at": created_at,
                    "occurrences": [],
                })
                item["count"] += 1
                conversation = question.conversation
                item["occurrences"].append({
                    "message_id": question.id,
                    "session_id": conversation.session_id,
                    "user_id": conversation.user_id,
                    "display_name": user_names.get(conversation.user_id, conversation.user_id),
                    "product_id": conversation.product_id,
                    "order_id": conversation.order_id,
                    "conversation_status": conversation.status,
                    "asked_at": created_at,
                })
                if created_at > item["last_asked_at"]:
                    item["question"] = question.content.strip()
                    item["last_asked_at"] = created_at

            def process(question: MessageRecord, answer: MessageRecord | None) -> None:
                nonlocal total_questions, knowledge_questions, uncovered_count
                total_questions += 1
                add(frequent, question)
                if answer is None or not answer.metadata_json:
                    return
                try:
                    metadata = json.loads(answer.metadata_json)
                except json.JSONDecodeError:
                    return
                intent = metadata.get("intent")
                if intent not in {"knowledge_qa", "general_chat"} or is_general_chat(question.content):
                    return
                knowledge_questions += 1
                if not metadata.get("citations"):
                    uncovered_count += 1
                    add(uncovered, question)

            for message in messages:
                conversation_id = message.conversation_id
                if message.role == "user":
                    previous = pending.get(conversation_id)
                    if previous is not None:
                        process(previous, None)
                    pending[conversation_id] = message
                elif message.role == "assistant" and conversation_id in pending:
                    process(pending.pop(conversation_id), message)
            for question in pending.values():
                process(question, None)

        def ranked(counter: dict[str, dict]) -> list[dict]:
            items = sorted(counter.values(), key=lambda item: (-item["count"], item["question"]))[:limit]
            for item in items:
                item["occurrences"].sort(key=lambda occurrence: occurrence["asked_at"], reverse=True)
            return items

        covered = knowledge_questions - uncovered_count
        uncovered_items = clustered_gaps if clustered_gaps is not None else ranked(uncovered)
        return {
            "total_questions": total_questions,
            "unique_questions": len(frequent),
            "knowledge_questions": knowledge_questions,
            "uncovered_count": uncovered_count,
            "coverage_rate": round(covered / knowledge_questions, 3) if knowledge_questions else 1.0,
            "top_questions": ranked(frequent),
            "uncovered_questions": uncovered_items[:limit],
        }

    def record_model_observation(
        self,
        model: str,
        status: str,
        latency_ms: int,
        input_chars: int,
        output_chars: int,
        session_id: str,
    ) -> None:
        with self.database.session_factory() as session:
            session.add(
                ModelObservationRecord(
                    model=model,
                    status=status,
                    latency_ms=latency_ms,
                    input_chars=input_chars,
                    output_chars=output_chars,
                    session_id=session_id,
                )
            )
            session.commit()

    def list_audit_logs(self, limit: int = 100) -> list[dict]:
        with self.database.session_factory() as session:
            records = session.scalars(
                select(AuditLogRecord).order_by(AuditLogRecord.created_at.desc()).limit(min(limit, 500))
            ).all()
            return [
                {
                    "actor_id": record.actor_id,
                    "action": record.action,
                    "target_type": record.target_type,
                    "target_id": record.target_id,
                    "detail": json.loads(record.detail_json) if record.detail_json else {},
                    "created_at": record.created_at.isoformat(),
                }
                for record in records
            ]

    @staticmethod
    def _document_dict(record: KnowledgeDocumentRecord) -> dict:
        return {
            "doc_id": record.doc_id,
            "title": record.title,
            "file_name": record.file_name,
            "source_type": record.source_type,
            "version": record.version,
            "status": record.status,
            "visibility": record.visibility,
            "product_id": record.product_id,
            "document_category": record.document_category,
            "size_bytes": record.size_bytes,
            "chunk_count": len(record.chunks),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _user_dict(record: UserRecord) -> dict:
        return {
            "user_id": record.user_id,
            "username": record.username,
            "password_hash": record.password_hash,
            "display_name": record.display_name,
            "role": record.role,
            "active": bool(record.active),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _ticket_dict(record: TicketRecord, include_replies: bool = False) -> dict:
        result = {
            "ticket_id": record.ticket_id,
            "session_id": record.session_id,
            "user_id": record.user_id,
            "status": record.status,
            "priority": record.priority,
            "reason": record.reason,
            "summary": record.summary,
            "assigned_to": record.assigned_to,
            "reply_count": len(record.replies),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
        }
        if include_replies:
            result["replies"] = [
                {
                    "author_id": reply.author_id,
                    "author_role": reply.author_role,
                    "content": reply.content,
                    "created_at": reply.created_at.isoformat(),
                }
                for reply in record.replies
            ]
        return result
