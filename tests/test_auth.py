from __future__ import annotations

from fastapi.testclient import TestClient

from auth.security import create_access_token
from auth.security import decode_access_token
from auth.security import verify_password
from dashboard.app import create_app


def build_client(temp_settings) -> TestClient:
    return TestClient(create_app(temp_settings))


def test_signup_login_and_jwt_cookie_session(temp_settings):
    client = build_client(temp_settings)

    signup_response = client.post(
        "/signup",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert signup_response.status_code == 303
    assert temp_settings.auth.cookie_name in signup_response.headers["set-cookie"]

    user = client.app.state.auth_service.get_user_by_username_or_email("alice")
    assert user is not None
    assert user.password_hash != "password123"
    assert verify_password("password123", user.password_hash)
    assert user.role == "admin"

    client.get("/logout", follow_redirects=False)
    login_response = client.post(
        "/login",
        data={
            "username_or_email": "alice",
            "password": "password123",
            "next_path": "/runs",
        },
        follow_redirects=False,
    )
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/runs"


def test_invalid_login_returns_401(temp_settings):
    client = build_client(temp_settings)
    client.app.state.auth_service.create_user(
        username="alice",
        email="alice@example.com",
        password="password123",
    )

    response = client.post(
        "/login",
        data={
            "username_or_email": "alice",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert "Invalid username" in response.text


def test_jwt_validation_rejects_tampered_token(temp_settings):
    service = create_app(temp_settings).state.auth_service
    user = service.create_user(
        username="alice",
        email="alice@example.com",
        password="password123",
    )
    token = create_access_token(
        settings=temp_settings.auth,
        user_id=user.user_id,
        role=user.role,
    )

    assert decode_access_token(temp_settings.auth, token)["sub"] == user.user_id
    assert decode_access_token(temp_settings.auth, token + "tampered") is None


def test_protected_pages_and_apis_require_auth(temp_settings):
    client = build_client(temp_settings)

    page_response = client.get("/runs", follow_redirects=False)
    api_response = client.get("/api/runs")

    assert page_response.status_code == 303
    assert page_response.headers["location"].startswith("/login")
    assert api_response.status_code == 401
    assert api_response.json()["error"] == "Authentication required."


def test_user_run_ownership_is_enforced(temp_settings, make_dashboard_run):
    client = build_client(temp_settings)
    service = client.app.state.auth_service
    service.create_user(
        username="admin",
        email="admin@example.com",
        password="password123",
        role="admin",
    )
    alice = service.create_user(
        username="alice",
        email="alice@example.com",
        password="password123",
        role="user",
    )
    service.create_user(
        username="bob",
        email="bob@example.com",
        password="password123",
        role="user",
    )
    run_id = "20260524T130000000000Z"
    make_dashboard_run(run_id=run_id, owner_user_id=alice.user_id)

    client.post(
        "/login",
        data={"username_or_email": "bob", "password": "password123"},
        follow_redirects=False,
    )

    runs_response = client.get("/api/runs")
    detail_response = client.get(f"/runs/{run_id}")

    assert runs_response.status_code == 200
    assert runs_response.json()["runs"] == []
    assert detail_response.status_code == 404
