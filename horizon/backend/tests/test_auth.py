"""Registration and login follow the current three-role contract."""
import pytest


@pytest.mark.parametrize("role", ["admin", "consumer", "processor"])
def test_register_login_and_onboarding(client, role):
    credentials = {"username": f"test-{role}", "password": "test-only-password"}
    registered = client.post("/api/v1/auth/register", json={**credentials, "role": role})
    assert registered.status_code == 201
    account = registered.json()
    assert account["role"] == role and account["onboarded"] is False
    assert "password" not in account and "password_hash" not in account

    logged_in = client.post("/api/v1/auth/login", json=credentials)
    assert logged_in.status_code == 200 and logged_in.json() == account
    assert client.post("/api/v1/auth/login", json={**credentials, "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/register", json={**credentials, "role": role}).status_code == 409

    onboarded = client.post("/api/v1/auth/onboard", json=credentials)
    assert onboarded.status_code == 200 and onboarded.json()["onboarded"] is True
    assert client.post("/api/v1/auth/login", json=credentials).json()["onboarded"] is True


@pytest.mark.parametrize("role", ["analyst", "approver", "publisher"])
def test_removed_roles_cannot_register_or_access_protected_routes(client, role):
    registration = client.post("/api/v1/auth/register", json={
        "username": "removed-role", "password": "test-only-password", "role": role,
    })
    assert registration.status_code == 422
    assert client.get("/api/v1/policies", headers={"X-Demo-Role": role}).status_code == 401
