def test_settings_snapshot(client):
    resp = client.get("/api/v1/settings", headers={"X-Demo-Role": "admin"})
    assert resp.status_code == 200
    body = resp.json()

    # 运行时状态
    assert body["runtime"]["db"] == "ok"
    assert body["runtime"]["llm_provider"] == "mock"
    assert body["runtime"]["storage_backend"] == "local"

    # 模型分层路由（classify 走 flash 档）
    assert body["llm"]["provider"] == "mock"
    assert body["llm"]["model_tier"]["classify"] == "qwen-flash"

    # 抓取合规
    assert body["crawl"]["respect_robots"] is True

    # 通知：站内始终在场
    assert body["notify"]["inapp"] == "configured"

    # 安全
    assert body["security"]["auth"] == "api_key"

    # 存储：本地目录脱敏为布尔，不暴露文件系统路径
    assert isinstance(body["storage"]["storage_dir_configured"], bool)
    assert "storage_dir" not in body["storage"]


def test_settings_no_secret_leak(client):
    """密钥类字段绝不返回明文（只返回 bool / 是否配置）。"""
    resp = client.get("/api/v1/settings", headers={"X-Demo-Role": "admin"})
    body = resp.json()

    # 密钥配置状态只用布尔表达
    assert isinstance(body["llm"]["dashscope_configured"], bool)
    assert isinstance(body["security"]["job_trigger_token_configured"], bool)
    assert isinstance(body["storage"]["oss_configured"], bool)

    # 通知通道不返回完整 webhook URL（只返回是否配置）
    for channel in ("email", "wecom", "feishu"):
        assert body["notify"][channel] in ("", "configured")

    # 任何字段都不包含明文密钥
    flat = str(body)
    assert "test-key" not in flat
    assert "sk-" not in flat


def test_settings_requires_auth(client):
    resp = client.get("/api/v1/settings", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
