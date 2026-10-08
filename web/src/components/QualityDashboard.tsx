import { useEffect, useState } from "react";
import {
  Bot,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  Download,
  MessageSquareText,
  RefreshCw,
  Route,
  SearchX,
  Timer,
  TrendingUp,
  Wrench,
  X
} from "lucide-react";
import { DashboardMetrics, getDashboardMetrics, QuestionFrequency } from "../lib/api";

function QuestionList({ items, emptyText, onSelect }: { items: QuestionFrequency[]; emptyText: string; onSelect?: (item: QuestionFrequency) => void }) {
  if (items.length === 0) return <div className="empty-question-list"><CheckCircle2 size={23} /><span>{emptyText}</span></div>;
  return (
    <div className="question-list">
      {items.map((item, index) => {
        const content = <>
          <span>{index + 1}</span>
          <div><strong>{item.question}</strong><small>最近提问 {new Date(item.last_asked_at).toLocaleString("zh-CN")}</small></div>
          <b>{item.count} 次</b>
        </>;
        return onSelect
          ? <button type="button" key={`${item.question}-${index}`} onClick={() => onSelect(item)} title="查看知识缺口详情">{content}</button>
          : <article key={`${item.question}-${index}`}>{content}</article>;
      })}
    </div>
  );
}

function csvCell(value: string | number | null | undefined): string {
  let text = String(value ?? "");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function exportKnowledgeGaps(items: QuestionFrequency[]) {
  const header = ["知识缺口簇", "代表问题", "原始问法", "簇累计次数", "相似度", "用户", "会话ID", "商品ID", "订单ID", "会话状态", "本次提问时间"];
  const rows = items.flatMap(item => {
    const occurrences = item.occurrences.length ? item.occurrences : [null];
    return occurrences.map(occurrence => [
      item.cluster_id, item.question, occurrence?.question ?? item.question, item.count,
      occurrence?.similarity, occurrence?.display_name, occurrence?.session_id,
      occurrence?.product_id ?? item.product_id, occurrence?.order_id,
      occurrence?.conversation_status, occurrence?.asked_at,
    ]);
  });
  const csv = `\uFEFF${[header, ...rows].map(row => row.map(csvCell).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `知识库未覆盖-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function QualityDashboard() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [selectedGap, setSelectedGap] = useState<QuestionFrequency | null>(null);
  const [error, setError] = useState("");

  async function refresh() {
    try { setData(await getDashboardMetrics()); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "指标加载失败"); }
  }

  useEffect(() => { void refresh(); }, []);

  const operations = data?.operations;
  const analytics = data?.question_analytics;

  return (
    <main className="quality-workspace">
      <header className="knowledge-header">
        <div><h1>质量看板</h1><span>真实提问与知识缺口</span></div>
        <button className="secondary-button" onClick={() => void refresh()} title="刷新"><RefreshCw size={16} /></button>
      </header>
      {error && <div className="error-banner">{error}<button onClick={() => setError("")} title="关闭"><X size={14} /></button></div>}

      <section className="quality-overview">
        <div><span><MessageSquareText size={17} /></span><small>会话</small><strong>{operations?.conversations ?? 0}</strong></div>
        <div><span><Bot size={17} /></span><small>平均置信度</small><strong>{Math.round((operations?.average_confidence ?? 0) * 100)}%</strong></div>
        <div><span><Route size={17} /></span><small>人工转接率</small><strong>{Math.round((operations?.human_handoff_rate ?? 0) * 100)}%</strong></div>
        <div><span><Wrench size={17} /></span><small>工具调用率</small><strong>{Math.round((operations?.tool_call_rate ?? 0) * 100)}%</strong></div>
        <div><span><Timer size={17} /></span><small>模型平均延迟</small><strong>{operations?.average_model_latency_ms ?? 0}<small> ms</small></strong></div>
        <div><span><Timer size={17} /></span><small>平均首响</small><strong>{operations?.average_first_response_seconds ?? 0}<small> 秒</small></strong></div>
        <div><span><Clock3 size={17} /></span><small>会话超时率</small><strong>{Math.round((operations?.overdue_rate ?? 0) * 100)}%</strong></div>
        <div><span><CheckCircle2 size={17} /></span><small>会话解决率</small><strong>{Math.round((operations?.resolution_rate ?? 0) * 100)}%</strong></div>
        <div><span><TrendingUp size={17} /></span><small>满意度</small><strong>{(operations?.average_satisfaction ?? 0).toFixed(1)}<small> / 5</small></strong></div>
      </section>

      <section className="question-overview">
        <div><small>用户提问总数</small><strong>{analytics?.total_questions ?? 0}</strong></div>
        <div><small>不同问题</small><strong>{analytics?.unique_questions ?? 0}</strong></div>
        <div><small>知识类问题</small><strong>{analytics?.knowledge_questions ?? 0}</strong></div>
        <div><small>知识覆盖率</small><strong>{Math.round((analytics?.coverage_rate ?? 1) * 100)}%</strong></div>
      </section>

      <div className="quality-grid question-grid">
        <section className="question-panel">
          <header><div><TrendingUp size={17} /><strong>高频用户提问</strong></div><span>按出现次数排序</span></header>
          <QuestionList items={analytics?.top_questions ?? []} emptyText="暂无用户提问" />
        </section>
        <section className="question-panel gap-panel">
          <header><div><SearchX size={17} /><strong>知识库未覆盖</strong></div><div className="gap-header-actions"><span>{analytics?.uncovered_count ?? 0} 次未覆盖</span><button type="button" disabled={!analytics?.uncovered_questions.length} onClick={() => exportKnowledgeGaps(analytics?.uncovered_questions ?? [])} title="导出未覆盖问题"><Download size={14}/>导出</button></div></header>
          <QuestionList items={analytics?.uncovered_questions ?? []} emptyText="当前没有知识缺口" onSelect={setSelectedGap} />
        </section>

        <section className="operations-panel quality-operations">
          <header><Database size={17} /><strong>运营概览</strong></header>
          <div className="operations-list"><div><span>知识文档</span><strong>{operations?.documents ?? 0}</strong></div><div><span>向量分段</span><strong>{operations?.chunks ?? 0}</strong></div><div><span>消息总数</span><strong>{operations?.messages ?? 0}</strong></div></div>
          <h2><CircleHelp size={13} /> 工单状态</h2>
          <div className="ticket-stats"><div><i className="open" /><span>待接单</span><strong>{operations?.tickets.open ?? 0}</strong></div><div><i className="assigned" /><span>处理中</span><strong>{operations?.tickets.assigned ?? 0}</strong></div><div><i className="resolved" /><span>已解决</span><strong>{operations?.tickets.resolved ?? 0}</strong></div></div>
        </section>
      </div>
      {selectedGap&&<div className="gap-detail-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setSelectedGap(null)}}><aside className="gap-detail" role="dialog" aria-modal="true" aria-label="知识缺口详情"><header><div><SearchX size={17}/><span><strong>知识缺口详情</strong><small>{selectedGap.count} 次提问 · {selectedGap.product_id??"通用问题"}</small></span></div><button type="button" onClick={()=>setSelectedGap(null)} title="关闭"><X size={16}/></button></header><section><small>代表问题</small><p>{selectedGap.question}</p>{selectedGap.variants&&selectedGap.variants.length>0&&<div className="gap-variants">{selectedGap.variants.map(item=><span key={item.question}>{item.question} · {item.count} 次</span>)}</div>}</section><section><div className="gap-detail-heading"><strong>原始提问来源</strong><small>最近提问 {new Date(selectedGap.last_asked_at).toLocaleString("zh-CN")}</small></div><div className="gap-occurrences">{selectedGap.occurrences.map(item=><article key={item.message_id}><div><strong>{item.display_name}</strong><time>{new Date(item.asked_at).toLocaleString("zh-CN")}</time></div>{item.question&&<p>{item.question}</p>}<dl><div><dt>会话</dt><dd>{item.session_id}</dd></div><div><dt>关联业务</dt><dd>{item.product_id??item.order_id??"通用咨询"}</dd></div><div><dt>相似度</dt><dd>{item.similarity==null?"-":`${Math.round(item.similarity*100)}%`}</dd></div><div><dt>状态</dt><dd>{item.conversation_status}</dd></div></dl></article>)}</div></section><footer><button type="button" onClick={()=>exportKnowledgeGaps([selectedGap])}><Download size={14}/>导出此问题</button></footer></aside></div>}
    </main>
  );
}
