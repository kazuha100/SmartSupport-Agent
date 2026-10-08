import hashlib
import io
import re
import uuid
from pathlib import Path

import frontmatter
from docx import Document
from pypdf import PdfReader

from app.repository import Repository


ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


class DocumentError(ValueError):
    pass


class DocumentService:
    def __init__(self, repository: Repository, upload_dir: Path, max_upload_mb: int = 10):
        self.repository = repository
        self.upload_dir = upload_dir
        self.max_upload_bytes = max_upload_mb * 1024 * 1024
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def sync_markdown_directory(self, root: Path) -> int:
        synced = 0
        if not root.exists():
            return synced
        for path in sorted(root.rglob("*.md")):
            post = frontmatter.load(path)
            metadata = post.metadata
            content = post.content.strip()
            title = str(metadata.get("title", path.stem))
            _, created = self.repository.upsert_document(
                self._document_payload(
                    doc_id=str(metadata.get("doc_id", path.stem)),
                    title=title,
                    file_name=path.name,
                    source_type="markdown",
                    source_path=str(path),
                    version=str(metadata.get("version", "1.0")),
                    status=str(metadata.get("status", "active")),
                    visibility=str(metadata.get("visibility", "public")),
                    product_id=str(metadata.get("product_id")) if metadata.get("product_id") else None,
                    document_category=str(metadata.get("document_category", "product" if metadata.get("product_id") else "general")),
                    content=content,
                    size_bytes=path.stat().st_size,
                ),
                self._chunk(content, title),
            )
            synced += int(created)
        return synced

    def upload(
        self,
        file_name: str,
        data: bytes,
        title: str | None,
        version: str,
        visibility: str,
    ) -> dict:
        safe_name = Path(file_name).name
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise DocumentError("仅支持 PDF、Word、Markdown 和 TXT 文件。")
        if not data:
            raise DocumentError("上传文件不能为空。")
        if len(data) > self.max_upload_bytes:
            raise DocumentError(f"文件不能超过 {self.max_upload_bytes // 1024 // 1024} MB。")

        content = self._extract(extension, data).strip()
        if not content:
            raise DocumentError("文件中没有可提取的文本。")
        doc_id = f"upload_{uuid.uuid4().hex[:12]}"
        stored_path = self.upload_dir / f"{doc_id}{extension}"
        stored_path.write_bytes(data)
        document_title = (title or Path(safe_name).stem).strip()
        result, _ = self.repository.upsert_document(
            self._document_payload(
                doc_id=doc_id,
                title=document_title,
                file_name=safe_name,
                source_type=extension.removeprefix("."),
                source_path=str(stored_path),
                version=version,
                status="active",
                visibility=visibility,
                product_id=None,
                document_category="general",
                content=content,
                size_bytes=len(data),
            ),
            self._chunk(content, document_title),
        )
        return result

    def delete_source(self, document: dict) -> None:
        if not document["doc_id"].startswith("upload_"):
            return
        for path in self.upload_dir.glob(f"{document['doc_id']}.*"):
            path.unlink(missing_ok=True)

    @staticmethod
    def _extract(extension: str, data: bytes) -> str:
        if extension in {".md", ".txt"}:
            try:
                return data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise DocumentError("文本文件必须使用 UTF-8 编码。") from exc
        if extension == ".pdf":
            try:
                return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
            except Exception as exc:
                raise DocumentError("PDF 解析失败或文件已损坏。") from exc
        if extension == ".docx":
            try:
                document = Document(io.BytesIO(data))
                return "\n".join(paragraph.text for paragraph in document.paragraphs)
            except Exception as exc:
                raise DocumentError("Word 文档解析失败或文件已损坏。") from exc
        raise DocumentError("不支持的文件类型。")

    @staticmethod
    def _chunk(content: str, title: str, chunk_size: int = 700, overlap: int = 100) -> list[dict]:
        sections = re.split(r"(?m)^#{1,3}\s+", content)
        chunks: list[dict] = []
        for raw_section in sections:
            text = raw_section.strip()
            if not text:
                continue
            lines = text.splitlines()
            section = lines[0].strip() if len(lines) > 1 and len(lines[0]) <= 80 else title
            body = "\n".join(lines[1:]).strip() if section != title else text
            if not body:
                continue
            start = 0
            while start < len(body):
                end = min(len(body), start + chunk_size)
                part = body[start:end].strip()
                if part:
                    chunks.append({"section": section, "content": part})
                if end == len(body):
                    break
                start = end - overlap
        return chunks or [{"section": title, "content": content[:chunk_size]}]

    @staticmethod
    def _document_payload(**values: object) -> dict:
        content = str(values.pop("content"))
        return {
            **values,
            "content_text": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
