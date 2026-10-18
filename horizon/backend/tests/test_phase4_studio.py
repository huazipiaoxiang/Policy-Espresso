"""Phase 4 验收：政策 2.0（T2-01..T2-05）+ 案例检索 + 业务图谱。"""
from __future__ import annotations


def _seed_and_analyze(client):
    """灌入用例 1 样本并跑分析（供图谱矩阵有数据）。"""
    from sqlalchemy import select

    from app.db.models import Document, Source
    from app.db.session import SessionLocal
    from app.ingest.normalize import normalize_html
    from app.jobs.analyze_job import analyze_document
    from app.jobs.seed_job import seed_cases, seed_sources
    from pathlib import Path

    html = Path(__file__).resolve().parent / "fixtures" / "gd_subsidy_policy.html"
    with SessionLocal() as db:
        seed_sources(db)
        seed_cases(db)
        src = db.query(Source).filter(Source.code == "gd_gov").first()
        norm = normalize_html(html.read_text(encoding="utf-8"), "https://demo.local/p4",
                              fallback_title="关于做好中小微企业贷款贴息工作的通知")
        doc = Document(source_id=src.id, url="https://demo.local/p4", canonical_url="https://demo.local/p4",
                       title=norm.title, lang=norm.lang, published_at=norm.published_at,
                       content_text=norm.content_text, content_hash="p4", status="new")
        db.add(doc)
        db.commit()
        analyze_document(db, db.get(Document, doc.id))


def test_corpus_index_marks_validity(client):
    """T2-09 前置：语料索引带有效性，已废止不得作依据。"""
    from app.domain.studio_corpus import load_corpus

    corpus_all = load_corpus(include_all_validity=True)
    corpus_effective = load_corpus()
    assert corpus_all.docs, "语料库不能为空"
    assert all(d.effective for d in corpus_effective.docs)
    assert len(corpus_all.docs) >= len(corpus_effective.docs)
    assert all(d.doc_number and d.published_at for d in corpus_all.docs), "每份文件必须有文号与发布日期"


def test_studio_generate_full_acceptance(client):
    """T2-01..T2-05：生成 5–8 条建议，五段结构，引用可回溯，突破项 boundary warn。"""
    from app.ai.chains.studio import validate_proposal
    from app.ai.evidence import locate_quote
    from app.domain.studio_corpus import load_corpus

    corpus = load_corpus()
    from app.ai.chains.studio import StudioChain

    result = StudioChain().run(theme="跨境金融", corpus_text=corpus.text)
    parsed = result.parsed

    # T2-01 数量与主题覆盖
    proposals = parsed["proposals"]
    assert 5 <= len(proposals) <= 8
    assert len({p["theme"] for p in proposals}) >= 3

    # T2-02 五段固定结构
    for p in proposals:
        assert p["current_basis"] and p["non_conflict_argument"] and p["draft_clause"]
        assert p["impact"]["on_hk"] and p["impact"]["on_hsbc"] and p["impact"]["on_industry"]
        assert p["risks"] and p["kpis"]

    # T2-03 current_basis quote 可在语料定位
    for p in proposals:
        for basis in p["current_basis"]:
            assert locate_quote(corpus.text, basis["quote"]) is not None, f"引文不可回溯: {basis['quote'][:20]}"

    # T2-04 拟条文四要素
    for p in proposals:
        draft = p["draft_clause"]
        for element in ("适用主体", "条件", "程序", "监管分工"):
            assert element in draft, f"{p['id']} 拟条文缺少 {element}"

    # T2-05 突破项 boundary 必须 warn/fail
    breakthrough = [p for p in proposals if "突破" in p["draft_clause"] or "取消" in p["draft_clause"]]
    assert breakthrough, "样本应含至少一条突破档建议"
    for p in breakthrough:
        check = next((c for c in parsed["boundary_check"] if c["proposal_id"] == p["id"]), None)
        assert check and check["status"] in ("warn", "fail"), f"{p['id']} 突破项 boundary 必须 warn/fail"

    # T2-06 无断言式预测
    full_text = str(parsed)
    for banned in ("中国政府将", "香港将立法", "必将出台"):
        assert banned not in full_text

    # T2-07 免责声明
    assert "未经政策与合规审核不得对外" in parsed["disclaimer"]

    # 自检函数本身
    assert validate_proposal(parsed, corpus.text) == []


def test_studio_api_flow(client):
    """API 流：建项目 → 生成 → 详情 → 双审 → reviewed。"""
    r = client.post("/api/v1/studio/projects", json={"name": "CEPA 推演", "theme": "跨境金融"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    r = client.post(f"/api/v1/studio/projects/{project_id}/generate")
    assert r.status_code == 202
    assert r.json()["proposals"] >= 5
    proposal_id = r.json()["proposal_id"]

    r = client.get(f"/api/v1/studio/proposals/{proposal_id}")
    assert r.status_code == 200
    assert r.json()["disclaimer"]

    # 单签不够
    client.post(f"/api/v1/studio/proposals/{proposal_id}/review",
                json={"role": "expert", "approve": True})
    r = client.post(f"/api/v1/studio/proposals/{proposal_id}/review",
                    json={"role": "compliance", "approve": True})
    assert r.json()["project_status"] == "reviewed"  # 双签齐才可导出


def test_cases_search(client):
    """案例检索：关键词 + 业务线加权。"""
    from app.jobs.seed_job import seed_cases
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        seed_cases(db)

    r = client.get("/api/v1/cases?q=贴息")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and any("贴息" in c["title"] for c in items)

    r = client.get("/api/v1/cases?business_line=CMB")
    assert r.status_code == 200 and r.json()["items"]


def test_business_map_matrix(client):
    """图谱矩阵：行=业务线，格值=数量+均分。"""
    _seed_and_analyze(client)
    r = client.get("/api/v1/business-map")
    assert r.status_code == 200
    body = r.json()
    assert "CMB" in body["matrix"]
    assert body["themes"], "主题列不能为空"
    cells = body["matrix"]["CMB"]["cells"]
    assert "贷款与贴息" in cells
    assert cells["贷款与贴息"]["policy_count"] >= 1
