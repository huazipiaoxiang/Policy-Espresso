"""管理员用户管理接口：列表 / 新建 / 改角色 / 重置密码 / 删除 与权限约束。"""
ADMIN = {"X-Demo-Role": "admin"}
CONSUMER = {"X-Demo-Role": "consumer"}
PROCESSOR = {"X-Demo-Role": "processor"}


def _create(client, username: str, role: str = "consumer", password: str = "secret123") -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=ADMIN,
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_only_admin_can_access_user_management(client):
    for headers in (CONSUMER, PROCESSOR):
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
        assert client.post(
            "/api/v1/admin/users",
            headers=headers,
            json={"username": "x", "password": "secret123", "role": "consumer"},
        ).status_code == 403


def test_admin_lists_users_with_role_summary(client):
    _create(client, "user_a", "consumer")
    _create(client, "user_b", "processor")

    response = client.get("/api/v1/admin/users", headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["summary"] == {"total": 2, "admin": 0, "processor": 1, "consumer": 1}
    assert {item["username"] for item in body["items"]} == {"user_a", "user_b"}


def test_admin_searches_and_filters_users(client):
    _create(client, "alpha_user", "consumer")
    _create(client, "beta_user", "processor")

    by_keyword = client.get("/api/v1/admin/users?q=alpha", headers=ADMIN).json()
    assert [item["username"] for item in by_keyword["items"]] == ["alpha_user"]

    by_role = client.get("/api/v1/admin/users?role=processor", headers=ADMIN).json()
    assert [item["username"] for item in by_role["items"]] == ["beta_user"]


def test_create_user_validates_input_and_duplicates(client):
    _create(client, "dup_user")
    duplicate = client.post(
        "/api/v1/admin/users",
        headers=ADMIN,
        json={"username": "dup_user", "password": "secret123", "role": "consumer"},
    )
    assert duplicate.status_code == 409

    short_password = client.post(
        "/api/v1/admin/users",
        headers=ADMIN,
        json={"username": "short_pwd", "password": "123", "role": "consumer"},
    )
    assert short_password.status_code == 422

    bad_role = client.post(
        "/api/v1/admin/users",
        headers=ADMIN,
        json={"username": "bad_role", "password": "secret123", "role": "root"},
    )
    assert bad_role.status_code == 422


def test_admin_updates_role_and_resets_password(client):
    created = _create(client, "role_user", "consumer")
    user_id = created["id"]
    assert created["onboarded"] is False

    patched = client.patch(
        f"/api/v1/admin/users/{user_id}", headers=ADMIN, json={"role": "processor"}
    )
    assert patched.status_code == 200
    assert patched.json()["role"] == "processor"
    assert patched.json()["onboarded"] is True

    reset = client.patch(
        f"/api/v1/admin/users/{user_id}", headers=ADMIN, json={"password": "newpass123"}
    )
    assert reset.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "role_user", "password": "newpass123"},
    )
    assert login.status_code == 200, login.text


def test_admin_deletes_user(client):
    created = _create(client, "to_delete")
    response = client.delete(f"/api/v1/admin/users/{created['id']}", headers=ADMIN)
    assert response.status_code == 200

    remaining = client.get("/api/v1/admin/users?q=to_delete", headers=ADMIN).json()
    assert remaining["total"] == 0


def test_cannot_delete_self_or_last_admin(client):
    admin = _create(client, "admin_one", "admin")

    # 删除自己
    self_delete = client.delete(
        f"/api/v1/admin/users/{admin['id']}?actor=admin_one", headers=ADMIN
    )
    assert self_delete.status_code == 400

    # 仅剩一个管理员时不允许删除
    last_admin = client.delete(f"/api/v1/admin/users/{admin['id']}", headers=ADMIN)
    assert last_admin.status_code == 400

    # 新增第二个管理员后可以删除
    _create(client, "admin_two", "admin")
    allowed = client.delete(f"/api/v1/admin/users/{admin['id']}?actor=admin_two", headers=ADMIN)
    assert allowed.status_code == 200


def test_cannot_demote_last_admin(client):
    admin = _create(client, "solo_admin", "admin")
    response = client.patch(
        f"/api/v1/admin/users/{admin['id']}", headers=ADMIN, json={"role": "consumer"}
    )
    assert response.status_code == 400
