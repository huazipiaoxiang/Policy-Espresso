"""文档流与版本 diff（04 §4.2）。"""
from datetime import datetime
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, not_found
from app.core.security import require_api_key, require_roles
from app.db.models import AuditLog, Document, DocumentVersion, Policy, Source, new_id
from app.db.session import get_db
from app.domain.pdf_export import build_document_pdf
from app.domain.policy_admin import delete_policy_records
from app.ingest.uploads import UploadParseError, extract_upload

router = APIRouter(
    prefix="/documents", tags=["documents"],
    dependencies=[Depends(require_api_key), Depends(require_roles("admin", "analyst", "approver", "publisher"))],
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
UPLOAD_JURISDICTIONS = {"HK", "CN", "GD", "SZ", "GBA", "MO", "GB", "SG", "EU"}


def _processing_error(doc: Document) -> str:
    if doc.attachments and isinstance(doc.attachments[0], dict):
        return str(doc.attachments[0].get("processing_error") or "")
    return ""


def _document_view(doc: Document) -> dict:
    return {
        "id": doc.id, "source_id": doc.source_id, "title": doc.title, "url": doc.url,
        "lang": doc.lang, "published_at": doc.published_at, "fetched_at": doc.fetched_at,
        "status": doc.status, "duplicate_of": doc.duplicate_of,
        "attachments": doc.attachments, "content_len": len(doc.content_text or ""),
        "processing_error": _processing_error(doc),
        "policy_id": doc.policy.id if doc.policy else None,
        "source_name": doc.source.name if doc.source else "",
        # 手动上传没有数据源辖区，市场记在生成的政策上，列表按政策辖区展示
        "jurisdiction": (doc.source.jurisdiction if doc.source else "")
        or (doc.policy.jurisdiction if doc.policy else ""),
    }


@router.get("")
def list_documents(
    page: int = 1,
    page_size: int = 20,
    source_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Document).order_by(Document.published_at.desc().nullslast(), Document.fetched_at.desc())
    if source_id:
        stmt = stmt.where(Document.source_id == source_id)
    if status:
        stmt = stmt.where(Document.status == status)
    items = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    count_stmt = select(func.count(Document.id))
    if source_id:
        count_stmt = count_stmt.where(Document.source_id == source_id)
    if status:
        count_stmt = count_stmt.where(Document.status == status)
    total = db.execute(count_stmt).scalar() or 0
    return {
        "items": [_document_view(d) for d in items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    published_at: datetime | None = Form(default=None),
    jurisdiction: str | None = Form(default=None),
    db: Session = Depends(get_db),
    actor: str = Depends(require_api_key),
    _: str = Depends(require_roles("admin")),
):
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise ApiError("UNSUPPORTED_FILE", "仅支持 PDF、DOC、DOCX、XLS、XLSX 文件", 422)
    jurisdiction = (jurisdiction or "").strip().upper()
    if not jurisdiction:
        raise ApiError("MISSING_JURISDICTION", "请选择政策所属市场", 422)
    if jurisdiction not in UPLOAD_JURISDICTIONS:
        raise ApiError("INVALID_JURISDICTION", f"不支持的市场代码 {jurisdiction}", 422)

    settings = get_settings()
    upload_dir = Path(settings.storage_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = new_id("d")
    destination = upload_dir / f"{document_id}{suffix}"
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ApiError("FILE_TOO_LARGE", "文件不能超过 20 MB", 413)
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    if size == 0:
        destination.unlink(missing_ok=True)
        raise ApiError("EMPTY_FILE", "不能上传空文件", 422)

    content_hash = digest.hexdigest()
    duplicate = db.scalar(select(Document).where(Document.content_hash == content_hash))
    if duplicate:
        destination.unlink(missing_ok=True)
        raise ApiError("DUPLICATE_DOCUMENT", "相同文件已存在，未重复上传", 409, {"document_id": duplicate.id})

    source = db.scalar(select(Source).where(Source.code == "manual_upload"))
    if not source:
        source = Source(
            code="manual_upload", name="管理员手动上传", org="HORIZON",
            jurisdiction="", tier=1, adapter="manual", url="upload://manual", lang="zh",
            enabled=False,
        )
        db.add(source)
        db.flush()

    attachment = {
        "name": original_name, "path": str(destination.relative_to(Path(settings.storage_dir))),
        "content_type": file.content_type or "", "size": size, "processing_error": "",
    }
    doc = Document(
        id=document_id, source_id=source.id, url=f"upload://{document_id}",
        canonical_url=f"upload://{document_id}", title=(title or "").strip() or Path(original_name).stem,
        lang="zh", published_at=published_at, content_text="", content_hash=content_hash,
        doc_type="upload", attachments=[attachment], status="new",
    )
    db.add(doc)
    db.commit()

    processing_error = ""
    try:
        doc.content_text = extract_upload(destination, suffix)
        if len(doc.content_text.strip()) < 50:
            raise UploadParseError("未提取到足够正文，请检查文件是否损坏或仅包含扫描图片")
        doc.status = "new"
        db.commit()
        from app.jobs.analyze_job import analyze_document

        policy = analyze_document(db, doc)
        if policy is None:
            processing_error = "文件已解析，但未生成政策：非金融政策或正文不足"
        elif jurisdiction:
            # 手动上传没有数据源辖区，市场由上传人指定，否则政策库与推荐都无法按市场筛选
            policy.jurisdiction = jurisdiction
    except Exception as exc:
        db.rollback()
        processing_error = str(exc) if isinstance(exc, UploadParseError) else f"分析失败：{type(exc).__name__}: {exc}"
        existing = db.scalar(select(Policy).where(Policy.document_id == doc.id))
        if existing:
            delete_policy_records(db, existing)
            doc.policy = None
        doc.status = "failed"

    doc.attachments = [{**attachment, "processing_error": processing_error}]
    db.add(AuditLog(
        actor=actor, action="upload_document", object_type="document", object_id=doc.id,
        before={}, after={"status": doc.status, "policy_id": doc.policy.id if doc.policy else None},
        reason=processing_error or "原文件保存并完成现有解析分析流程",
    ))
    db.commit()
    return {
        **_document_view(doc), "processing_status": "failed" if doc.status == "failed" else "completed",
    }


@router.get("/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise not_found("文档", doc_id)
    return {
        **_document_view(doc),
        "canonical_url": doc.canonical_url,
        "title": doc.title, "lang": doc.lang, "published_at": doc.published_at,
        "fetched_at": doc.fetched_at, "content_text": doc.content_text,
        "content_hash": doc.content_hash, "status": doc.status, "attachments": doc.attachments,
        "versions": [
            {"version_no": v.version_no, "changed_at": v.changed_at,
             "changed_ratio": v.changed_ratio, "minor_edit": v.minor_edit}
            for v in doc.versions
        ],
    }


@router.get("/{doc_id}/pdf")
def download_document_pdf(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise not_found("文档", doc_id)

    settings = get_settings()
    for att in doc.attachments or []:
        rel = att.get("path") if isinstance(att, dict) else ""
        if rel:
            candidate = Path(settings.storage_dir) / rel
            if candidate.is_file():
                media = "application/pdf" if candidate.suffix.lower() == ".pdf" else "application/octet-stream"
                return FileResponse(candidate, media_type=media, filename=f"{doc_id}{candidate.suffix}")

    if not (doc.content_text or "").strip():
        raise ApiError("NO_CONTENT", "该文档暂无可用正文，无法导出 PDF", 404)

    try:
        payload = build_document_pdf(
            title=doc.title or doc_id,
            doc_id=doc.id,
            source_name=doc.source.name if doc.source else "",
            jurisdiction=(doc.source.jurisdiction if doc.source else "")
            or (doc.policy.jurisdiction if doc.policy else ""),
            published_at=str(doc.published_at) if doc.published_at else None,
            lang=doc.lang or "zh",
            content_text=doc.content_text,
        )
    except Exception as exc:
        raise ApiError("PDF_EXPORT_FAILED", f"PDF 生成失败：{type(exc).__name__}: {exc}", 500)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc_id}.pdf"'},
    )


@router.get("/{doc_id}/versions/{version_no}/diff")
def get_version_diff(doc_id: str, version_no: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise not_found("文档", doc_id)
    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc_id, DocumentVersion.version_no == version_no
        )
    )
    if not version:
        raise not_found("文档版本", f"{doc_id}@v{version_no}")
    return {
        "document_id": doc_id, "version_no": version_no,
        "changed_at": version.changed_at, "changed_ratio": version.changed_ratio,
        "minor_edit": version.minor_edit, "diff": version.diff_json.get("items", []),
    }
