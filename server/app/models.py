from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    product_id: str | None = Field(default=None, max_length=50)
    order_id: str | None = Field(default=None, max_length=50)


class ProductShareRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=50)


class Citation(BaseModel):
    doc_id: str
    title: str
    section: str
    version: str
    excerpt: str
    score: float


class ToolCall(BaseModel):
    name: str
    status: Literal["success", "blocked", "pending"]
    arguments: dict
    summary: str


class TraceStep(BaseModel):
    name: str
    detail: str
    status: Literal["done", "waiting", "blocked"] = "done"


class ChatResponse(BaseModel):
    answer: str
    intent: str
    confidence: float
    needs_human: bool = False
    citations: list[Citation] = []
    tool_calls: list[ToolCall] = []
    trace: list[TraceStep] = []
    ticket_id: str | None = None
    route: str | None = None
    current_stage: str | None = None
    agent_results: list[dict] = []
    appeal_id: str | None = None
    risk_review: dict | None = None


class DocumentStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{4,32}$")
    display_name: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=72)


class ConversationReplyRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4000)


class ConversationActionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    resolution_code: str | None = Field(default=None, max_length=60)
    resolution_summary: str | None = Field(default=None, max_length=2000)


class ConversationNoteRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=2000)


class ConversationRatingRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=8)
    comment: str | None = Field(default=None, max_length=1000)


class AuthUser(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: Literal["customer", "agent", "admin"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


class TicketReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class Order(BaseModel):
    order_id: str
    user_id: str
    product_name: str
    amount: float
    status: str
    created_at: str
    delivered_at: str | None = None
    refundable: bool = True


class Shipment(BaseModel):
    order_id: str
    carrier: str
    tracking_number: str
    status: str
    latest_event: str
    updated_at: str
