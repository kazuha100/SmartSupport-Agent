import { FormEvent, useEffect, useState } from "react";
import {
  BarChart3, Bot, CheckCircle2, Clock3, FileText, Headphones, Library,
  LogOut, MessageSquareText, MessagesSquare, Search, Send,
  ShieldCheck, StickyNote, UserRound, UserRoundCheck
} from "lucide-react";
import {
  addConversationNote, AuthUser, clearToken, ConversationMessage, ConversationNote,
  ConversationSummary, CustomerContext, getCurrentUser, getCustomerContext,
  listConversationMessages, listConversationNotes, listConversations, listQuickReplies,
  QuickReply, releaseConversation, replyConversation, resolveConversation, takeoverConversation
} from "./lib/api";
import KnowledgeAdmin from "./components/KnowledgeAdmin";
import LoginScreen from "./components/LoginScreen";
import TicketDesk from "./components/TicketDesk";
import QualityDashboard from "./components/QualityDashboard";
import CustomerStorefront from "./components/CustomerStorefront";
import AppealDesk from "./components/AppealDesk";

type View = "conversations" | "tickets" | "appeals" | "knowledge" | "quality";
const STATUS: Record<string, string> = { bot_active: "智能客服处理中", waiting_human: "待人工", human_active: "人工处理中", resolved: "已解决" };
const relative = (value: string) => { const mins = Math.max(0, Math.round((Date.now()-new Date(value).getTime())/60000)); return mins < 1 ? "刚刚" : mins < 60 ? `${mins} 分钟前` : `${Math.round(mins/60)} 小时前`; };
const time = (value: string) => new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
const money = (cents: number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(cents / 100);
const remaining = (value: string | null) => { if (!value) return "--"; const mins=Math.round((new Date(value).getTime()-Date.now())/60000); return mins < 0 ? `超时 ${Math.abs(mins)} 分钟` : mins < 60 ? `${mins} 分钟` : `${Math.floor(mins/60)} 小时`; };

function SharedProductCard({ message }: { message: ConversationMessage }) {
  const product = message.attachment?.product;
  if (!product) return <p>{message.content}</p>;
  return <div className="agent-product-card"><img src={product.image_url} alt={product.name}/><span><small>{product.category} · {product.product_id}</small><strong>{product.name}</strong><p>{product.description}</p><em>{money(product.price_cents)}</em></span></div>;
}

function Workbench({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [view, setView] = useState<View>("conversations");
  const [queue, setQueue] = useState<ConversationSummary[]>([]);
  const [selected, setSelected] = useState<ConversationSummary | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [context, setContext] = useState<CustomerContext | null>(null);
  const [notes, setNotes] = useState<ConversationNote[]>([]);
  const [quickReplies, setQuickReplies] = useState<QuickReply[]>([]);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadQueue() {
    try {
      const items = await listConversations({ status: filter === "all" || filter === "overdue" ? undefined : filter, query: search || undefined, overdue: filter === "overdue" });
      setQueue(items); setSelected(current => current ? items.find(x=>x.session_id===current.session_id) ?? current : items[0] ?? null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "队列加载失败"); }
  }
  async function loadConversation(item: ConversationSummary) {
    setSelected(item);
    const [m,c,n] = await Promise.all([listConversationMessages(item.session_id,item.user_id),getCustomerContext(item.user_id),listConversationNotes(item.session_id,item.user_id)]);
    setMessages(m); setContext(c); setNotes(n);
  }
  useEffect(()=>{ void loadQueue(); void listQuickReplies().then(setQuickReplies); },[filter]);
  useEffect(()=>{ if(view!=="conversations")return; const timer=window.setInterval(()=>{void loadQueue(); if(selected)void listConversationMessages(selected.session_id,selected.user_id).then(setMessages)},3000); return()=>clearInterval(timer); },[view,selected?.session_id,filter,search]);
  useEffect(()=>{ if(selected)void loadConversation(selected); },[selected?.session_id]);
  async function takeOver() { if(!selected)return; setBusy(true); try{const next=await takeoverConversation(selected.session_id,selected.user_id);setSelected(next);setReply(next.suggested_reply??"");await loadQueue();}catch(e){setError(e instanceof Error?e.message:"接管失败")}finally{setBusy(false)} }
  async function release() { if(!selected)return; setBusy(true); try{setSelected(await releaseConversation(selected.session_id,selected.user_id));await loadQueue();}catch(e){setError(e instanceof Error?e.message:"交还失败")}finally{setBusy(false)} }
  async function sendReply(event:FormEvent){event.preventDefault();if(!selected||!reply.trim())return;setBusy(true);try{setSelected(await replyConversation(selected.session_id,selected.user_id,reply.trim()));setReply("");setMessages(await listConversationMessages(selected.session_id,selected.user_id));await loadQueue();}catch(e){setError(e instanceof Error?e.message:"发送失败")}finally{setBusy(false)} }
  async function saveNote(){if(!selected||!note.trim())return;try{await addConversationNote(selected.session_id,selected.user_id,note.trim());setNote("");setNotes(await listConversationNotes(selected.session_id,selected.user_id));}catch(e){setError(e instanceof Error?e.message:"备注失败")} }
  async function resolve(){if(!selected)return;const code=window.prompt("处理结果（例如：已解答、已退款、已维修）");if(!code)return;const summary=window.prompt("请输入结案总结");if(!summary)return;try{setSelected(await resolveConversation(selected.session_id,selected.user_id,code,summary));await loadQueue();}catch(e){setError(e instanceof Error?e.message:"结案失败")} }

  const nav=[{id:"conversations",label:"客服工作台",icon:MessagesSquare},{id:"tickets",label:"工单中心",icon:FileText},{id:"appeals",label:"申诉调查",icon:ShieldCheck},{id:"knowledge",label:"知识库",icon:Library},{id:"quality",label:"质量看板",icon:BarChart3}] as const;
  return <main className="app-shell enterprise-shell"><aside className="main-sidebar"><div className="brand"><span><Headphones/></span><div><strong>SmartSupport</strong><small>客服运营中心</small></div></div><nav>{nav.map(item=><button key={item.id} className={view===item.id?"active":""} onClick={()=>setView(item.id)}><item.icon size={18}/>{item.label}</button>)}</nav><div className="sidebar-user"><UserRound size={18}/><span><strong>{user.display_name}</strong><small>全权限客服账号</small></span><button onClick={onLogout}><LogOut size={17}/></button></div></aside>
    {view==="tickets"&&<TicketDesk user={user} onOpenConversation={(sessionId)=>{setView("conversations");const item=queue.find(x=>x.session_id===sessionId);if(item)setSelected(item)}}/>}
    {view==="appeals"&&<AppealDesk user={user} onOpenConversation={(sessionId)=>{setView("conversations");const item=queue.find(x=>x.session_id===sessionId);if(item)setSelected(item)}}/>} {view==="knowledge"&&<KnowledgeAdmin/>} {view==="quality"&&<QualityDashboard/>} 
    {view==="conversations"&&<section className="agent-workbench">
      <aside className="queue-pane"><header><div><h1>会话队列</h1><span>{queue.filter(x=>x.unread_count>0).length} 个会话有新消息</span></div><label><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>e.key==="Enter"&&void loadQueue()} placeholder="用户、订单、会话或关键词"/></label><div className="queue-filters">{[["all","全部"],["waiting_human","待人工"],["human_active","处理中"],["overdue","已超时"],["resolved","已解决"]].map(([id,label])=><button key={id} className={filter===id?"active":""} onClick={()=>setFilter(id)}>{label}</button>)}</div></header><div className="queue-list">{queue.map(item=><button key={`${item.session_id}-${item.user_id}`} className={`${selected?.session_id===item.session_id?"active":""} ${item.is_overdue?"overdue":""}`} onClick={()=>void loadConversation(item)}><span className="avatar">{item.display_name.slice(0,1)}</span><div><div><strong>{item.display_name}</strong><time>{relative(item.updated_at)}</time></div><p>{item.last_user_message||item.last_assistant_message}</p><small>{item.product_id??item.order_id??"售前咨询"} · {STATUS[item.status]}</small></div>{item.unread_count>0&&<b>{item.unread_count}</b>}<em className={item.priority}>{item.priority==="high"?"高":"普"}</em></button>)}{!queue.length&&<div className="empty-queue"><CheckCircle2/><strong>当前没有匹配的会话</strong></div>}</div></aside>
      {selected?<section className="conversation-pane"><header><div className="conversation-title"><span className="avatar">{selected.display_name.slice(0,1)}</span><div><h2>{selected.display_name}</h2><p>{selected.session_id} · {STATUS[selected.status]}</p></div></div><div className="sla-strip"><span><Clock3 size={15}/>首响 {remaining(selected.first_response_due_at)}</span><span className={selected.is_overdue?"danger":""}>解决 {remaining(selected.resolve_due_at)}</span></div><div className="conversation-actions">{selected.status!=="human_active"&&selected.status!=="resolved"&&<button onClick={()=>void takeOver()} disabled={busy}><UserRoundCheck size={16}/>接管</button>}{selected.status==="human_active"&&<button onClick={()=>void release()}><Bot size={16}/>交还智能客服</button>}{selected.status!=="resolved"&&<button className="primary" onClick={()=>void resolve()}><CheckCircle2 size={16}/>标记已解决</button>}</div></header>
      <div className="customer-overview" aria-label="客户概览"><div><span>客户</span><strong>@{context?.customer.username??"--"}</strong></div><div><span>注册时间</span><strong>{context?.customer.created_at?new Date(context.customer.created_at).toLocaleDateString("zh-CN"):"--"}</strong></div><div><span>会员</span><strong>{context?.member_status??"--"}</strong></div><div className="customer-order"><span>关联订单</span><strong>{selected.order_id??context?.orders[0]?.order_id??"暂无订单"}</strong></div><div><span>历史记录</span><strong>{context?.conversations.length??0} 会话 · {context?.tickets.length??0} 工单 · {context?.appeals.length??0} 申诉</strong></div></div>
      <div className="message-scroll">{messages.map(message=><article key={message.id} className={`agent-message ${message.sender_type==="customer"?"customer":"support"}`}><div><strong>{message.sender_name}</strong><time>{time(message.created_at)}</time></div><SharedProductCard message={message}/>{message.result?.citations?.length?<small>知识引用：{message.result.citations.map(c=>c.title).join("、")}</small>:null}</article>)}</div><form className="agent-composer" onSubmit={sendReply}><details className="conversation-notes"><summary><StickyNote size={14}/>内部备注{notes.length>0&&<span>{notes.length}</span>}</summary><div className="notes-panel"><div>{notes.map(n=><div className="note-item" key={n.id}><strong>{n.author_name}</strong><p>{n.content}</p></div>)}{!notes.length&&<p className="muted">暂无内部备注</p>}</div><div className="note-entry"><textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="仅客服和管理员可见"/><button type="button" onClick={()=>void saveNote()}>保存</button></div></div></details><div className="quick-replies">{quickReplies.map(item=><button type="button" key={item.id} title={item.category} onClick={()=>setReply(item.content)}>{item.title}</button>)}</div>{selected.suggested_reply&&<button type="button" className="suggested-reply" onClick={()=>setReply(selected.suggested_reply??"")}><Bot size={15}/>采用智能建议：{selected.suggested_reply}</button>}<div><textarea value={reply} onChange={e=>setReply(e.target.value)} disabled={selected.status!=="human_active"} placeholder={selected.status==="human_active"?"编辑后发送给顾客":"接管会话后可人工回复"}/><button disabled={busy||selected.status!=="human_active"||!reply.trim()}><Send size={18}/></button></div></form></section>:<div className="workbench-empty"><MessageSquareText/><strong>选择一个真实会话开始处理</strong></div>}
    </section>}
    {error&&<div className="global-toast">{error}<button onClick={()=>setError("")}>关闭</button></div>}
  </main>;
}

export default function App(){
  const storefront=import.meta.env.VITE_PORTAL==="storefront";
  const [user,setUser]=useState<AuthUser|null>(null); const [loading,setLoading]=useState(true);
  useEffect(()=>{getCurrentUser().then(setUser).catch(()=>clearToken()).finally(()=>setLoading(false))},[]);
  const logout=()=>{clearToken();setUser(null)};
  if(loading)return <main className="boot-screen"><Bot/><span>正在连接服务…</span></main>;
  if(!user)return <LoginScreen portal={storefront?"storefront":"employee"} onLogin={setUser}/>;
  return storefront?<CustomerStorefront user={user} onLogout={logout}/>:<Workbench user={user} onLogout={logout}/>;
}
