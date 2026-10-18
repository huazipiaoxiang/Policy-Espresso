"""文档流与版本 diff（04 §4.2）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.security import require_api_key
from app.db.models import Document, DocumentVersion
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])


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
    total = db.query(Document).count()
    return {
        "items": [
            {
                "id": d.id, "source_id": d.source_id, "title": d.title, "url": d.url,
                "lang": d.lang, "published_at": d.published_at, "fetched_at": d.fetched_at,
                "status": d.status, "duplicate_of": d.duplicate_of,
                "attachments": d.attachments, "content_len": len(d.content_text or ""),
            }
            for d in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise not_found("文档", doc_id)
    return {
        "id": doc.id, "source_id": doc.source_id, "url": doc.url, "canonical_url": doc.canonical_url,
        "title": doc.title, "lang": doc.lang, "published_at": doc.published_at,
        "fetched_at": doc.fetched_at, "content_text": doc.content_text,
        "content_hash": doc.content_hash, "status": doc.status, "attachments": doc.attachments,
        "versions": [
            {"version_no": v.version_no, "changed_at": v.changed_at,
             "changed_ratio": v.changed_ratio, "minor_edit": v.minor_edit}
            for v in doc.versions
        ],
    }


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
