"""政策 2.0 工作台 API（04 §4.2 /studio）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chains.studio import StudioChain
from app.core.errors import ApiError, not_found
from app.core.security import require_api_key
from app.db.models import Proposal, StudioProject
from app.db.session import get_db
from app.domain.studio_corpus import load_corpus

router = APIRouter(prefix="/studio", tags=["studio"], dependencies=[Depends(require_api_key)])

DISCLAIMER = "AI 辅助生成，仅供内部研讨，未经政策与合规审核不得对外。"


class ProjectCreate(BaseModel):
    name: str
    theme: str = "跨境金融"
    constraints: dict | None = None


class ReviewBody(BaseModel):
    role: str  # expert / compliance
    approve: bool
    note: str = ""


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = StudioProject(name=body.name, theme=body.theme, constraints=body.constraints or {})
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name, "theme": project.theme, "status": project.status}


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.scalars(select(StudioProject).order_by(StudioProject.created_at.desc())).all()
    return {
        "items": [
            {"id": p.id, "name": p.name, "theme": p.theme, "status": p.status, "created_at": p.created_at}
            for p in projects
        ]
    }


@router.get("/projects/{project_id}/proposals")
def list_proposals(project_id: str, db: Session = Depends(get_db)):
    """项目下的建议书版本列表（最新在前）。"""
    project = db.get(StudioProject, project_id)
    if not project:
        raise not_found("Studio 项目", project_id)
    proposals = db.scalars(
        select(Proposal).where(Proposal.project_id == project_id).order_by(Proposal.version.desc())
    ).all()
    return {
        "items": [
            {"id": p.id, "version": p.version, "created_at": p.created_at,
             "proposals": len(p.sections.get("proposals", [])) if isinstance(p.sections, dict) else 0}
            for p in proposals
        ]
    }


@router.get("/corpus")
def corpus_index():
    """语料索引（含有效性——T2-09 关键：已废止文件不得作依据）。"""
    corpus = load_corpus(include_all_validity=True)
    return {
        "themes": corpus.themes,
        "docs": [
            {
                "doc_id": d.doc_id, "title": d.title, "issuing_bodies": d.issuing_bodies,
                "doc_number": d.doc_number, "published_at": d.published_at,
                "validity": d.validity, "themes": d.themes, "effective": d.effective,
            }
            for d in corpus.docs
        ],
        "disclaimer": DISCLAIMER,
    }


@router.post("/projects/{project_id}/generate", status_code=202)
def generate(project_id: str, db: Session = Depends(get_db)):
    project = db.get(StudioProject, project_id)
    if not project:
        raise not_found("Studio 项目", project_id)
    corpus = load_corpus()  # 只含现行有效/已修订
    if not corpus.docs:
        raise ApiError("CORPUS_EMPTY", "语料库为空，请检查 seed/cepa/", 422)

    chain = StudioChain()
    result = chain.run(theme=project.theme, corpus_text=corpus.text)

    version = (
        db.scalar(select(Proposal).where(Proposal.project_id == project_id).order_by(Proposal.version.desc()))
    )
    next_version = (version.version if version else 0) + 1
    proposal = Proposal(
        project_id=project_id, version=next_version,
        sections=result.parsed, boundary_check={"items": result.parsed.get("boundary_check", [])},
        reviewer_notes="",
    )
    db.add(proposal)
    project.status = "generated"
    db.commit()
    db.refresh(proposal)
    return {"proposal_id": proposal.id, "version": next_version,
            "proposals": len(result.parsed.get("proposals", [])), "status": project.status}


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: Session = Depends(get_db)):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        raise not_found("建议书", proposal_id)
    corpus = load_corpus(include_all_validity=True)
    return {
        "id": proposal.id, "project_id": proposal.project_id, "version": proposal.version,
        "sections": proposal.sections, "boundary_check": proposal.boundary_check,
        "reviewer_notes": proposal.reviewer_notes, "created_at": proposal.created_at,
        "corpus": [
            {"doc_id": d.doc_id, "title": d.title, "published_at": d.published_at,
             "validity": d.validity, "themes": d.themes}
            for d in corpus.docs
        ],
        "disclaimer": DISCLAIMER,
    }


@router.post("/proposals/{proposal_id}/review")
def review_proposal(proposal_id: str, body: ReviewBody, db: Session = Depends(get_db)):
    """专家 + 合规双审（T2-10）：两签齐才能导出对外版本。"""
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        raise not_found("建议书", proposal_id)
    if body.role not in ("expert", "compliance"):
        raise ApiError("BAD_ROLE", "role 须为 expert/compliance", 422)

    notes = proposal.reviewer_notes or ""
    stamp = f"{datetime.now(timezone.utc).isoformat()} {body.role} {'通过' if body.approve else '驳回'} {body.note}".strip()
    proposal.reviewer_notes = f"{notes}\n{stamp}".strip()

    approved = proposal.reviewer_notes
    project = db.get(StudioProject, proposal.project_id)
    if "expert 通过" in approved and "compliance 通过" in approved:
        project.status = "reviewed"  # 可导出对外版本（仍带水印/免责声明）
    db.commit()
    return {"proposal_id": proposal_id, "role": body.role, "approve": body.approve,
            "project_status": project.status, "reviewer_notes": proposal.reviewer_notes}
