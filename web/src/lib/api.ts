export interface Citation {
  doc_id: string;
  title: string;
  section: string;
  version: string;
  excerpt: string;
  score: number;
}

export interface ToolCall {
  name: string;
  status: "success" | "blocked" | "pending";
  arguments: Record<string, string>;
  summary: string;
}

export interface TraceStep {
  name: string;
  detail: string;
  status: "done" | "waiting" | "blocked";
}

export interface AgentExecution {
  agent: string;
  intent: string;
  status: "completed" | "blocked" | "waiting" | "failed";
  summary: string;
  answer: string;
  findings: string[];
  evidence_ids: string[];
  tool_calls: Array<Record<string, unknown>>;
  citations: string[];
  confidence: number;
  needs_human: boolean;
  next_action: string | null;
  order_id: string | null;
  appeal_id: string | null;
}

export interface AgentResponse {
  answer: string;
  intent: string;
  confidence: number;
  needs_human: boolean;
  citations: Citation[];
  tool_calls: ToolCall[];
  trace: TraceStep[];
  ticket_id: string | null;
  route?: string | null;
  current_stage?: string | null;
  agent_results?: AgentExecution[];
  appeal_id?: string | null;
  risk_review?: { requires_approval: boolean; agent: string } | null;
}

export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  result: AgentResponse | null;
  created_at: string;
  sender_type: "customer" | "ai" | "agent";
  sender_id: string | null;
  sender_name: string;
  attachment?: ProductShareAttachment | null;
}

export interface ProductShareAttachment {
  type: "product";
  product: Pick<ShopProduct, "product_id" | "name" | "category" | "description" | "price_cents" | "image_url">;
}

export interface ConversationSummary {
  session_id: string;
  user_id: string;
  display_name: string;
  last_user_message: string;
  last_assistant_message: string;
  message_count: number;
  updated_at: string;
  status: "bot_active" | "waiting_human" | "human_active" | "resolved";
  priority: "normal" | "high";
  assigned_to: string | null;
  product_id: string | null;
  order_id: string | null;
  first_response_due_at: string | null;
  resolve_due_at: string | null;
  resolved_at: string | null;
  resolution_code: string | null;
  resolution_summary: string | null;
  suggested_reply: string | null;
  tags: string[];
  unread_count: number;
  is_overdue: boolean;
}

export interface KnowledgeDocument {
  doc_id: string;
  title: string;
  file_name: string;
  source_type: string;
  version: string;
  status: "active" | "disabled";
  visibility: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  product_id: string | null;
  document_category: string;
}

export interface DocumentChunk {
  position: number;
  section: string;
  content: string;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  content: string;
  chunks: DocumentChunk[];
}

export interface AuthUser {
  user_id: string;
  username: string;
  display_name: string;
  role: "customer" | "agent" | "admin";
}

export interface ShopProduct {
  product_id: string;
  name: string;
  category: string;
  description: string;
  price_cents: number;
  stock: number;
  image_url: string;
  specs: Record<string, string>;
  warranty_months: number;
}

export interface ShopCartItem extends ShopProduct {
  quantity: number;
  cart_item_id: number;
}

export interface ShopCart {
  items: ShopCartItem[];
  total_cents: number;
}

export interface ShopAddress {
  address_id: string;
  recipient: string;
  phone: string;
  province: string;
  city: string;
  detail: string;
  is_default: boolean;
}

export interface ShopOrder {
  order_id: string;
  user_id: string;
  status: string;
  payment_status: string;
  shipping_status: string;
  total_cents: number;
  address: ShopAddress;
  created_at: string;
  paid_at: string | null;
  items: Array<{ product_id: string; name: string; image_url: string; price_cents: number; quantity: number }>;
  payment: { payment_id: string; status: string; method: string } | null;
  shipment: { carrier: string; tracking_number: string; status: string; latest_event: string; events: Array<{ status: string; content: string; at: string }> } | null;
}

export interface OrderAppeal {
  appeal_id: string;
  order_id: string;
  user_id: string;
  session_id: string;
  ticket_id: string | null;
  appeal_type: string;
  description: string;
  priority: string;
  status: string;
  agent_result: AgentResponse | null;
  assigned_to: string | null;
  assigned_name: string | null;
  accepted_at: string | null;
  responsibility: string | null;
  investigation_conclusion: string | null;
  proposed_action: string | null;
  proposed_amount_cents: number | null;
  proposal_reason: string | null;
  risk_level: string | null;
  risk_reasons: string[];
  approved_by: string | null;
  approved_name: string | null;
  approval_comment: string | null;
  approved_at: string | null;
  customer_confirmation: string | null;
  resolved_at: string | null;
  order_total_cents: number;
  created_at: string;
  updated_at: string;
  attachments: AppealAttachment[];
  material_requests: AppealMaterialRequest[];
  events: AppealEvent[];
  executions: AppealExecution[];
  execution: AppealExecution | null;
}

export interface AppealAttachment {
  attachment_id: string;
  appeal_id: string;
  material_request_id: string | null;
  file_name: string;
  content_type: string;
  size_bytes: number;
  review_status: string;
  reviewed_name: string | null;
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AppealMaterialRequest { request_id: string; content: string; status: string; requested_name: string; due_at: string | null; completed_at: string | null; created_at: string }
export interface AppealEvent { id: number; actor_name: string; actor_role: string; event_type: string; title: string; detail: Record<string, unknown>; from_status: string | null; to_status: string | null; visible_to_customer: boolean; created_at: string }
export interface AppealExecution { execution_id: string; approval_round: number; action: string; amount_cents: number | null; status: string; sandbox_reference: string; result: { sandbox?: boolean; message?: string }; error_message: string | null; created_at: string; updated_at: string }

export interface ConversationNote { id: number; author_name: string; content: string; created_at: string }
export interface QuickReply { id: number; category: string; title: string; content: string }
export interface CustomerContext {
  customer: AuthUser & { created_at: string };
  member_status: string;
  conversations: ConversationSummary[];
  orders: ShopOrder[];
  tickets: Ticket[];
  appeals: OrderAppeal[];
}

export interface Ticket {
  ticket_id: string;
  session_id: string;
  user_id: string;
  status: "open" | "assigned" | "resolved";
  priority: "normal" | "high";
  reason: string;
  summary: string;
  assigned_to: string | null;
  reply_count: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface TicketReply {
  author_id: string;
  author_role: string;
  content: string;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  replies: TicketReply[];
}

export interface QuestionFrequency {
  cluster_id?: string;
  question: string;
  product_id?: string | null;
  count: number;
  last_asked_at: string;
  variants?: Array<{
    question: string;
    count: number;
  }>;
  occurrences: Array<{
    message_id: number;
    session_id: string;
    user_id: string;
    display_name: string;
    product_id: string | null;
    order_id: string | null;
    conversation_status: string;
    question?: string;
    similarity?: number;
    asked_at: string;
  }>;
}

export interface DashboardMetrics {
  operations: {
    documents: number;
    chunks: number;
    conversations: number;
    messages: number;
    tickets: { open: number; assigned: number; resolved: number };
    average_confidence: number;
    human_handoff_rate: number;
    tool_call_rate: number;
    model_calls: number;
    average_model_latency_ms: number;
    average_first_response_seconds: number;
    overdue_rate: number;
    resolution_rate: number;
    average_satisfaction: number;
    rating_count: number;
  };
  question_analytics: {
    total_questions: number;
    unique_questions: number;
    knowledge_questions: number;
    uncovered_count: number;
    coverage_rate: number;
    top_questions: QuestionFrequency[];
    uncovered_questions: QuestionFrequency[];
  };
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

const TOKEN_KEY = "smart-support-token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const result = await parseResponse<LoginResponse>(await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  }));
  localStorage.setItem(TOKEN_KEY, result.access_token);
  return result.user;
}

export async function register(username: string, displayName: string, password: string): Promise<AuthUser> {
  const result = await parseResponse<LoginResponse>(await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, display_name: displayName, password })
  }));
  localStorage.setItem(TOKEN_KEY, result.access_token);
  return result.user;
}

export async function getCurrentUser(): Promise<AuthUser> {
  return parseResponse(await apiFetch("/api/auth/me"));
}

export async function listConversationMessages(sessionId: string, userId?: string): Promise<ConversationMessage[]> {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/messages${query}`));
}

export async function listConversations(filters: { prefix?: string; status?: string; query?: string; overdue?: boolean; limit?: number } = {}): Promise<ConversationSummary[]> {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 100) });
  if (filters.prefix) params.set("prefix", filters.prefix);
  if (filters.status) params.set("status", filters.status);
  if (filters.query) params.set("query", filters.query);
  if (filters.overdue) params.set("overdue", "true");
  return parseResponse(await apiFetch(`/api/conversations?${params.toString()}`));
}

export async function listShopProducts(): Promise<ShopProduct[]> {
  return parseResponse(await apiFetch("/api/shop/products"));
}

export async function getShopCart(): Promise<ShopCart> {
  return parseResponse(await apiFetch("/api/shop/cart"));
}

export async function addShopCartItem(productId: string, quantity = 1): Promise<ShopCart> {
  return parseResponse(await apiFetch("/api/shop/cart/items", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ product_id: productId, quantity })
  }));
}

export async function updateShopCartItem(itemId: number, quantity: number): Promise<ShopCart> {
  return parseResponse(await apiFetch(`/api/shop/cart/items/${itemId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantity })
  }));
}

export async function listShopAddresses(): Promise<ShopAddress[]> {
  return parseResponse(await apiFetch("/api/shop/addresses"));
}

export async function createShopAddress(payload: Omit<ShopAddress, "address_id">): Promise<ShopAddress> {
  return parseResponse(await apiFetch("/api/shop/addresses", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  }));
}

export async function updateShopAddress(addressId: string, payload: Omit<ShopAddress, "address_id">): Promise<ShopAddress> {
  return parseResponse(await apiFetch(`/api/shop/addresses/${addressId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  }));
}

export async function deleteShopAddress(addressId: string): Promise<void> {
  const response = await apiFetch(`/api/shop/addresses/${addressId}`, { method: "DELETE" });
  if (!response.ok) throw new Error("删除地址失败");
}

export async function createShopOrder(addressId: string): Promise<ShopOrder> {
  return parseResponse(await apiFetch("/api/shop/orders", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address_id: addressId })
  }));
}

export async function payShopOrder(orderId: string): Promise<ShopOrder> {
  return parseResponse(await apiFetch(`/api/shop/orders/${orderId}/pay`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ success: true })
  }));
}

export async function listShopOrders(): Promise<ShopOrder[]> {
  return parseResponse(await apiFetch("/api/shop/orders"));
}

export async function createOrderAppeal(orderId: string, sessionId: string, appealType: string, description: string): Promise<{ appeal: { appeal_id: string; status: string; ticket_id: string | null }; agent_response: AgentResponse }> {
  return parseResponse(await apiFetch(`/api/orders/${orderId}/appeals`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, appeal_type: appealType, description })
  }));
}

export async function listOrderAppeals(): Promise<OrderAppeal[]> {
  return parseResponse(await apiFetch("/api/appeals"));
}

export async function getOrderAppeal(appealId: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}`)); }
export async function acceptAppeal(appealId: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/accept`, { method: "POST" })); }
export async function requestAppealMaterial(appealId: string, content: string, dueAt?: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/material-requests`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content, due_at: dueAt || null }) })); }
export async function reviewAppealAttachment(appealId: string, attachmentId: string, status: "accepted" | "rejected", note: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/attachments/${attachmentId}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status, note }) })); }
export async function saveAppealInvestigation(appealId: string, responsibility: string, conclusion: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/investigation`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ responsibility, conclusion }) })); }
export async function saveAppealProposal(appealId: string, action: string, amountCents: number | null, reason: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/proposal`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, amount_cents: amountCents, reason }) })); }
export async function submitAppealApproval(appealId: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/submit-approval`, { method: "POST" })); }
export async function decideAppealApproval(appealId: string, decision: "approve" | "return", comment: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/approval`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment }) })); }
export async function retryAppealExecution(appealId: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/retry-execution`, { method: "POST" })); }
export async function confirmAppeal(appealId: string, comment = ""): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment }) })); }
export async function objectAppeal(appealId: string, comment: string): Promise<OrderAppeal> { return parseResponse(await apiFetch(`/api/appeals/${appealId}/object`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment }) })); }

export async function uploadAppealAttachment(appealId: string, file: File, materialRequestId?: string): Promise<AppealAttachment> {
  const form = new FormData(); form.append("file", file);
  if (materialRequestId) form.append("material_request_id", materialRequestId);
  return parseResponse(await apiFetch(`/api/appeals/${appealId}/attachments`, { method: "POST", body: form }));
}

export async function listAppealAttachments(appealId: string): Promise<AppealAttachment[]> {
  return parseResponse(await apiFetch(`/api/appeals/${appealId}/attachments`));
}

export async function sendMessage(message: string, sessionId: string, context: { productId?: string; orderId?: string } = {}): Promise<AgentResponse> {
  const response = await apiFetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message, product_id: context.productId, order_id: context.orderId
    })
  });
  if (!response.ok) {
    throw new Error("客服服务暂时不可用");
  }
  return response.json();
}

export async function shareProduct(sessionId: string, productId: string): Promise<{ created: boolean; message_id: number; product_id: string }> {
  return parseResponse(await apiFetch("/api/chat/product-share", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, product_id: productId })
  }));
}

export async function sendMessageStream(
  message: string,
  onDelta: (content: string) => void,
  sessionId: string,
  onStatus?: (status: string) => void,
  context: { productId?: string; orderId?: string } = {}
): Promise<AgentResponse> {
  const response = await apiFetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, product_id: context.productId, order_id: context.orderId })
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "客服服务暂时不可用");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AgentResponse | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as { type: "status" | "delta" | "done"; content?: string; data?: AgentResponse };
      if (event.type === "status" && event.content) onStatus?.(event.content);
      if (event.type === "delta" && event.content) onDelta(event.content);
      if (event.type === "done" && event.data) result = event.data;
    }
    if (done) break;
  }
  if (!result) throw new Error("流式响应未正常结束");
  return result;
}

function formatApiError(detail: unknown): string | null {
  if (typeof detail === "string") return detail || null;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => {
      if (!item || typeof item !== "object") return null;
      const issue = item as { loc?: unknown[]; type?: string; msg?: string };
      const field = issue.loc?.[issue.loc.length - 1];
      if (field === "username" && issue.type === "string_pattern_mismatch") return "用户名须为 4–32 位字母、数字或下划线";
      if (field === "password" && issue.type === "string_too_short") return "密码至少需要 8 位，且包含字母和数字";
      if (field === "password" && issue.type === "string_too_long") return "密码不能超过 72 位";
      if (field === "display_name") return "显示名称须为 2–40 个字符";
      return typeof issue.msg === "string" ? issue.msg : null;
    }).filter((message): message is string => Boolean(message));
    return messages.length ? [...new Set(messages)].join("；") : null;
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") return detail.message;
  return null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const message = formatApiError(payload?.detail);
    if (message) throw new Error(message);
    if (response.status === 401) throw new Error("登录状态已失效，请重新登录");
    if (response.status === 403) throw new Error("当前账号没有执行此操作的权限");
    if (response.status === 404) throw new Error("请求的数据不存在或已被删除");
    if (response.status >= 500) throw new Error("后台服务暂时不可用，请稍后重试");
    throw new Error(`操作未完成（HTTP ${response.status}）`);
  }
  return response.json();
}

export async function listDocuments(): Promise<KnowledgeDocument[]> {
  return parseResponse(await apiFetch("/api/admin/documents"));
}

export async function getDocument(docId: string): Promise<KnowledgeDocumentDetail> {
  return parseResponse(await apiFetch(`/api/admin/documents/${docId}`));
}

export async function uploadDocument(form: FormData): Promise<KnowledgeDocument> {
  return parseResponse(await apiFetch("/api/admin/documents", { method: "POST", body: form }));
}

export async function setDocumentStatus(
  docId: string,
  status: "active" | "disabled"
): Promise<KnowledgeDocument> {
  return parseResponse(await apiFetch(`/api/admin/documents/${docId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status })
  }));
}

export async function deleteDocument(docId: string): Promise<void> {
  await parseResponse(await apiFetch(`/api/admin/documents/${docId}`, { method: "DELETE" }));
}

export async function listTickets(): Promise<Ticket[]> {
  return parseResponse(await apiFetch("/api/tickets"));
}

export async function getTicket(ticketId: string): Promise<TicketDetail> {
  return parseResponse(await apiFetch(`/api/tickets/${ticketId}`));
}

export async function acceptTicket(ticketId: string): Promise<Ticket> {
  return parseResponse(await apiFetch(`/api/tickets/${ticketId}/accept`, { method: "POST" }));
}

export async function replyTicket(ticketId: string, content: string): Promise<TicketDetail> {
  return parseResponse(await apiFetch(`/api/tickets/${ticketId}/replies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content })
  }));
}

export async function resolveTicket(ticketId: string): Promise<TicketDetail> {
  return parseResponse(await apiFetch(`/api/tickets/${ticketId}/resolve`, { method: "POST" }));
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  return parseResponse(await apiFetch("/api/dashboard/metrics"));
}

export async function takeoverConversation(sessionId: string, userId: string): Promise<ConversationSummary> {
  return conversationAction(sessionId, "takeover", userId);
}
export async function releaseConversation(sessionId: string, userId: string): Promise<ConversationSummary> {
  return conversationAction(sessionId, "release", userId);
}
export async function resolveConversation(sessionId: string, userId: string, resolutionCode: string, resolutionSummary: string): Promise<ConversationSummary> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, resolution_code: resolutionCode, resolution_summary: resolutionSummary })
  }));
}
async function conversationAction(sessionId: string, action: string, userId: string): Promise<ConversationSummary> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId })
  }));
}
export async function replyConversation(sessionId: string, userId: string, content: string): Promise<ConversationSummary> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/replies`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, content })
  }));
}
export async function listConversationNotes(sessionId: string, userId: string): Promise<ConversationNote[]> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/notes?user_id=${encodeURIComponent(userId)}`));
}
export async function addConversationNote(sessionId: string, userId: string, content: string): Promise<ConversationNote> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/notes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId, content })
  }));
}
export async function rateConversation(sessionId: string, score: number, tags: string[], comment: string): Promise<{ score: number }> {
  return parseResponse(await apiFetch(`/api/conversations/${sessionId}/rating`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ score, tags, comment })
  }));
}
export async function listQuickReplies(): Promise<QuickReply[]> { return parseResponse(await apiFetch("/api/agent/quick-replies")); }
export async function getCustomerContext(userId: string): Promise<CustomerContext> { return parseResponse(await apiFetch(`/api/agent/customer-context/${userId}`)); }
