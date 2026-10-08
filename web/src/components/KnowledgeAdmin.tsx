import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookOpen,
  Eye,
  FileArchive,
  FileText,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X
} from "lucide-react";
import {
  deleteDocument,
  getDocument,
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  listDocuments,
  setDocumentStatus,
  uploadDocument
} from "../lib/api";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function KnowledgeAdmin() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selected, setSelected] = useState<KnowledgeDocumentDetail | null>(null);
  const [viewerMode, setViewerMode] = useState<"document" | "chunks" | null>(null);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeDocument | null>(null);
  const [query, setQuery] = useState("");
  const [productFilter, setProductFilter] = useState("all");
  const [showUpload, setShowUpload] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return documents.filter((item) =>
      (!term || `${item.title}${item.file_name}${item.doc_id}`.toLowerCase().includes(term)) &&
      (productFilter === "all" || item.product_id === productFilter)
    );
  }, [documents, query, productFilter]);

  const activeCount = documents.filter((item) => item.status === "active").length;
  const chunkCount = documents.reduce((total, item) => total + item.chunk_count, 0);

  async function refresh() {
    setError("");
    try {
      setDocuments(await listDocuments());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识库加载失败");
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("请选择文件");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = new FormData(formElement);
      data.set("file", file);
      await uploadDocument(data);
      formElement.reset();
      setShowUpload(false);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(document: KnowledgeDocument) {
    setBusy(true);
    setError("");
    try {
      await setDocumentStatus(document.doc_id, document.status === "active" ? "disabled" : "active");
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "状态更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function inspect(document: KnowledgeDocument, mode: "document" | "chunks") {
    setError("");
    try {
      setSelected(await getDocument(document.doc_id));
      setViewerMode(mode);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文档加载失败");
    }
  }

  async function remove(document: KnowledgeDocument) {
    setBusy(true);
    setError("");
    try {
      await deleteDocument(document.doc_id);
      setPendingDelete(null);
      if (selected?.doc_id === document.doc_id) {
        setSelected(null);
        setViewerMode(null);
      }
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="knowledge-workspace">
      <header className="knowledge-header">
        <div><h1>知识库</h1><span>文档与检索分段</span></div>
        <div>
          <button className="secondary-button" onClick={() => void refresh()} title="刷新"><RefreshCw size={16} /></button>
          <button className="primary-button" onClick={() => setShowUpload((value) => !value)}><Upload size={16} /> 上传文档</button>
        </div>
      </header>

      {showUpload && (
        <form className="upload-band" onSubmit={submitUpload}>
          <label className="file-picker"><FileArchive size={18} /><span>选择文件</span><input ref={fileRef} name="file" type="file" accept=".pdf,.docx,.md,.txt" required /></label>
          <label><span>标题</span><input name="title" placeholder="默认使用文件名" /></label>
          <label className="short-field"><span>版本</span><input name="version" defaultValue="1.0" required /></label>
          <label className="short-field"><span>可见范围</span><select name="visibility" defaultValue="public"><option value="public">公开</option><option value="internal">内部</option></select></label>
          <button className="primary-button" disabled={busy} type="submit">{busy ? "处理中" : "开始解析"}</button>
        </form>
      )}

      {error && <div className="error-banner">{error}<button onClick={() => setError("")} title="关闭"><X size={14} /></button></div>}

      <section className="knowledge-metrics">
        <div><small>文档总数</small><strong>{documents.length}</strong></div>
        <div><small>已启用</small><strong>{activeCount}</strong></div>
        <div><small>检索分段</small><strong>{chunkCount}</strong></div>
        <div><small>存储方式</small><strong>PostgreSQL + pgvector</strong></div>
      </section>

      <section className="document-area">
        <div className="document-toolbar">
          <div className="search-field"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文档" /></div>
          <select value={productFilter} onChange={(event) => setProductFilter(event.target.value)} aria-label="按关联商品筛选"><option value="all">全部商品</option>{Array.from(new Set(documents.map(item => item.product_id).filter(Boolean))).sort().map(productId => <option key={productId} value={productId!}>{productId}</option>)}</select>
          <span>{filtered.length} 项</span>
        </div>
        <div className="document-table" role="table" aria-label="知识文档">
          <div className="document-row table-head" role="row">
            <span>文档</span><span>版本</span><span>分段</span><span>状态</span><span>操作</span>
          </div>
          {filtered.map((document) => (
            <div className="document-row" role="row" key={document.doc_id}>
              <button className="document-name document-open" onClick={() => void inspect(document, "document")} title={`打开${document.title}`}>
                <span><FileText size={17} /></span><span><strong>{document.title}</strong><small>{document.file_name} · {formatBytes(document.size_bytes)}</small></span>
              </button>
              <span>v{document.version}</span>
              <span>{document.chunk_count}</span>
              <label className="status-switch" title={document.status === "active" ? "禁用文档" : "启用文档"}>
                <input type="checkbox" checked={document.status === "active"} disabled={busy} onChange={() => void toggleStatus(document)} />
                <i /><span>{document.status === "active" ? "启用" : "禁用"}</span>
              </label>
              <div className="row-actions">
                <button onClick={() => void inspect(document, "document")} title="打开文档"><BookOpen size={16} /></button>
                <button onClick={() => void inspect(document, "chunks")} title="查看分段"><Eye size={16} /></button>
                {document.doc_id.startsWith("upload_") && <button onClick={() => setPendingDelete(document)} disabled={busy} title="删除文档"><Trash2 size={16} /></button>}
              </div>
            </div>
          ))}
          {filtered.length === 0 && <div className="empty-table"><FileText size={24} /><span>暂无文档</span></div>}
        </div>
      </section>

      {selected && viewerMode === "document" && (
        <div className="document-reader-backdrop" role="presentation" onClick={() => { setSelected(null); setViewerMode(null); }}>
          <article className="document-reader" role="dialog" aria-modal="true" aria-labelledby="document-reader-title" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span><BookOpen size={19} /></span>
                <div><h2 id="document-reader-title">{selected.title}</h2><p>{selected.file_name} · {formatBytes(selected.size_bytes)}</p></div>
              </div>
              <button onClick={() => { setSelected(null); setViewerMode(null); }} title="关闭文档"><X size={19} /></button>
            </header>
            <div className="document-reader-meta">
              <span>版本 <strong>v{selected.version}</strong></span>
              <span>状态 <strong>{selected.status === "active" ? "已启用" : "已禁用"}</strong></span>
              <span>可见范围 <strong>{selected.visibility === "public" ? "公开" : "内部"}</strong></span>
              <span>更新时间 <strong>{new Date(selected.updated_at).toLocaleString("zh-CN")}</strong></span>
            </div>
            <div className="document-reader-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{selected.content}</ReactMarkdown>
            </div>
          </article>
        </div>
      )}

      {selected && viewerMode === "chunks" && (
        <aside className="chunk-drawer">
          <header><div><strong>{selected.title}</strong><span>{selected.chunk_count} 个分段 · v{selected.version}</span></div><button onClick={() => { setSelected(null); setViewerMode(null); }} title="关闭"><X size={18} /></button></header>
          <div className="chunk-list">
            {selected.chunks.map((chunk) => (
              <article key={chunk.position}><div><strong>{chunk.section}</strong><span>#{chunk.position + 1}</span></div><p>{chunk.content}</p></article>
            ))}
          </div>
        </aside>
      )}

      {pendingDelete && (
        <div className="modal-backdrop" role="presentation">
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title">
            <div><Trash2 size={18} /><strong id="delete-dialog-title">删除文档</strong></div>
            <p>确定删除“{pendingDelete.title}”及其全部检索分段？</p>
            <footer><button className="dialog-cancel" onClick={() => setPendingDelete(null)}>取消</button><button className="dialog-danger" disabled={busy} onClick={() => void remove(pendingDelete)}>删除</button></footer>
          </div>
        </div>
      )}
    </main>
  );
}
