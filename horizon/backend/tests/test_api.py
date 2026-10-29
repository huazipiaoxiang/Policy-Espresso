def test_healthz(client):
    resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["llm_provider"] == "mock"


def test_auth_required(client):
    resp = client.get("/api/v1/sources", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_sources_crud(client):
    admin = {"X-Demo-Role": "admin"}
    resp = client.post("/api/v1/sources", headers=admin, json={
        "code": "hkma_press", "name": "香港金管局 · 新闻稿", "jurisdiction": "HK",
        "adapter": "rss", "url": "https://www.hkma.gov.hk/",
    })
    assert resp.status_code == 201
    src = resp.json()
    assert src["code"] == "hkma_press"

    dup = client.post("/api/v1/sources", headers=admin, json={
        "code": "hkma_press", "name": "x", "jurisdiction": "HK", "adapter": "rss", "url": "https://x",
    })
    assert dup.status_code == 409

    listed = client.get("/api/v1/sources", headers=admin).json()
    assert listed["total"] >= 1

    patched = client.patch(f"/api/v1/sources/{src['id']}", headers=admin, json={"enabled": False})
    assert patched.json()["enabled"] is False


def test_dispatch_blocked_until_approved(client):
    # 造一个 draft 政策：未审核分发必须 409（01 §三.5 硬规则）
    from app.db.models import Document, Policy, Source
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        src = Source(code="t_src", name="t", jurisdiction="HK", adapter="manual", url="https://x")
        db.add(src)
        db.flush()
        doc = Document(source_id=src.id, url="https://x/p", canonical_url="https://x/p", title="t", content_hash="h")
        db.add(doc)
        db.flush()
        policy = Policy(document_id=doc.id, title="t", status="in_review")
        db.add(policy)
        db.commit()
        pid = policy.id

    resp = client.post(f"/api/v1/policies/{pid}/dispatch", headers={"X-Demo-Role": "publisher"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "NOT_APPROVED"
    assert body["error"]["detail"]["current_status"] == "in_review"


def test_document_delete_cascades_policy(client):
    # 原文删除：admin 可删，关联政策级联清除；非 admin 403
    from app.db.models import Document, Policy, Source
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        src = Source(code="t_doc_src", name="t", jurisdiction="HK", adapter="manual", url="https://x")
        db.add(src)
        db.flush()
        doc = Document(source_id=src.id, url="https://x/d", canonical_url="https://x/d", title="t doc", content_hash="hd")
        db.add(doc)
        db.flush()
        policy = Policy(document_id=doc.id, title="t policy", status="draft")
        db.add(policy)
        db.commit()
        doc_id, pid = doc.id, policy.id

    forbidden = client.delete(f"/api/v1/documents/{doc_id}", headers={"X-Demo-Role": "analyst"})
    assert forbidden.status_code == 403

    resp = client.delete(f"/api/v1/documents/{doc_id}", headers={"X-Demo-Role": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok" and body["policy_deleted"] is True

    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert client.get(f"/api/v1/policies/{pid}").status_code == 404

    missing = client.delete("/api/v1/documents/d_nonexistent", headers={"X-Demo-Role": "admin"})
    assert missing.status_code == 404


def test_analytics_overview(client):
    resp = client.get("/api/v1/analytics/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"today_new", "pending_review", "p0_p1_open", "sources_total"}
