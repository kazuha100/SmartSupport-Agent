import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleDot, Clock3, MessageSquareReply, MessagesSquare, RefreshCw, Send, TicketCheck, UserRoundCheck, X } from "lucide-react";
import { acceptTicket, AuthUser, getTicket, listTickets, replyTicket, resolveTicket, Ticket, TicketDetail } from "../lib/api";

const statusLabels = { open: "待接单", assigned: "处理中", resolved: "已解决" };
const reasonLabels: Record<string, string> = {
  human_handoff: "人工服务",
  refund_request: "退款审批",
  knowledge_qa: "知识咨询",
  logistics: "物流异常",
  warranty: "售后保修",
  invoice: "发票处理",
  order_change: "订单修改",
  membership: "会员权益",
  payment_issue: "支付异常",
  account_security: "账号安全"
};

type TicketDeskProps = {
  user: AuthUser;
  onOpenConversation: (sessionId: string) => void;
};

export default function TicketDesk({ user, onOpenConversation }: TicketDeskProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<TicketDetail | null>(null);
  const [filter, setFilter] = useState<"all" | Ticket["status"]>("all");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const filtered = useMemo(
    () => filter === "all" ? tickets : tickets.filter((ticket) => ticket.status === filter),
    [filter, tickets]
  );

  async function refresh() {
    setError("");
    try { setTickets(await listTickets()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "工单加载失败"); }
  }

  useEffect(() => { void refresh(); }, []);

  async function inspect(ticketId: string) {
    setError("");
    try { setSelected(await getTicket(ticketId)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "工单加载失败"); }
  }

  async function accept() {
    if (!selected) return;
    setBusy(true);
    try {
      const accepted = await acceptTicket(selected.ticket_id);
      await refresh();
      onOpenConversation(accepted.session_id);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "接单失败"); }
    finally { setBusy(false); }
  }

  async function submitReply(event: FormEvent) {
    event.preventDefault();
    if (!selected || !reply.trim()) return;
    setBusy(true);
    try { setSelected(await replyTicket(selected.ticket_id, reply.trim())); setReply(""); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "回复失败"); }
    finally { setBusy(false); }
  }

  async function resolve() {
    if (!selected) return;
    setBusy(true);
    try { setSelected(await resolveTicket(selected.ticket_id)); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "解决工单失败"); }
    finally { setBusy(false); }
  }

  return (
    <main className="ticket-workspace">
      <header className="knowledge-header">
        <div><h1>{user.role === "customer" ? "我的工单" : "工单中心"}</h1><span>人工服务与处理记录</span></div>
        <button className="secondary-button" onClick={() => void refresh()} title="刷新"><RefreshCw size={16} /></button>
      </header>
      {error && <div className="error-banner">{error}<button onClick={() => setError("")} title="关闭"><X size={14} /></button></div>}
      <section className="ticket-filter" role="tablist">
        {(["all", "open", "assigned", "resolved"] as const).map((value) => (
          <button role="tab" aria-selected={filter === value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)} key={value}>
            {value === "all" ? "全部" : statusLabels[value]}
            <span>{value === "all" ? tickets.length : tickets.filter((item) => item.status === value).length}</span>
          </button>
        ))}
      </section>
      <section className="ticket-list">
        {filtered.map((ticket) => (
          <button className="ticket-item" key={ticket.ticket_id} onClick={() => void inspect(ticket.ticket_id)}>
            <span className={`ticket-state ${ticket.status}`}>{ticket.status === "resolved" ? <CheckCircle2 size={17} /> : ticket.status === "assigned" ? <Clock3 size={17} /> : <CircleDot size={17} />}</span>
            <span className="ticket-main"><strong>{reasonLabels[ticket.reason] ?? ticket.reason}</strong><small>{ticket.summary}</small></span>
            <span className={`priority ${ticket.priority}`}>{ticket.priority === "high" ? "高" : "普通"}</span>
            <span className="ticket-meta"><strong>{ticket.ticket_id}</strong><small>{statusLabels[ticket.status]}</small></span>
          </button>
        ))}
        {filtered.length === 0 && <div className="empty-table"><TicketCheck size={25} /><span>暂无工单</span></div>}
      </section>

      {selected && (
        <aside className="ticket-drawer">
          <header><div><strong>{reasonLabels[selected.reason] ?? selected.reason}</strong><span>{selected.ticket_id} · {statusLabels[selected.status]}</span></div><button onClick={() => setSelected(null)} title="关闭"><X size={18} /></button></header>
          <div className="ticket-detail-scroll">
            <section className="ticket-summary"><small>会话摘要</small><p>{selected.summary}</p></section>
            <section className="ticket-properties"><div><span>优先级</span><strong>{selected.priority === "high" ? "高" : "普通"}</strong></div><div><span>处理人</span><strong>{selected.assigned_to ?? "未分配"}</strong></div></section>
            <section className="reply-history">
              <h2><MessageSquareReply size={15} /> 回复记录</h2>
              {selected.replies.map((item, index) => <article key={`${item.created_at}-${index}`}><div><strong>{item.author_role === "customer" ? "顾客" : "客服"}</strong><time>{new Date(item.created_at).toLocaleString("zh-CN")}</time></div><p>{item.content}</p></article>)}
              {selected.replies.length === 0 && <span className="no-replies">暂无回复</span>}
            </section>
          </div>
          <footer className="ticket-actions">
            {user.role !== "customer" && selected.status === "open" && <button className="accept-button" disabled={busy} onClick={() => void accept()}><UserRoundCheck size={16} /> 接单并进入会话</button>}
            {user.role !== "customer" && selected.status === "assigned" && <button className="accept-button" disabled={busy} onClick={() => onOpenConversation(selected.session_id)}><MessagesSquare size={16} /> 进入客服工作台</button>}
            {selected.status !== "resolved" && <form onSubmit={submitReply}><input value={reply} onChange={(event) => setReply(event.target.value)} placeholder="输入人工回复" /><button disabled={busy || !reply.trim()} title="发送回复"><Send size={16} /></button></form>}
            {user.role !== "customer" && selected.status !== "resolved" && <button className="resolve-button" disabled={busy} onClick={() => void resolve()}><CheckCircle2 size={16} /> 解决工单</button>}
          </footer>
        </aside>
      )}
    </main>
  );
}
