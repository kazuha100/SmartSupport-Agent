import { FormEvent, useEffect, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ClipboardCheck, Clock3, FileText, History,
  MessageSquareText, PackageCheck, RefreshCw, Scale, Send, ShieldCheck, UserRoundCheck, X
} from "lucide-react";
import {
  acceptAppeal, AuthUser, decideAppealApproval, getOrderAppeal, listOrderAppeals,
  OrderAppeal, requestAppealMaterial, retryAppealExecution, reviewAppealAttachment,
  saveAppealInvestigation, saveAppealProposal, submitAppealApproval
} from "../lib/api";
import "./appeals.css";

const STATUS: Record<string,string> = { submitted:"待受理", investigating:"调查中", waiting_customer:"等待用户补材料", pending_approval:"待确认执行", returned:"退回修改", executing:"执行中", waiting_confirmation:"等待用户确认", resolved:"已结案", execution_failed:"执行失败" };
const TYPES: Record<string,string> = { refund:"退款申请", return:"退货申请", repair:"维修争议", rights_protection:"投诉维权" };
const RESPONSIBILITY: Record<string,string> = { merchant:"商家责任", customer:"用户责任", logistics:"物流责任", platform:"平台责任", undetermined:"待确认" };
const ACTIONS: Record<string,string> = { refund:"退款", return_refund:"退货退款", replace:"换货", repair:"维修", compensation:"补偿", reject:"驳回申诉" };
const REVIEW: Record<string,string> = { pending:"待审核", accepted:"有效", rejected:"无效" };
type Tab = "overview"|"evidence"|"investigation"|"timeline";
type FormFeedback = { type:"success"|"error"; text:string } | null;

function eventDetail(detail: Record<string, unknown>): string {
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

export default function AppealDesk({user,onOpenConversation}:{user:AuthUser;onOpenConversation:(sessionId:string)=>void}) {
  const [appeals,setAppeals]=useState<OrderAppeal[]>([]);
  const [selected,setSelected]=useState<OrderAppeal|null>(null);
  const [tab,setTab]=useState<Tab>("overview");
  const [responsibility,setResponsibility]=useState("undetermined");
  const [conclusion,setConclusion]=useState("");
  const [action,setAction]=useState("repair");
  const [amount,setAmount]=useState("");
  const [reason,setReason]=useState("");
  const [material,setMaterial]=useState("");
  const [approvalComment,setApprovalComment]=useState("");
  const [investigationFeedback,setInvestigationFeedback]=useState<FormFeedback>(null);
  const [proposalFeedback,setProposalFeedback]=useState<FormFeedback>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");

  async function refresh(keepId=selected?.appeal_id){
    try{
      const items=await listOrderAppeals();
      setAppeals(items);
      if(keepId){
        const detail=await getOrderAppeal(keepId);
        if(selected?.appeal_id===keepId)setSelected(detail);
        else select(detail);
      }else if(!selected&&items[0]){
        select(await getOrderAppeal(items[0].appeal_id));
      }
      setError("");
    }catch(e){
      setError(e instanceof Error?e.message:"申诉加载失败");
    }
  }
  function select(item:OrderAppeal){setSelected(item);setResponsibility(item.responsibility??"undetermined");setConclusion(item.investigation_conclusion??"");setAction(item.proposed_action??"repair");setAmount(item.proposed_amount_cents?String(item.proposed_amount_cents/100):"");setReason(item.proposal_reason??"");}
  async function run(operation:()=>Promise<OrderAppeal>):Promise<boolean>{setBusy(true);setError("");try{const result=await operation();select(result);await refresh(result.appeal_id);return true;}catch(e){setError(e instanceof Error?e.message:"操作失败");return false;}finally{setBusy(false)}}
  useEffect(()=>{void refresh()},[]);
  useEffect(()=>{const timer=window.setInterval(()=>void refresh(selected?.appeal_id),3000);return()=>clearInterval(timer)},[selected?.appeal_id]);
  const mine=selected?.assigned_to===user.user_id;

  async function saveInvestigation(e:FormEvent){
    e.preventDefault();
    if(conclusion.trim().length<10){
      setInvestigationFeedback({type:"error",text:`调查结论至少填写 10 个字，当前 ${conclusion.trim().length} 个字。`});
      return;
    }
    if(selected&&await run(()=>saveAppealInvestigation(selected.appeal_id,responsibility,conclusion.trim()))){
      setInvestigationFeedback({type:"success",text:"调查结论已保存。"});
    }
  }
  async function saveProposal(e:FormEvent){
    e.preventDefault();
    if(reason.trim().length<10){
      setProposalFeedback({type:"error",text:`方案理由至少填写 10 个字，当前 ${reason.trim().length} 个字。`});
      return;
    }
    const needsAmount=["refund","return_refund","compensation"].includes(action);
    const amountCents=Math.round(Number(amount)*100);
    if(needsAmount&&(!Number.isFinite(amountCents)||amountCents<=0)){
      setProposalFeedback({type:"error",text:"退款或补偿方案必须填写大于 0 元的金额。"});
      return;
    }
    if(selected&&await run(()=>saveAppealProposal(selected.appeal_id,action,needsAmount?amountCents:null,reason.trim()))){
      setProposalFeedback({type:"success",text:"处理方案已保存。"});
    }
  }
  async function requestMaterial(e:FormEvent){e.preventDefault();if(selected&&material.trim()){await run(()=>requestAppealMaterial(selected.appeal_id,material.trim()));setMaterial("")}}
  async function approveCurrentAppeal(){
    if(!selected)return;
    const comment=approvalComment.trim()||"全权限管理员已核验方案并确认执行。";
    await run(async()=>{
      if(["investigating","returned"].includes(selected.status)) await submitAppealApproval(selected.appeal_id);
      return decideAppealApproval(selected.appeal_id,"approve",comment);
    });
    setApprovalComment("");
  }

  return <main className="appeal-workspace">
    <header className="appeal-header"><div><h1>申诉中心</h1><span>调查、审批与执行闭环</span></div><button onClick={()=>void refresh()} title="刷新"><RefreshCw size={15}/></button></header>
    {error&&<div className="error-banner">{error}<button onClick={()=>setError("")}><X size={14}/></button></div>}
    <section className="appeal-layout">
      <aside className="appeal-queue"><div className="appeal-metrics"><span><b>{appeals.length}</b>全部</span><span><b>{appeals.filter(x=>x.status==="submitted").length}</b>待受理</span><span><b>{appeals.filter(x=>x.status==="pending_approval").length}</b>待审批</span></div>{appeals.map(item=><button key={item.appeal_id} className={selected?.appeal_id===item.appeal_id?"active":""} onClick={()=>void getOrderAppeal(item.appeal_id).then(select)}><i className={item.priority}><ShieldCheck size={16}/></i><span><strong>{TYPES[item.appeal_type]??item.appeal_type}</strong><small>{item.description}</small><em>{item.appeal_id} · {STATUS[item.status]??item.status}</em></span></button>)}{!appeals.length&&<div className="appeal-empty"><Scale/><span>暂无用户申诉</span></div>}</aside>
      {selected?<section className="appeal-case">
        <header><div><h2>{TYPES[selected.appeal_type]??selected.appeal_type}</h2><p>{selected.appeal_id} · 订单 {selected.order_id}</p></div><span className={`case-status ${selected.status}`}>{STATUS[selected.status]??selected.status}</span></header>
        <nav>{([["overview","案件概览",ClipboardCheck],["evidence","证据材料",FileText],["investigation","调查处理",Scale],["timeline","处理时间线",History]] as const).map(([id,label,Icon])=><button className={tab===id?"active":""} onClick={()=>setTab(id)} key={id}><Icon size={14}/>{label}</button>)}</nav>
        <div className="appeal-case-scroll">
          {tab==="overview"&&<div className="case-overview"><section><h3>用户诉求</h3><p>{selected.description}</p></section><dl><div><dt>当前负责人</dt><dd>{selected.assigned_name??"未分配"}</dd></div><div><dt>优先级</dt><dd>{selected.priority==="high"?"高":"普通"}</dd></div><div><dt>订单金额</dt><dd>¥{(selected.order_total_cents/100).toFixed(2)}</dd></div><div><dt>关联工单</dt><dd>{selected.ticket_id??"未创建"}</dd></div><div><dt>提交时间</dt><dd>{new Date(selected.created_at).toLocaleString("zh-CN")}</dd></div><div><dt>处理状态</dt><dd>{STATUS[selected.status]}</dd></div></dl><button className="conversation-link" onClick={()=>onOpenConversation(selected.session_id)}><MessageSquareText size={15}/>进入关联会话</button>{selected.execution&&<section className="sandbox-result"><PackageCheck size={18}/><div><strong>沙箱业务单 {selected.execution.sandbox_reference}</strong><p>{selected.execution.result.message}</p></div></section>}</div>}
          {tab==="evidence"&&<div className="case-evidence"><section><h3>用户证据</h3>{selected.attachments.map(file=><article key={file.attachment_id}><a href={`/api/attachments/${file.attachment_id}`} target="_blank" rel="noreferrer"><FileText size={16}/><span><strong>{file.file_name}</strong><small>{(file.size_bytes/1024).toFixed(1)} KB</small></span></a><em className={file.review_status}>{REVIEW[file.review_status]??file.review_status}</em>{mine&&file.review_status==="pending"&&<div><button onClick={()=>void run(()=>reviewAppealAttachment(selected.appeal_id,file.attachment_id,"accepted","材料清晰有效"))}>标记有效</button><button onClick={()=>void run(()=>reviewAppealAttachment(selected.appeal_id,file.attachment_id,"rejected","材料无法支持诉求"))}>标记无效</button></div>}</article>)}{!selected.attachments.length&&<p className="muted">用户尚未上传证据</p>}</section><section><h3>补材料记录</h3>{selected.material_requests.map(item=><div className="material-row" key={item.request_id}><strong>{item.content}</strong><span>{item.status==="pending"?"等待上传":item.status==="submitted"?"用户已补充":"已完成"}</span></div>)}{mine&&["investigating","returned"].includes(selected.status)&&<form className="material-form" onSubmit={requestMaterial}><textarea value={material} onChange={e=>setMaterial(e.target.value)} placeholder="说明需要用户补充的材料" required/><button disabled={busy||!material.trim()}><Send size={14}/>发送要求</button></form>}</section></div>}
          {tab==="investigation"&&<div className="case-investigation"><section><h3>智能核验建议</h3>{selected.agent_result?.agent_results?.map((item,index)=><div className="review-line" key={index}><CheckCircle2 size={14}/><span>{item.summary}</span></div>)}</section><form onSubmit={saveInvestigation}><h3>调查结论</h3><label>责任认定<select value={responsibility} onChange={e=>setResponsibility(e.target.value)} disabled={!mine}>{Object.entries(RESPONSIBILITY).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label><label>调查结论<textarea value={conclusion} onChange={e=>{setConclusion(e.target.value);setInvestigationFeedback(null)}} disabled={!mine} placeholder="结合订单、政策和用户证据填写调查结论"/></label>{mine&&["investigating","returned"].includes(selected.status)&&<button disabled={busy}>保存调查结论</button>}{investigationFeedback&&<p className={`form-feedback ${investigationFeedback.type}`}>{investigationFeedback.text}</p>}</form><form onSubmit={saveProposal}><h3>处理方案</h3><div className="proposal-grid"><label>方案<select value={action} onChange={e=>setAction(e.target.value)} disabled={!mine}>{Object.entries(ACTIONS).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label>{["refund","return_refund","compensation"].includes(action)&&<label>金额（元）<input type="number" min="0.01" step="0.01" max={selected.order_total_cents/100} value={amount} onChange={e=>setAmount(e.target.value)} disabled={!mine}/></label>}</div><label>方案理由<textarea value={reason} onChange={e=>{setReason(e.target.value);setProposalFeedback(null)}} disabled={!mine} placeholder="说明方案依据、执行条件和用户影响"/></label>{mine&&["investigating","returned"].includes(selected.status)&&<button disabled={busy}>保存处理方案</button>}{proposalFeedback&&<p className={`form-feedback ${proposalFeedback.type}`}>{proposalFeedback.text}</p>}{selected.risk_reasons.length>0&&<div className="risk-box"><AlertTriangle size={16}/><span><strong>{selected.risk_level==="high"?"高风险":"需复核"}</strong>{selected.risk_reasons.join("；")}</span></div>}</form></div>}
          {tab==="timeline"&&<div className="case-timeline">{selected.events.map(event=><article key={event.id}><i/><div><strong>{event.title}</strong><p>{event.actor_name} · {new Date(event.created_at).toLocaleString("zh-CN")}</p>{eventDetail(event.detail)&&<small>{eventDetail(event.detail)}</small>}{event.from_status!==event.to_status&&<small>{event.from_status?STATUS[event.from_status]:"创建"} → {event.to_status?STATUS[event.to_status]:"--"}</small>}</div></article>)}</div>}
        </div>
        <footer className="appeal-primary-actions">
          {selected.status==="submitted"&&<button className="primary" disabled={busy} onClick={()=>void run(()=>acceptAppeal(selected.appeal_id))}><UserRoundCheck size={15}/>受理申诉</button>}
          {mine&&["investigating","returned"].includes(selected.status)&&selected.proposed_action&&<button className="primary" disabled={busy} onClick={()=>void approveCurrentAppeal()}><ShieldCheck size={15}/>提交方案</button>}
          {selected.status==="pending_approval"&&user.role==="admin"&&<><input value={approvalComment} onChange={e=>setApprovalComment(e.target.value)} placeholder="处理说明（可选）"/><button disabled={busy||approvalComment.trim().length>0&&approvalComment.trim().length<2} onClick={()=>void run(()=>decideAppealApproval(selected.appeal_id,"return",approvalComment.trim()||"请补充调查材料。"))}>退回修改</button><button className="primary" disabled={busy||approvalComment.trim().length>0&&approvalComment.trim().length<2} onClick={()=>void run(()=>decideAppealApproval(selected.appeal_id,"approve",approvalComment.trim()||"全权限管理员已提交处理方案。"))}>提交方案</button></>}
          {selected.status==="execution_failed"&&user.role==="admin"&&<button className="primary" disabled={busy} onClick={()=>void run(()=>retryAppealExecution(selected.appeal_id))}>重新执行沙箱业务单</button>}
          {selected.status==="waiting_confirmation"&&<span><Clock3 size={14}/>沙箱处理已完成，等待用户确认</span>}
          {selected.status==="resolved"&&<span><CheckCircle2 size={14}/>申诉已完成闭环</span>}
        </footer>
      </section>:<div className="appeal-empty"><Scale/><span>选择一个申诉开始处理</span></div>}
    </section>
  </main>;
}
