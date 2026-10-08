import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, Bot, CheckCircle2, ChevronRight, Clock3, FileUp, Headphones, Home,
  LogOut, MessageCircle, Minus, PackageCheck, Plus, Search, Send, ShoppingBag,
  ShoppingCart, ShieldCheck, Star, Trash2, Truck, UserRound, WalletCards, X
} from "lucide-react";
import {
  addShopCartItem, AppealAttachment, AuthUser, ConversationMessage, ConversationSummary,
  confirmAppeal, createOrderAppeal, createShopAddress, createShopOrder, deleteShopAddress, getOrderAppeal, getShopCart,
  listConversationMessages, listConversations, listOrderAppeals, listShopAddresses,
  listShopOrders, listShopProducts, payShopOrder, rateConversation, sendMessageStream,
  objectAppeal, OrderAppeal, shareProduct, ShopAddress, ShopCart, ShopOrder, ShopProduct, updateShopCartItem, uploadAppealAttachment
} from "../lib/api";
import "./storefront.css";

const money = (cents: number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(cents / 100);
const time = (value: string) => new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
const STATUS: Record<string, string> = { bot_active: "智能客服处理中", waiting_human: "等待人工客服", human_active: "人工客服处理中", resolved: "问题已解决" };

function ProductMessageCard({ product }: { product: Pick<ShopProduct, "product_id" | "name" | "category" | "description" | "price_cents" | "image_url"> }) {
  return <div className="shared-product-card"><img src={product.image_url} alt={product.name}/><span><small>{product.category} · {product.product_id}</small><strong>{product.name}</strong><p>{product.description}</p><em>{money(product.price_cents)}</em></span></div>;
}

function appealEventDetail(detail: Record<string, unknown>): string {
  if (typeof detail.reference === "string") {
    const round = typeof detail.approval_round === "number" ? `第 ${detail.approval_round} 轮 · ` : "";
    return `${round}沙箱业务单 ${detail.reference}`;
  }
  if (typeof detail.comment === "string") return detail.comment;
  if (typeof detail.note === "string") return detail.note;
  if (typeof detail.content === "string") return detail.content;
  if (typeof detail.file_name === "string") return `材料：${detail.file_name}`;
  return "";
}

type View = "shop" | "messages" | "orders" | "aftersales" | "account";
type AddressDraft = Omit<ShopAddress, "address_id">;
const blankAddress: AddressDraft = { recipient: "", phone: "", province: "", city: "", detail: "", is_default: true };

export default function CustomerStorefront({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [view, setView] = useState<View>("shop");
  const [products, setProducts] = useState<ShopProduct[]>([]);
  const [cart, setCart] = useState<ShopCart>({ items: [], total_cents: 0 });
  const [addresses, setAddresses] = useState<ShopAddress[]>([]);
  const [orders, setOrders] = useState<ShopOrder[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [appeals, setAppeals] = useState<OrderAppeal[]>([]);
  const [selectedAppeal, setSelectedAppeal] = useState<OrderAppeal | null>(null);
  const [appealFeedback, setAppealFeedback] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [selectedSession, setSelectedSession] = useState("shop-general");
  const [context, setContext] = useState<{ productId?: string; orderId?: string }>({});
  const [selectedProduct, setSelectedProduct] = useState<ShopProduct | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<ShopOrder | null>(null);
  const [showCart, setShowCart] = useState(false);
  const [showCheckout, setShowCheckout] = useState(false);
  const [selectedAddress, setSelectedAddress] = useState("");
  const [addressDraft, setAddressDraft] = useState<AddressDraft>(blankAddress);
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [agentStatus, setAgentStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failedMessage, setFailedMessage] = useState("");
  const [showAppeal, setShowAppeal] = useState(false);
  const [appealText, setAppealText] = useState("");
  const [appealFiles, setAppealFiles] = useState<File[]>([]);
  const [rating, setRating] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);

  async function refreshCore() {
    try {
      const [p, c, a, o, conv, ap] = await Promise.all([listShopProducts(), getShopCart(), listShopAddresses(), listShopOrders(), listConversations(), listOrderAppeals()]);
      setProducts(p); setCart(c); setAddresses(a); setOrders(o); setConversations(conv); setAppeals(ap); if(!selectedAppeal&&ap.length)setSelectedAppeal(ap[0]);
      if (!selectedAddress && a.length) setSelectedAddress((a.find(x => x.is_default) ?? a[0]).address_id);
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "数据加载失败"); }
  }
  async function refreshMessages(sessionId = selectedSession) {
    try { setMessages(await listConversationMessages(sessionId)); } catch { /* next poll retries */ }
  }
  useEffect(() => { void refreshCore(); }, []);
  useEffect(() => {
    if (view !== "messages") return;
    void refreshMessages();
    const timer = window.setInterval(() => { void refreshCore(); void refreshMessages(); }, 3000);
    return () => window.clearInterval(timer);
  }, [view, selectedSession]);
  useEffect(()=>{if(view!=="aftersales")return;const timer=window.setInterval(()=>{void refreshCore();if(selectedAppeal)void getOrderAppeal(selectedAppeal.appeal_id).then(setSelectedAppeal)},3000);return()=>window.clearInterval(timer)},[view,selectedAppeal?.appeal_id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, agentStatus]);

  const filtered = useMemo(() => products.filter(p => `${p.name}${p.description}${p.category}`.toLowerCase().includes(query.toLowerCase())), [products, query]);
  const unread = conversations.reduce((sum, item) => sum + item.unread_count, 0);
  const selectedConversation = conversations.find(x => x.session_id === selectedSession);
  const grouped = useMemo(() => ({
    "售前咨询": conversations.filter(x => x.session_id === "shop-general" && !["waiting_human", "human_active"].includes(x.status)),
    "商品咨询": conversations.filter(x => x.session_id.startsWith("shop-product-") && !["waiting_human", "human_active"].includes(x.status)),
    "订单售后": conversations.filter(x => (x.order_id || /^shop-SC/.test(x.session_id)) && !["waiting_human", "human_active"].includes(x.status)),
    "人工服务": conversations.filter(x => ["waiting_human", "human_active"].includes(x.status))
  }), [conversations]);

  function openConversation(sessionId: string, nextContext: { productId?: string; orderId?: string } = {}) {
    setSelectedSession(sessionId); setContext(nextContext); setView("messages"); setSelectedProduct(null); setSelectedOrder(null); setError("");
  }
  async function openProductConversation(product: ShopProduct) {
    const sessionId = `shop-product-${product.product_id}`;
    openConversation(sessionId, { productId: product.product_id });
    try {
      await shareProduct(sessionId, product.product_id);
      await Promise.all([refreshMessages(sessionId), refreshCore()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "商品发送失败");
    }
  }
  async function submitMessage(event?: FormEvent, retryText?: string) {
    event?.preventDefault(); const text = (retryText ?? input).trim(); if (!text || busy) return;
    setInput(""); setBusy(true); setFailedMessage(""); setAgentStatus("正在分析您的问题…");
    setMessages(current => [...current, { id: Date.now(), role: "user", sender_type: "customer", sender_id: user.user_id, sender_name: user.display_name, content: text, result: null, created_at: new Date().toISOString() }]);
    try {
      await sendMessageStream(text, () => undefined, selectedSession, setAgentStatus, context);
      await Promise.all([refreshMessages(), refreshCore()]); setAgentStatus("");
    } catch (reason) { setFailedMessage(text); setAgentStatus(""); setError(reason instanceof Error ? reason.message : "消息发送失败"); }
    finally { setBusy(false); }
  }
  async function addAddress(event: FormEvent) {
    event.preventDefault(); try { await createShopAddress(addressDraft); setAddressDraft(blankAddress); setShowAddressForm(false); await refreshCore(); } catch (reason) { setError(reason instanceof Error ? reason.message : "地址保存失败"); }
  }
  async function checkout() {
    if (!selectedAddress) { setView("account"); setShowCheckout(false); setShowAddressForm(true); setError("请先添加收货地址"); return; }
    setBusy(true); try { const created = await createShopOrder(selectedAddress); const paid = await payShopOrder(created.order_id); setShowCheckout(false); setShowCart(false); setSelectedOrder(paid); setView("orders"); await refreshCore(); } catch (reason) { setError(reason instanceof Error ? reason.message : "下单失败"); } finally { setBusy(false); }
  }
  async function submitAppeal(event: FormEvent) {
    event.preventDefault(); if (!selectedOrder) return; setBusy(true);
    try {
      const sessionId = `shop-${selectedOrder.order_id}`;
      const result = await createOrderAppeal(selectedOrder.order_id, sessionId, "rights_protection", appealText);
      const uploaded: AppealAttachment[] = [];
      for (const file of appealFiles) uploaded.push(await uploadAppealAttachment(result.appeal.appeal_id, file));
      setShowAppeal(false); setAppealText(""); setAppealFiles([]); setSelectedAppeal(await getOrderAppeal(result.appeal.appeal_id)); setView("aftersales"); await refreshCore();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "申诉提交失败"); } finally { setBusy(false); }
  }
  async function submitRating(score: number) { try { await rateConversation(selectedSession, score, score < 4 ? ["问题未解决"] : ["处理专业"], ""); setRating(score); } catch (reason) { setError(reason instanceof Error ? reason.message : "评价失败"); } }

  return <main className="store-shell">
    <header className="store-header"><button className="store-logo" onClick={() => setView("shop")}><span>NEBULA</span><small>星云商城</small></button><nav>
      <button className={view === "shop" ? "active" : ""} onClick={() => setView("shop")}><Home size={17}/>商城</button>
      <button className={view === "messages" ? "active" : ""} onClick={() => openConversation("shop-general")}><MessageCircle size={17}/>消息{unread > 0 && <b>{unread}</b>}</button>
      <button className={view === "orders" ? "active" : ""} onClick={() => setView("orders")}><PackageCheck size={17}/>订单</button>
      <button className={view === "aftersales" ? "active" : ""} onClick={() => setView("aftersales")}><ShieldCheck size={17}/>售后服务</button>
      <button className={view === "account" ? "active" : ""} onClick={() => setView("account")}><UserRound size={17}/>账户与地址</button>
    </nav><div className="store-actions"><button onClick={() => setShowCart(true)} title="购物车"><ShoppingCart size={19}/>{cart.items.length > 0 && <b>{cart.items.reduce((s,x)=>s+x.quantity,0)}</b>}</button><span>{user.display_name}</span><button onClick={onLogout} title="退出"><LogOut size={18}/></button></div></header>
    {error && <div className="store-error">{error}<button onClick={() => setError("")}><X size={15}/></button></div>}

    {view === "shop" && <><section className="store-toolbar"><div><h1>精选科技生活</h1><p>全部商品均可在购买前咨询规格、兼容性与使用限制</p></div><label><Search size={17}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索商品"/></label><button onClick={() => openConversation("shop-general")}><Headphones size={17}/>咨询客服</button></section><section className="product-grid">{filtered.map(product => <article className="product-card" key={product.product_id}><button className="product-image" onClick={()=>setSelectedProduct(product)}><img src={product.image_url} alt={product.name}/></button><small>{product.category} · {product.product_id}</small><h2>{product.name}</h2><p>{product.description}</p><div className="product-meta"><strong>{money(product.price_cents)}</strong><span>库存 {product.stock}</span></div><div className="product-buttons"><button onClick={()=>void openProductConversation(product)}><MessageCircle size={16}/>发给客服</button><button onClick={async()=>{setCart(await addShopCartItem(product.product_id));setShowCart(true)}}><ShoppingCart size={16}/>加入购物车</button></div></article>)}</section></>}

    {view === "messages" && <section className="message-center"><aside><header><h1>消息中心</h1><button onClick={()=>openConversation("shop-general")}><Plus size={16}/>新咨询</button></header>{Object.entries(grouped).map(([name, items]) => items.length > 0 && <div className="message-group" key={name}><h3>{name}</h3>{items.map(item=><button key={item.session_id} className={selectedSession===item.session_id?"active":""} onClick={()=>openConversation(item.session_id,{productId:item.product_id??undefined,orderId:item.order_id??undefined})}><span><strong>{item.product_id ?? item.order_id ?? "通用咨询"}</strong><small>{item.last_user_message || item.last_assistant_message}</small></span><i>{item.unread_count>0&&item.unread_count}</i><em>{STATUS[item.status]}</em></button>)}</div>)}</aside><div className="customer-chat"><header><div><Bot size={20}/><span><strong>{context.productId ? `商品 ${context.productId}` : context.orderId ? `订单 ${context.orderId}` : "智能客服"}</strong><small>{STATUS[selectedConversation?.status ?? "bot_active"]}{selectedConversation?.assigned_to ? ` · 客服 ${selectedConversation.assigned_to}` : ""}</small></span></div><div className="sla-note"><Clock3 size={15}/>{selectedConversation?.priority === "high" ? "高优先级预计 5 分钟内人工响应" : "普通问题预计 15 分钟内人工响应"}</div></header><div className="customer-chat-scroll">{messages.length===0&&<div className="chat-empty"><Headphones size={28}/><strong>有什么可以帮您？</strong><span>购买前也可以咨询商品功能、兼容性、保修和商城政策。</span></div>}{messages.map(message=><div className={`customer-message ${message.sender_type==="customer"?"mine":"theirs"}`} key={message.id}><small>{message.sender_name}</small>{message.attachment?.type==="product"?<ProductMessageCard product={message.attachment.product}/>:<p>{message.content}</p>}{message.result?.citations?.length ? <div className="message-citations">引用：{message.result.citations.map(c=>c.title).join("、")}</div>:null}</div>)}{agentStatus&&<div className="agent-working"><Bot size={16}/>{agentStatus}</div>}{failedMessage&&<div className="message-failed">消息发送失败 <button onClick={()=>void submitMessage(undefined,failedMessage)}>重试</button></div>}<div ref={endRef}/></div>{selectedConversation?.status==="resolved"&&<div className="rating-bar"><span>{rating?"感谢您的评价":"请评价本次服务"}</span>{[1,2,3,4,5].map(n=><button key={n} onClick={()=>void submitRating(n)} className={rating>=n?"active":""}><Star size={18}/></button>)}</div>}<form className="customer-composer" onSubmit={submitMessage}><textarea value={input} onChange={e=>setInput(e.target.value)} placeholder={selectedConversation?.status==="human_active"?"消息将发送给人工客服":"输入您的问题"}/><button disabled={busy||!input.trim()}><Send size={18}/></button></form></div></section>}

    {view === "orders" && <section className="orders-page"><header><h1>我的订单</h1><p>查看沙箱支付、履约和售后进度</p></header>{orders.length===0?<div className="empty-state"><ShoppingBag size={32}/><strong>还没有订单</strong><span>您仍然可以直接咨询客服</span><button onClick={()=>openConversation("shop-general")}>开始咨询</button></div>:orders.map(order=><article className="order-row" key={order.order_id}><div><small>{time(order.created_at)}</small><strong>{order.order_id}</strong><span>{order.items.map(x=>x.name).join("、")}</span></div><div><small>沙箱支付</small><strong>{money(order.total_cents)}</strong><span>{order.shipment?.latest_event??"等待履约"}</span></div><div className="order-actions"><button onClick={()=>{setSelectedOrder(order);openConversation(`shop-${order.order_id}`,{orderId:order.order_id})}}><MessageCircle size={16}/>咨询订单</button><button onClick={()=>{setSelectedOrder(order);setShowAppeal(true)}}>售后申诉</button></div></article>)}</section>}

    {view === "aftersales" && <section className="customer-aftersales"><header><div><h1>售后服务</h1><p>查看申诉进度、补充证据并确认处理结果</p></div></header><div className="customer-appeal-layout"><aside>{appeals.map(item=><button className={selectedAppeal?.appeal_id===item.appeal_id?"active":""} key={item.appeal_id} onClick={()=>void getOrderAppeal(item.appeal_id).then(setSelectedAppeal)}><ShieldCheck size={17}/><span><strong>{item.appeal_id}</strong><small>{item.order_id}</small><em>{({submitted:"待受理",investigating:"调查中",waiting_customer:"等待补材料",pending_approval:"审批中",returned:"补充调查",executing:"执行中",waiting_confirmation:"待您确认",resolved:"已结案",execution_failed:"执行异常"} as Record<string,string>)[item.status]??item.status}</em></span></button>)}{!appeals.length&&<div className="empty-state"><ShieldCheck/><strong>暂无售后申诉</strong><span>您可以从订单页面发起售后申诉</span></div>}</aside>{selectedAppeal?<article className="customer-appeal-detail"><header><div><h2>{selectedAppeal.appeal_id}</h2><p>订单 {selectedAppeal.order_id} · {selectedAppeal.assigned_name?`客服 ${selectedAppeal.assigned_name}`:selectedAppeal.status==="resolved"?"历史案件":"等待分配客服"}</p></div><strong>{({submitted:"待受理",investigating:"调查中",waiting_customer:"等待补材料",pending_approval:"审批中",returned:"补充调查",executing:"执行中",waiting_confirmation:"待您确认",resolved:"已结案",execution_failed:"执行异常"} as Record<string,string>)[selectedAppeal.status]}</strong></header><section><h3>您的诉求</h3><p>{selectedAppeal.description}</p></section>{selectedAppeal.material_requests.length>0&&<section><h3>待补材料</h3>{selectedAppeal.material_requests.map(request=><div className="customer-material" key={request.request_id}><span><strong>{request.content}</strong><small>{request.status==="pending"?"等待上传":"已提交材料"}</small></span>{request.status==="pending"&&<label><FileUp size={15}/>上传材料<input type="file" accept="image/jpeg,image/png,application/pdf" onChange={async e=>{const file=e.target.files?.[0];if(file){setBusy(true);try{await uploadAppealAttachment(selectedAppeal.appeal_id,file,request.request_id);setSelectedAppeal(await getOrderAppeal(selectedAppeal.appeal_id));await refreshCore()}catch(reason){setError(reason instanceof Error?reason.message:"上传失败")}finally{setBusy(false)}}}}/></label>}</div>)}</section>}{selectedAppeal.execution&&<section className="customer-execution"><h3>处理结果</h3><strong>{selectedAppeal.execution.sandbox_reference}</strong><p>{selectedAppeal.execution.result.message}</p>{selectedAppeal.execution.amount_cents&&<span>处理金额 {money(selectedAppeal.execution.amount_cents)}</span>}</section>}<section><h3>处理时间线</h3><div className="customer-appeal-timeline">{selectedAppeal.events.map(event=><div key={event.id}><i/><span><strong>{event.title}</strong><small>{event.actor_name} · {time(event.created_at)}</small>{appealEventDetail(event.detail)&&<small>{appealEventDetail(event.detail)}</small>}</span></div>)}</div></section>{selectedAppeal.status==="waiting_confirmation"&&<footer><input value={appealFeedback} onChange={e=>setAppealFeedback(e.target.value)} placeholder="可填写确认意见或异议原因"/><button onClick={()=>void objectAppeal(selectedAppeal.appeal_id,appealFeedback||"处理结果未解决我的问题").then(result=>{setSelectedAppeal(result);setAppealFeedback("");void refreshCore()})}>仍有异议</button><button className="primary" onClick={()=>void confirmAppeal(selectedAppeal.appeal_id,appealFeedback).then(result=>{setSelectedAppeal(result);setAppealFeedback("");void refreshCore()})}>确认处理结果</button></footer>}</article>:<div className="empty-state"><ShieldCheck/><strong>选择一个申诉查看进度</strong></div>}</div></section>}

    {view === "account" && <section className="account-page"><header><div><h1>账户与地址</h1><p>@{user.username} · {user.display_name}</p></div><button onClick={()=>setShowAddressForm(true)}><Plus size={16}/>新增地址</button></header><div className="address-list">{addresses.map(address=><article key={address.address_id}><div><strong>{address.recipient} · {address.phone}</strong>{address.is_default&&<em>默认</em>}</div><p>{address.province}{address.city}{address.detail}</p><button title="删除" onClick={async()=>{await deleteShopAddress(address.address_id);await refreshCore()}}><Trash2 size={16}/></button></article>)}{!addresses.length&&<div className="empty-state"><Home size={28}/><strong>暂无收货地址</strong></div>}</div></section>}

    {selectedProduct&&<div className="store-modal-backdrop"><section className="product-detail-modal"><button className="modal-close" onClick={()=>setSelectedProduct(null)}><X/></button><img src={selectedProduct.image_url} alt={selectedProduct.name}/><div><small>{selectedProduct.product_id} · {selectedProduct.category}</small><h1>{selectedProduct.name}</h1><p>{selectedProduct.description}</p><dl>{Object.entries(selectedProduct.specs).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl><strong>{money(selectedProduct.price_cents)}</strong><div className="product-buttons"><button onClick={()=>void openProductConversation(selectedProduct)}><MessageCircle size={17}/>发送给客服</button><button onClick={async()=>{setCart(await addShopCartItem(selectedProduct.product_id));setSelectedProduct(null);setShowCart(true)}}>加入购物车</button></div></div></section></div>}
    {showCart&&<div className="store-drawer"><header><h2>购物车</h2><button onClick={()=>setShowCart(false)}><X/></button></header><div>{cart.items.map(item=><article key={item.cart_item_id}><img src={item.image_url}/><span><strong>{item.name}</strong><small>{money(item.price_cents)}</small></span><div><button onClick={()=>void updateShopCartItem(item.cart_item_id,item.quantity-1).then(setCart)}><Minus size={14}/></button>{item.quantity}<button onClick={()=>void updateShopCartItem(item.cart_item_id,item.quantity+1).then(setCart)}><Plus size={14}/></button></div></article>)}</div><footer><span>合计 <strong>{money(cart.total_cents)}</strong></span><button disabled={!cart.items.length} onClick={()=>{setShowCart(false);setShowCheckout(true)}}>去结算</button></footer></div>}
    {showCheckout&&<div className="store-modal-backdrop"><section className="checkout-modal"><header><h2>确认收货与沙箱支付</h2><button onClick={()=>setShowCheckout(false)}><X/></button></header><div className="checkout-address">{addresses.map(a=><label key={a.address_id}><input type="radio" name="address" checked={selectedAddress===a.address_id} onChange={()=>setSelectedAddress(a.address_id)}/><span><strong>{a.recipient} {a.phone}</strong><small>{a.province}{a.city}{a.detail}</small></span></label>)}</div><div className="mock-payment"><WalletCards/><span><strong>沙箱支付通道</strong><small>仅用于项目验收，不会产生真实资金交易</small></span><CheckCircle2/></div><footer><strong>{money(cart.total_cents)}</strong><button disabled={busy} onClick={()=>void checkout()}>确认沙箱支付</button></footer></section></div>}
    {showAddressForm&&<div className="store-modal-backdrop"><form className="address-modal" onSubmit={addAddress}><header><h2>新增收货地址</h2><button type="button" onClick={()=>setShowAddressForm(false)}><X/></button></header>{([['recipient','收货人'],['phone','手机号'],['province','省份'],['city','城市'],['detail','详细地址']] as const).map(([key,label])=><label key={key}><span>{label}</span><input value={addressDraft[key] as string} onChange={e=>setAddressDraft({...addressDraft,[key]:e.target.value})} required/></label>)}<label className="check-row"><input type="checkbox" checked={addressDraft.is_default} onChange={e=>setAddressDraft({...addressDraft,is_default:e.target.checked})}/>设为默认地址</label><button className="primary" type="submit">保存地址</button></form></div>}
    {showAppeal&&selectedOrder&&<div className="store-modal-backdrop"><form className="appeal-form" onSubmit={submitAppeal}><header><h2>提交售后申诉</h2><button type="button" onClick={()=>setShowAppeal(false)}><X/></button></header><p>订单 {selectedOrder.order_id}</p><textarea minLength={10} required value={appealText} onChange={e=>setAppealText(e.target.value)} placeholder="请说明问题、已尝试的处理方式和期望方案"/><label className="file-picker"><FileUp size={18}/>上传 JPG、PNG 或 PDF（单文件不超过 10 MB）<input type="file" multiple accept="image/jpeg,image/png,application/pdf" onChange={e=>setAppealFiles(Array.from(e.target.files??[]))}/></label>{appealFiles.map(f=><small key={f.name}>{f.name}</small>)}<button className="primary" disabled={busy}>提交申诉与证据</button></form></div>}
  </main>;
}
