import json
import re
from contextlib import asynccontextmanager
from uuid import uuid4
from pathlib import Path
from threading import Thread

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import text

from app.agent.graph import SupportGraph
from app.agent.service import SupportAgent
from app.auth import AuthService, build_auth_dependencies
from app.config import get_settings
from app.commerce_models import (
    AddressInput, AppealApprovalInput, AppealAttachmentReviewInput, AppealCreate,
    AppealCustomerFeedbackInput, AppealInvestigationInput, AppealMaterialRequestInput,
    AppealProposalInput, CartItemInput, CartItemUpdate, SandboxPaymentRequest, OrderCreate,
)
from app.commerce_repository import CommerceError, CommerceRepository
from app.database import Database
from app.documents import DocumentError, DocumentService
from app.llm import DeepSeekClient
from app.knowledge_gaps import KnowledgeGapService, is_knowledge_gap
from app.models import (
    AuthUser,
    ChatRequest,
    ChatResponse,
    DocumentStatusUpdate,
    KnowledgeSearchRequest,
    LoginRequest,
    ProductShareRequest,
    RegisterRequest,
    ConversationReplyRequest,
    ConversationActionRequest,
    ConversationNoteRequest,
    ConversationRatingRequest,
    TicketReplyRequest,
    TokenResponse,
    TraceStep,
)
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.observability import MetricsMiddleware, metrics_response
from app.off_topic import OffTopicGuard
from app.rag.embeddings import LocalEmbeddingProvider
from app.rag.retriever import KnowledgeBase
from app.repository import Repository
from app.tools.business import configure_business_tools


settings = get_settings()
root = settings.knowledge_base_path
if not root.is_absolute():
    root = Path(__file__).resolve().parents[2] / root

upload_dir = settings.upload_dir
if not upload_dir.is_absolute():
    upload_dir = Path(__file__).resolve().parents[1] / upload_dir

database = Database(settings.database_url)
database.create_all()
repository = Repository(database)
commerce_repository = CommerceRepository(database)
commerce_repository.seed()
configure_business_tools(commerce_repository)
auth_service = AuthService(repository, settings)
auth_service.seed_staff_users()
repository.seed_quick_replies()
current_user, require_roles = build_auth_dependencies(auth_service)
document_service = DocumentService(repository, upload_dir, settings.max_upload_mb)
document_service.sync_markdown_directory(root)
embedding_provider = None
if settings.embedding_mode.lower() == "local":
    embedding_provider = LocalEmbeddingProvider(settings.embedding_model, settings.embedding_dimension)
knowledge_base = KnowledgeBase(root, repository, embedding_provider)
knowledge_gap_service = (
    KnowledgeGapService(repository, embedding_provider, settings.knowledge_gap_similarity_threshold)
    if embedding_provider is not None
    else None
)
if embedding_provider is not None:
    Thread(target=embedding_provider.warm_up, name="embedding-warmup", daemon=True).start()
chat_model = None
if settings.llm_mode.lower() == "deepseek" and settings.llm_api_key:
    chat_model = DeepSeekClient.from_settings(settings)
agent = SupportAgent(knowledge_base, chat_model)
checkpoint_pool = ConnectionPool(
    conninfo=settings.psycopg_database_url,
    min_size=1,
    max_size=10,
    open=False,
    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
)
checkpoint_pool.open()
checkpoint_pool.wait()
checkpoint_saver = PostgresSaver(checkpoint_pool)
checkpoint_saver.setup()
support_graph = SupportGraph(agent, checkpoint_saver, settings.intent_router_min_confidence)
off_topic_guard = OffTopicGuard(
    settings.off_topic_max_consecutive_questions,
    settings.off_topic_window_seconds,
    settings.redis_url,
)
attachment_root = upload_dir / "appeal-attachments"
attachment_root.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    checkpoint_pool.close()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.requests_per_minute,
    chat_requests_per_minute=settings.chat_requests_per_minute,
    redis_url=settings.redis_url,
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "knowledge_chunks": len(knowledge_base.chunks),
        "llm_mode": settings.llm_mode,
        "llm_model": settings.llm_model,
        "llm_configured": chat_model is not None,
        "orchestrator": "langgraph",
        "database": "postgresql",
        "retrieval": "hybrid-vector" if embedding_provider else "keyword",
        "embedding_model": settings.embedding_model if embedding_provider else None,
        "checkpointer": "postgresql",
    }


@app.get("/health/live")
def liveness() -> dict:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness() -> dict:
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "database": "ok",
        "knowledge_chunks": len(knowledge_base.chunks),
        "model_configured": chat_model is not None,
    }


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.post("/api/auth/login", response_model=TokenResponse)
def login(request: LoginRequest) -> TokenResponse:
    result = auth_service.login(request.username, request.password)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, user = result
    repository.audit(user.user_id, "auth.login", "user", user.user_id, {"role": user.role})
    return TokenResponse(access_token=token, user=user)


@app.post("/api/auth/register", response_model=TokenResponse, status_code=201)
def register(request: RegisterRequest) -> TokenResponse:
    if not re.search(r"[A-Za-z]", request.password) or not re.search(r"\d", request.password):
        raise HTTPException(status_code=422, detail="密码必须同时包含字母和数字")
    result = auth_service.register_customer(request.username, request.display_name, request.password)
    if result is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    token, user = result
    repository.audit(user.user_id, "auth.register", "user", user.user_id, {})
    return TokenResponse(access_token=token, user=user)


@app.get("/api/auth/me", response_model=AuthUser)
def me(user: AuthUser = Depends(current_user)) -> AuthUser:
    return user


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(current_user),
) -> ChatResponse:
    existing = repository.get_conversation(request.session_id, user.user_id)
    if existing and existing["status"] == "human_active":
        repository.record_customer_message(request.session_id, user.user_id, user.display_name, request.message)
        return ChatResponse(answer="消息已发送给人工客服。", intent="human_active", confidence=1.0, current_stage="human_active")
    limited = _off_topic_limit_response(request, user)
    if limited is not None:
        return finalize_chat(request, user, limited, background_tasks)
    response = support_graph.respond(_agent_message(request), user.user_id, request.session_id)
    return finalize_chat(request, user, response, background_tasks)


@app.post("/api/chat/product-share", status_code=201)
def share_product(
    request: ProductShareRequest,
    user: AuthUser = Depends(require_roles("customer")),
) -> dict:
    product = commerce_repository.get_product(request.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在或已下架")
    result = repository.record_product_share(
        request.session_id,
        user.user_id,
        user.display_name,
        product,
    )
    if result["created"]:
        repository.audit(
            user.user_id,
            "conversation.product_share",
            "conversation",
            request.session_id,
            {"product_id": product["product_id"]},
        )
    return result


def _agent_message(request: ChatRequest) -> str:
    context = []
    if request.product_id:
        context.append(f"商品 {request.product_id}")
    if request.order_id and request.order_id not in request.message:
        context.append(f"订单 {request.order_id}")
    return " ".join((request.message, *context)).strip()


def _off_topic_limit_response(request: ChatRequest, user: AuthUser) -> ChatResponse | None:
    decision = off_topic_guard.check(user.user_id, request.session_id, _agent_message(request))
    if not decision.blocked:
        return None
    return ChatResponse(
        answer="你已经连续咨询了较多与商城客服无关的问题。请不要继续发送无关内容，以免占用服务资源；你可以继续咨询商品、订单、物流或售后问题。",
        intent="off_topic_limited",
        confidence=1.0,
        route="general",
        current_stage="limited",
        trace=[TraceStep(name="服务资源保护", detail="连续无关问题已超过会话允许范围，本次未调用大模型。", status="blocked")],
    )


def finalize_chat(
    request: ChatRequest,
    user: AuthUser,
    response: ChatResponse,
    background_tasks: BackgroundTasks | None = None,
) -> ChatResponse:
    if response.needs_human:
        ticket = repository.create_ticket(
            request.session_id,
            user.user_id,
            response.intent,
            f"用户诉求：{request.message}\nAgent 处理结果：{response.answer}",
            "high" if response.intent in {"refund_request", "human_handoff"} else "normal",
        )
        response = response.model_copy(update={"ticket_id": ticket["ticket_id"]})
        repository.audit(
            user.user_id,
            "ticket.create",
            "ticket",
            ticket["ticket_id"],
            {"reason": response.intent, "priority": ticket["priority"]},
        )
    recorded = repository.record_chat_turn(
        request.session_id, user.user_id, user.display_name, request.message, response,
        product_id=request.product_id, order_id=request.order_id,
    )
    if knowledge_gap_service is not None and is_knowledge_gap(request.message, response.model_dump(mode="json")):
        arguments = (recorded["message_id"], recorded["question"], recorded["product_id"])
        if background_tasks is not None:
            background_tasks.add_task(knowledge_gap_service.cluster_message, *arguments)
        else:
            knowledge_gap_service.cluster_message(*arguments)
    return response


@app.post("/api/chat/stream")
def chat_stream(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(current_user),
) -> StreamingResponse:
    def event_stream():
        yield json.dumps(
            {"type": "status", "content": "Support Orchestrator 正在识别问题并选择业务 Agent..."},
            ensure_ascii=False,
        ) + "\n"
        existing = repository.get_conversation(request.session_id, user.user_id)
        if existing and existing["status"] == "human_active":
            repository.record_customer_message(request.session_id, user.user_id, user.display_name, request.message)
            response = ChatResponse(answer="消息已发送给人工客服。", intent="human_active", confidence=1.0, current_stage="human_active")
        else:
            response = _off_topic_limit_response(request, user)
            if response is None:
                response = support_graph.respond(_agent_message(request), user.user_id, request.session_id)
            response = finalize_chat(request, user, response, background_tasks)
        active_agent = response.agent_results[-1]["agent"] if response.agent_results else "orchestrator"
        yield json.dumps(
            {"type": "status", "content": f"已由 {active_agent} 完成处理，正在生成回复..."},
            ensure_ascii=False,
        ) + "\n"
        for start in range(0, len(response.answer), 16):
            yield json.dumps(
                {"type": "delta", "content": response.answer[start:start + 16]},
                ensure_ascii=False,
            ) + "\n"
        yield json.dumps({"type": "done", "data": response.model_dump(mode="json")}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/api/conversations/{session_id}/state")
def conversation_state(
    session_id: str,
    user_id: str | None = None,
    user: AuthUser = Depends(current_user),
) -> dict:
    target_user_id = user.user_id if user.role == "customer" else (user_id or user.user_id)
    return support_graph.session_state(target_user_id, session_id)


@app.get("/api/conversations")
def conversations(
    prefix: str | None = None,
    status: str | None = None,
    query: str | None = None,
    overdue: bool = False,
    limit: int = 50,
    user: AuthUser = Depends(current_user),
) -> list[dict]:
    return repository.list_conversations(
        limit=max(1, min(limit, 100)), session_prefix=prefix,
        user_id=user.user_id if user.role == "customer" else None,
        status=status, query=query, overdue=overdue,
    )


@app.get("/api/conversations/{session_id}/messages")
def conversation_messages(
    session_id: str,
    user_id: str | None = None,
    user: AuthUser = Depends(current_user),
) -> list[dict]:
    target_user_id = user.user_id if user.role == "customer" else (user_id or user.user_id)
    messages = repository.conversation_messages(session_id, target_user_id)
    repository.mark_conversation_read(session_id, target_user_id, user.role)
    return messages


@app.post("/api/conversations/{session_id}/takeover")
def takeover_conversation(session_id: str, request: ConversationActionRequest, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    result = repository.takeover_conversation(session_id, request.user_id, user.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    repository.audit(user.user_id, "conversation.takeover", "conversation", session_id, {"user_id": request.user_id})
    return result


@app.post("/api/conversations/{session_id}/release")
def release_conversation(session_id: str, request: ConversationActionRequest, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    result = repository.release_conversation(session_id, request.user_id, user.user_id)
    if not result:
        raise HTTPException(status_code=409, detail="会话不存在或不属于当前客服")
    repository.audit(user.user_id, "conversation.release", "conversation", session_id, {})
    return result


@app.post("/api/conversations/{session_id}/resolve")
def resolve_conversation(session_id: str, request: ConversationActionRequest, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    if not request.resolution_code or not request.resolution_summary:
        raise HTTPException(status_code=422, detail="结案必须选择处理结果并填写总结")
    result = repository.resolve_conversation(session_id, request.user_id, request.resolution_code, request.resolution_summary)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    repository.audit(user.user_id, "conversation.resolve", "conversation", session_id, {"code": request.resolution_code})
    return result


@app.post("/api/conversations/{session_id}/replies")
def reply_conversation(session_id: str, request: ConversationReplyRequest, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    result = repository.reply_conversation(session_id, request.user_id, user.user_id, user.display_name, request.content)
    if not result:
        raise HTTPException(status_code=409, detail="请先接管会话后再回复")
    repository.audit(user.user_id, "conversation.reply", "conversation", session_id, {})
    return result


@app.get("/api/conversations/{session_id}/notes")
def conversation_notes(session_id: str, user_id: str, _: AuthUser = Depends(require_roles("admin"))) -> list[dict]:
    return repository.conversation_notes(session_id, user_id)


@app.post("/api/conversations/{session_id}/notes")
def add_conversation_note(session_id: str, request: ConversationNoteRequest, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    result = repository.add_conversation_note(session_id, request.user_id, user.user_id, user.display_name, request.content)
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@app.post("/api/conversations/{session_id}/rating")
def rate_conversation(session_id: str, request: ConversationRatingRequest, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    result = repository.rate_conversation(session_id, user.user_id, request.score, request.tags, request.comment)
    if not result:
        raise HTTPException(status_code=409, detail="只能评价已解决的本人会话")
    return result


@app.get("/api/agent/quick-replies")
def quick_replies(_: AuthUser = Depends(require_roles("admin"))) -> list[dict]:
    return repository.list_quick_replies()


@app.get("/api/agent/customer-context/{user_id}")
def customer_context(user_id: str, _: AuthUser = Depends(require_roles("admin"))) -> dict:
    customer = repository.get_user_by_id(user_id)
    if not customer or customer["role"] != "customer":
        raise HTTPException(status_code=404, detail="顾客不存在")
    return {
        "customer": {key: customer[key] for key in ("user_id", "username", "display_name", "role", "created_at")},
        "member_status": "普通会员",
        "conversations": repository.list_conversations(user_id=user_id, limit=10),
        "orders": commerce_repository.list_orders(user_id)[:5],
        "tickets": repository.list_tickets(user_id)[:5],
        "appeals": commerce_repository.list_appeals(user_id)[:5],
    }


@app.get("/api/shop/products")
def shop_products(category: str | None = None, _: AuthUser = Depends(current_user)) -> list[dict]:
    return commerce_repository.list_products(category)


@app.get("/api/shop/products/{product_id}")
def shop_product(product_id: str, _: AuthUser = Depends(current_user)) -> dict:
    product = commerce_repository.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@app.get("/api/shop/cart")
def shop_cart(user: AuthUser = Depends(require_roles("customer"))) -> dict:
    return commerce_repository.cart(user.user_id)


@app.post("/api/shop/cart/items")
def add_shop_cart_item(payload: CartItemInput, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        return commerce_repository.put_cart_item(user.user_id, payload.product_id, payload.quantity)
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/shop/cart/items/{item_id}")
def update_shop_cart_item(item_id: int, payload: CartItemUpdate, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        return commerce_repository.update_cart_item(user.user_id, item_id, payload.quantity)
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/shop/addresses")
def shop_addresses(user: AuthUser = Depends(require_roles("customer"))) -> list[dict]:
    return commerce_repository.list_addresses(user.user_id)


@app.post("/api/shop/addresses")
def create_shop_address(payload: AddressInput, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    return commerce_repository.create_address(user.user_id, payload.model_dump())


@app.patch("/api/shop/addresses/{address_id}")
def update_shop_address(address_id: str, payload: AddressInput, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        return commerce_repository.update_address(user.user_id, address_id, payload.model_dump())
    except CommerceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/shop/addresses/{address_id}", status_code=204)
def delete_shop_address(address_id: str, user: AuthUser = Depends(require_roles("customer"))) -> None:
    try:
        commerce_repository.delete_address(user.user_id, address_id)
    except CommerceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/shop/orders")
def create_shop_order(payload: OrderCreate, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        order = commerce_repository.create_order(user.user_id, payload.address_id)
        repository.audit(user.user_id, "commerce.order.create", "order", order["order_id"], {"total_cents": order["total_cents"]})
        return order
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/shop/orders/{order_id}/pay")
def pay_shop_order(order_id: str, payload: SandboxPaymentRequest, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        order = commerce_repository.pay_order(order_id, user.user_id, payload.success)
        repository.audit(user.user_id, "commerce.payment.sandbox", "order", order_id, {"success": payload.success})
        return order
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/shop/orders")
def shop_orders(user: AuthUser = Depends(current_user)) -> list[dict]:
    return commerce_repository.list_orders(user.user_id if user.role == "customer" else None)


@app.get("/api/shop/orders/{order_id}")
def shop_order(order_id: str, user: AuthUser = Depends(current_user)) -> dict:
    order = commerce_repository.get_order(order_id, user.user_id if user.role == "customer" else None)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


@app.post("/api/orders/{order_id}/appeals")
def create_order_appeal(order_id: str, payload: AppealCreate, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        appeal = commerce_repository.create_appeal(order_id, user.user_id, payload.model_dump())
        agent_message = f"我要维权，订单 {order_id}。申诉类型：{payload.appeal_type}。{payload.description}"
        response = support_graph.respond(agent_message, user.user_id, payload.session_id)
        response = response.model_copy(update={"appeal_id": appeal["appeal_id"]})
        response = finalize_chat(ChatRequest(session_id=payload.session_id, message=agent_message), user, response)
        appeal = commerce_repository.attach_appeal_result(
            appeal["appeal_id"], response.ticket_id, response.model_dump(mode="json")
        )
        repository.audit(user.user_id, "appeal.create", "appeal", appeal["appeal_id"], {"order_id": order_id, "ticket_id": response.ticket_id})
        return {"appeal": appeal, "agent_response": response.model_dump(mode="json")}
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/appeals")
def list_order_appeals(user: AuthUser = Depends(current_user)) -> list[dict]:
    return commerce_repository.list_appeals(user.user_id if user.role == "customer" else None)


def appeal_for_user(appeal_id: str, user: AuthUser) -> dict:
    appeal = commerce_repository.get_appeal(appeal_id, user.user_id if user.role == "customer" else None)
    if not appeal:
        raise HTTPException(status_code=404, detail="申诉不存在或无权查看")
    return appeal


@app.get("/api/appeals/{appeal_id}")
def get_order_appeal(appeal_id: str, user: AuthUser = Depends(current_user)) -> dict:
    return appeal_for_user(appeal_id, user)


@app.post("/api/appeals/{appeal_id}/accept")
def accept_appeal(appeal_id: str, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.accept_appeal(appeal_id, user.user_id, user.display_name)
        if result.get("ticket_id"):
            repository.assign_ticket(result["ticket_id"], user.user_id)
        repository.takeover_conversation(result["session_id"], result["user_id"], user.user_id)
        repository.record_service_message(result["session_id"], result["user_id"], f"您的申诉已由{user.display_name}受理，正在核验证据和订单信息。")
        repository.audit(user.user_id, "appeal.accept", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/material-requests")
def request_appeal_material(appeal_id: str, payload: AppealMaterialRequestInput, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.request_material(appeal_id, user.user_id, user.display_name, payload.content, payload.due_at)
        repository.record_service_message(result["session_id"], result["user_id"], f"为继续处理申诉，请补充以下材料：{payload.content}")
        repository.audit(user.user_id, "appeal.material.request", "appeal", appeal_id, {"content": payload.content})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/attachments/{attachment_id}/review")
def review_appeal_attachment(appeal_id: str, attachment_id: str, payload: AppealAttachmentReviewInput, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.review_attachment(appeal_id, attachment_id, user.user_id, user.display_name, payload.status, payload.note)
        if payload.status == "accepted":
            message = "您补充的材料已审核通过，客服将继续调查。"
        else:
            message = f"您补充的材料未通过审核，请重新上传。审核意见：{payload.note or '材料不符合核验要求'}"
        repository.record_service_message(result["session_id"], result["user_id"], message)
        repository.audit(user.user_id, "appeal.attachment.review", "appeal", appeal_id, {"attachment_id": attachment_id, "status": payload.status})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/investigation")
def save_appeal_investigation(appeal_id: str, payload: AppealInvestigationInput, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.save_investigation(appeal_id, user.user_id, user.display_name, payload.responsibility, payload.conclusion)
        repository.audit(user.user_id, "appeal.investigation.save", "appeal", appeal_id, {"responsibility": payload.responsibility})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/proposal")
def save_appeal_proposal(appeal_id: str, payload: AppealProposalInput, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.save_proposal(appeal_id, user.user_id, user.display_name, payload.action, payload.amount_cents, payload.reason)
        repository.audit(user.user_id, "appeal.proposal.save", "appeal", appeal_id, {"action": payload.action})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/submit-approval")
def submit_appeal_approval(appeal_id: str, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.submit_appeal_approval(appeal_id, user.user_id, user.display_name)
        repository.record_service_message(result["session_id"], result["user_id"], "申诉调查已完成，处理方案正在等待管理员确认。")
        repository.audit(user.user_id, "appeal.approval.submit", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/approval")
def decide_appeal_approval(appeal_id: str, payload: AppealApprovalInput, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.approve_appeal(appeal_id, user.user_id, user.display_name, payload.decision, payload.comment)
        message = "申诉方案已批准，沙箱业务单已经创建，请确认处理结果。" if payload.decision == "approve" else f"申诉方案已退回补充调查：{payload.comment}"
        repository.record_service_message(result["session_id"], result["user_id"], message)
        repository.audit(user.user_id, f"appeal.approval.{payload.decision}", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/retry-execution")
def retry_appeal_execution(appeal_id: str, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    try:
        result = commerce_repository.execute_appeal(appeal_id)
        repository.audit(user.user_id, "appeal.execution.retry", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/confirm")
def confirm_appeal_result(appeal_id: str, payload: AppealCustomerFeedbackInput, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        result = commerce_repository.customer_feedback(appeal_id, user.user_id, "confirmed", payload.comment)
        if result.get("ticket_id"):
            repository.resolve_ticket(result["ticket_id"], user.user_id)
        repository.resolve_conversation(result["session_id"], user.user_id, "appeal_resolved", "用户确认申诉处理结果")
        repository.audit(user.user_id, "appeal.customer.confirm", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/object")
def object_appeal_result(appeal_id: str, payload: AppealCustomerFeedbackInput, user: AuthUser = Depends(require_roles("customer"))) -> dict:
    try:
        result = commerce_repository.customer_feedback(appeal_id, user.user_id, "objected", payload.comment)
        repository.record_customer_message(result["session_id"], result["user_id"], user.display_name, f"我对申诉处理结果仍有异议：{payload.comment or '请继续调查'}")
        repository.audit(user.user_id, "appeal.customer.object", "appeal", appeal_id, {})
        return result
    except CommerceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/appeals/{appeal_id}/attachments", status_code=201)
async def upload_appeal_attachment(
    appeal_id: str,
    file: UploadFile = File(...),
    material_request_id: str | None = Form(default=None),
    user: AuthUser = Depends(require_roles("customer")),
) -> dict:
    allowed = {"image/jpeg", "image/png", "application/pdf"}
    data = await file.read()
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG 和 PDF")
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="附件不能为空且不能超过 10 MB")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}[file.content_type]
    stored = attachment_root / f"{uuid4().hex}{suffix}"
    stored.write_bytes(data)
    try:
        attachment = commerce_repository.add_appeal_attachment(appeal_id, user.user_id, {
            "file_name": Path(file.filename or "attachment").name,
            "content_type": file.content_type,
            "storage_path": str(stored), "size_bytes": len(data),
            "material_request_id": material_request_id,
        })
        appeal = commerce_repository.get_appeal(appeal_id, user.user_id)
        if appeal:
            repository.record_customer_message(
                appeal["session_id"], appeal["user_id"], user.display_name,
                f"我已补充材料：{attachment['file_name']}",
            )
        return attachment
    except CommerceError as exc:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/appeals/{appeal_id}/attachments")
def appeal_attachments(appeal_id: str, user: AuthUser = Depends(current_user)) -> list[dict]:
    return commerce_repository.list_appeal_attachments(appeal_id, user.user_id if user.role == "customer" else None)


@app.get("/api/attachments/{attachment_id}")
def download_attachment(attachment_id: str, user: AuthUser = Depends(current_user)) -> FileResponse:
    record = commerce_repository.get_attachment(attachment_id)
    if not record or (user.role == "customer" and record["user_id"] != user.user_id):
        raise HTTPException(status_code=404, detail="附件不存在")
    return FileResponse(record["storage_path"], media_type=record["content_type"], filename=record["file_name"])


@app.get("/api/tickets")
def list_tickets(user: AuthUser = Depends(current_user)) -> list[dict]:
    return repository.list_tickets(user.user_id if user.role == "customer" else None)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, user: AuthUser = Depends(current_user)) -> dict:
    ticket = repository.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    if user.role == "customer" and ticket["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="无权查看该工单")
    return ticket


@app.post("/api/tickets/{ticket_id}/accept")
def accept_ticket(
    ticket_id: str,
    user: AuthUser = Depends(require_roles("admin")),
) -> dict:
    ticket = repository.assign_ticket(ticket_id, user.user_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    repository.takeover_conversation(ticket["session_id"], ticket["user_id"], user.user_id)
    repository.audit(user.user_id, "ticket.accept", "ticket", ticket_id, {})
    return ticket


@app.post("/api/tickets/{ticket_id}/replies")
def reply_ticket(
    ticket_id: str,
    request: TicketReplyRequest,
    user: AuthUser = Depends(current_user),
) -> dict:
    existing = repository.get_ticket(ticket_id)
    if not existing:
        raise HTTPException(status_code=404, detail="工单不存在")
    if user.role == "customer" and existing["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="无权回复该工单")
    ticket = repository.reply_ticket(ticket_id, user.user_id, user.role, request.content)
    if not ticket:
        raise HTTPException(status_code=409, detail="已解决的工单不能回复")
    if user.role == "admin":
        repository.reply_conversation(
            ticket["session_id"], ticket["user_id"], user.user_id, user.display_name, request.content,
        )
    else:
        repository.record_customer_message(
            ticket["session_id"], ticket["user_id"], user.display_name, request.content,
        )
    repository.audit(user.user_id, "ticket.reply", "ticket", ticket_id, {})
    return ticket


@app.post("/api/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: str,
    user: AuthUser = Depends(require_roles("admin")),
) -> dict:
    ticket = repository.resolve_ticket(ticket_id, user.user_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    repository.resolve_conversation(ticket["session_id"], ticket["user_id"], "ticket_resolved", "工单处理完成")
    repository.audit(user.user_id, "ticket.resolve", "ticket", ticket_id, {})
    return ticket


@app.get("/api/dashboard/metrics")
def dashboard_metrics(user: AuthUser = Depends(require_roles("admin"))) -> dict:
    clustered_gaps = None
    if knowledge_gap_service is not None:
        knowledge_gap_service.backfill(settings.knowledge_gap_backfill_limit)
        clustered_gaps = knowledge_gap_service.clusters()
    return {
        "operations": repository.operational_metrics(),
        "question_analytics": repository.question_analytics(clustered_gaps=clustered_gaps),
    }


@app.get("/api/admin/audit-logs")
def audit_logs(limit: int = 100, user: AuthUser = Depends(require_roles("admin"))) -> list[dict]:
    return repository.list_audit_logs(limit)


@app.post("/api/admin/knowledge/reload")
def reload_knowledge(user: AuthUser = Depends(require_roles("admin"))) -> dict:
    document_service.sync_markdown_directory(root)
    knowledge_base.reload()
    repository.audit(user.user_id, "knowledge.reload", "knowledge_base", "default", {})
    return {"status": "reloaded", "knowledge_chunks": len(knowledge_base.chunks)}


@app.post("/api/admin/knowledge/search")
def test_knowledge_search(
    request: KnowledgeSearchRequest,
    user: AuthUser = Depends(require_roles("admin")),
) -> dict:
    citations = knowledge_base.search(request.query, request.limit)
    return {
        "query": request.query,
        "count": len(citations),
        "results": [citation.model_dump() for citation in citations],
    }


@app.get("/api/admin/documents")
def list_documents(user: AuthUser = Depends(require_roles("admin"))) -> list[dict]:
    return repository.list_documents()


@app.get("/api/admin/documents/{doc_id}")
def get_document(doc_id: str, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    document = repository.get_document(doc_id, include_chunks=True)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return document


@app.post("/api/admin/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    version: str = Form(default="1.0"),
    visibility: str = Form(default="public"),
    user: AuthUser = Depends(require_roles("admin")),
) -> dict:
    try:
        document = document_service.upload(
            file.filename or "upload",
            await file.read(),
            title,
            version,
            visibility,
        )
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    knowledge_base.reload()
    repository.audit(user.user_id, "document.upload", "knowledge_document", document["doc_id"], document)
    return document


@app.patch("/api/admin/documents/{doc_id}/status")
def update_document_status(
    doc_id: str,
    update: DocumentStatusUpdate,
    user: AuthUser = Depends(require_roles("admin")),
) -> dict:
    document = repository.set_document_status(doc_id, update.status)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    knowledge_base.reload()
    repository.audit(user.user_id, "document.status", "knowledge_document", doc_id, {"status": update.status})
    return document


@app.delete("/api/admin/documents/{doc_id}")
def delete_document(doc_id: str, user: AuthUser = Depends(require_roles("admin"))) -> dict:
    existing = repository.get_document(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not doc_id.startswith("upload_"):
        raise HTTPException(status_code=409, detail="内置知识文档不能删除，只能禁用")
    document = repository.delete_document(doc_id)
    document_service.delete_source(existing)
    knowledge_base.reload()
    repository.audit(user.user_id, "document.delete", "knowledge_document", doc_id, existing)
    return {"status": "deleted", "doc_id": document["doc_id"]}
