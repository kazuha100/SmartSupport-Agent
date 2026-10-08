from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), index=True)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeDocumentRecord(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    file_name: Mapped[str] = mapped_column(String(260))
    source_type: Mapped[str] = mapped_column(String(20))
    source_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    version: Mapped[str] = mapped_column(String(40), default="1.0")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    visibility: Mapped[str] = mapped_column(String(30), default="public")
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    document_category: Mapped[str] = mapped_column(String(40), default="general", index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_text: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    chunks: Mapped[list["KnowledgeChunkRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunkRecord.position"
    )


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "position", name="uq_document_chunk_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(240), default="概述")
    content: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    document: Mapped[KnowledgeDocumentRecord] = relationship(back_populates="chunks")


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_conversation_session_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), default="bot_active", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolve_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_customer_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_agent_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    messages: Mapped[list["MessageRecord"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_type: Mapped[str] = mapped_column(String(20), default="ai", index=True)
    sender_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(120), default="智能客服")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")


class KnowledgeGapClusterRecord(Base):
    __tablename__ = "knowledge_gap_clusters"

    cluster_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    representative_question: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    embedding_model: Mapped[str] = mapped_column(String(160))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeGapMemberRecord(Base):
    __tablename__ = "knowledge_gap_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_gap_clusters.cluster_id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, index=True
    )
    original_question: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(120))
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TicketRecord(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    reason: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replies: Mapped[list["TicketReplyRecord"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketReplyRecord.created_at"
    )


class TicketReplyRecord(Base):
    __tablename__ = "ticket_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(String(100), index=True)
    author_role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ticket: Mapped[TicketRecord] = relationship(back_populates="replies")


class ModelObservationRecord(Base):
    __tablename__ = "model_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_chars: Mapped[int] = mapped_column(Integer)
    output_chars: Mapped[int] = mapped_column(Integer)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProductRecord(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60), index=True)
    description: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str] = mapped_column(String(500))
    specs_json: Mapped[str] = mapped_column(Text, default="{}")
    warranty_months: Mapped[int] = mapped_column(Integer, default=12)
    active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CartItemRecord(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AddressRecord(Base):
    __tablename__ = "addresses"

    address_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    recipient: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30))
    province: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(300))
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CommerceOrderRecord(Base):
    __tablename__ = "commerce_orders"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    payment_status: Mapped[str] = mapped_column(String(30), index=True)
    shipping_status: Mapped[str] = mapped_column(String(30), index=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    address_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommerceOrderItemRecord(Base):
    __tablename__ = "commerce_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.order_id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(50), index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    image_url: Mapped[str] = mapped_column(String(500))
    price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)


class PaymentRecord(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.order_id"), unique=True, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(30), default="sandbox_pay")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShipmentRecord(Base):
    __tablename__ = "commerce_shipments"

    shipment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.order_id"), unique=True, index=True)
    carrier: Mapped[str] = mapped_column(String(80))
    tracking_number: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    latest_event: Mapped[str] = mapped_column(String(300))
    events_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AppealRecord(Base):
    __tablename__ = "appeals"

    appeal_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.order_id"), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    appeal_type: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    agent_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    assigned_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responsibility: Mapped[str | None] = mapped_column(String(30), nullable=True)
    investigation_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    proposed_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    submitted_for_approval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_confirmation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ConversationNoteRecord(Base):
    __tablename__ = "conversation_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(String(100), index=True)
    author_name: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConversationRatingRecord(Base):
    __tablename__ = "conversation_ratings"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_rating_conversation_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[int] = mapped_column(Integer)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuickReplyRecord(Base):
    __tablename__ = "quick_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[int] = mapped_column(Integer, default=1)


class RefundRecord(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("commerce_orders.order_id"), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppealAttachmentRecord(Base):
    __tablename__ = "appeal_attachments"

    attachment_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.appeal_id", ondelete="CASCADE"), index=True)
    material_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("appeal_material_requests.request_id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    file_name: Mapped[str] = mapped_column(String(260))
    content_type: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(600))
    size_bytes: Mapped[int] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppealEventRecord(Base):
    __tablename__ = "appeal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.appeal_id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    actor_name: Mapped[str] = mapped_column(String(120))
    actor_role: Mapped[str] = mapped_column(String(30))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(160))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    visible_to_customer: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppealMaterialRequestRecord(Base):
    __tablename__ = "appeal_material_requests"

    request_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.appeal_id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(100))
    requested_name: Mapped[str] = mapped_column(String(120))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppealExecutionRecord(Base):
    __tablename__ = "appeal_executions"
    __table_args__ = (
        UniqueConstraint("appeal_id", "approval_round", name="uq_execution_appeal_round"),
    )

    execution_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.appeal_id", ondelete="CASCADE"), index=True)
    approval_round: Mapped[int] = mapped_column(Integer, default=1)
    action: Mapped[str] = mapped_column(String(40))
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    sandbox_reference: Mapped[str] = mapped_column(String(80))
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Database:
    def __init__(self, url: str):
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError("SmartSupport requires a postgresql+psycopg DATABASE_URL")
        self.engine = create_engine(url, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.is_postgres = True

    def create_all(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(self.engine)
        self._migrate_columns()
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding vector(512)"))
            connection.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(160)"))

    def _migrate_columns(self) -> None:
        columns = {
            "knowledge_documents": {
                "product_id": "VARCHAR(50)",
                "document_category": "VARCHAR(40) DEFAULT 'general'",
            },
            "conversations": {
                "status": "VARCHAR(30) DEFAULT 'bot_active'",
                "priority": "VARCHAR(20) DEFAULT 'normal'",
                "assigned_to": "VARCHAR(100)",
                "product_id": "VARCHAR(50)",
                "order_id": "VARCHAR(50)",
                "first_response_due_at": "TIMESTAMP",
                "resolve_due_at": "TIMESTAMP",
                "last_customer_read_at": "TIMESTAMP",
                "last_agent_read_at": "TIMESTAMP",
                "resolved_at": "TIMESTAMP",
                "resolution_code": "VARCHAR(60)",
                "resolution_summary": "TEXT",
                "suggested_reply": "TEXT",
                "tags_json": "TEXT DEFAULT '[]'",
            },
            "messages": {
                "sender_type": "VARCHAR(20)",
                "sender_id": "VARCHAR(100)",
                "sender_name": "VARCHAR(120)",
            },
            "knowledge_chunks": {
                "embedding_model": "VARCHAR(160)",
            },
            "appeals": {
                "assigned_to": "VARCHAR(100)", "assigned_name": "VARCHAR(120)", "accepted_at": "TIMESTAMP",
                "responsibility": "VARCHAR(30)", "investigation_conclusion": "TEXT",
                "proposed_action": "VARCHAR(40)", "proposed_amount_cents": "INTEGER", "proposal_reason": "TEXT",
                "risk_level": "VARCHAR(20)", "risk_reasons_json": "TEXT DEFAULT '[]'",
                "submitted_for_approval_at": "TIMESTAMP", "approved_by": "VARCHAR(100)",
                "approved_name": "VARCHAR(120)", "approval_comment": "TEXT", "approved_at": "TIMESTAMP",
                "customer_confirmation": "VARCHAR(30)", "resolved_at": "TIMESTAMP",
            },
            "appeal_attachments": {
                "review_status": "VARCHAR(20) DEFAULT 'pending'", "reviewed_by": "VARCHAR(100)",
                "reviewed_name": "VARCHAR(120)", "review_note": "TEXT", "reviewed_at": "TIMESTAMP",
                "material_request_id": "VARCHAR(50)",
            },
            "appeal_executions": {
                "approval_round": "INTEGER DEFAULT 1",
            },
        }
        with self.engine.begin() as connection:
            for table, additions in columns.items():
                for name, definition in additions.items():
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {definition}"))
            connection.execute(text("UPDATE knowledge_documents SET document_category='general' WHERE document_category IS NULL"))
            connection.execute(text("UPDATE conversations SET status='bot_active' WHERE status IS NULL"))
            connection.execute(text("UPDATE conversations SET priority='normal' WHERE priority IS NULL"))
            connection.execute(text("UPDATE conversations SET tags_json='[]' WHERE tags_json IS NULL"))
            connection.execute(text("UPDATE messages SET sender_type=CASE WHEN role='user' THEN 'customer' ELSE 'ai' END WHERE sender_type IS NULL"))
            connection.execute(text("UPDATE messages SET sender_name=CASE WHEN role='user' THEN '顾客' ELSE '智能客服' END WHERE sender_name IS NULL"))
            connection.execute(text("UPDATE appeals SET risk_reasons_json='[]' WHERE risk_reasons_json IS NULL"))
            connection.execute(text("UPDATE appeal_attachments SET review_status='pending' WHERE review_status IS NULL"))
            connection.execute(text("""
                UPDATE appeals SET status='submitted'
                WHERE status='open'
                   OR (status='investigating' AND assigned_to IS NULL AND accepted_at IS NULL)
            """))
            connection.execute(text("UPDATE appeals SET status='resolved', resolved_at=updated_at WHERE ticket_id IN (SELECT ticket_id FROM tickets WHERE status='resolved')"))
            connection.execute(text("""
                INSERT INTO appeal_events (appeal_id, actor_id, actor_name, actor_role, event_type, title, detail_json, from_status, to_status, visible_to_customer, created_at)
                SELECT a.appeal_id, 'system', '系统', 'system', 'initial_review', '历史智能核验结果已迁移', '{}', a.status, a.status, 1, a.updated_at
                FROM appeals a
                WHERE a.agent_result_json IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM appeal_events e WHERE e.appeal_id=a.appeal_id AND e.event_type='initial_review')
            """))
        self._migrate_appeal_execution_constraints()

    def _migrate_appeal_execution_constraints(self) -> None:
        """Preserve one immutable execution row per approval round."""
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE appeal_executions DROP CONSTRAINT IF EXISTS uq_execution_appeal"))
            connection.execute(text("ALTER TABLE appeal_executions DROP CONSTRAINT IF EXISTS appeal_executions_sandbox_reference_key"))
            connection.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname='uq_execution_appeal_round'
                    ) THEN
                        ALTER TABLE appeal_executions
                        ADD CONSTRAINT uq_execution_appeal_round UNIQUE (appeal_id, approval_round);
                    END IF;
                END $$;
            """))
