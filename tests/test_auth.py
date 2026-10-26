"""Tests for authentication, cookie persistence, concurrent session lifecycle, and API security."""

import asyncio
import pytest
import httpx
import respx

from app.client import UrjaPortalClient
from app.config import Settings
from app.exceptions import PortalAuthenticationError, PortalSessionExpiredError
from tests.fixtures.portal_responses import (
    LOGIN_FAILURE_BODY,
    LOGIN_SUCCESS_BODY,
    SESSION_EXPIRED_BODY,
)


@pytest.mark.asyncio
async def test_successful_login(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify login sets authenticated flag and captures session cookie."""
    mock_portal.post("/login").mock(
        return_value=httpx.Response(
            200,
            headers={"Set-Cookie": "__Secure-better-auth.session_token=valid_token_abc; Path=/; HttpOnly; Secure"},
            text=LOGIN_SUCCESS_BODY,
        )
    )

    result = await portal_client.authenticate("operator@urja.local", "urja-ops-2026")
    assert result is True
    assert portal_client.is_authenticated is True
    assert any("__Secure-better-auth.session_token" in c.name for c in portal_client._client.cookies.jar)


@pytest.mark.asyncio
async def test_invalid_credentials(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify portal HTTP 200 with failure type raises PortalAuthenticationError."""
    mock_portal.post("/login").mock(
        return_value=httpx.Response(200, text=LOGIN_FAILURE_BODY)
    )

    with pytest.raises(PortalAuthenticationError) as exc_info:
        await portal_client.authenticate("bad@urja.local", "wrong-password")
    assert "Invalid upstream credentials" in str(exc_info.value)


@pytest.mark.asyncio
async def test_expired_session_reauthenticates_automatically(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify client detects expired session (401), re-authenticates, and retries request."""
    search_call_count = 0

    def search_handler(request):
        nonlocal search_call_count
        search_call_count += 1
        if search_call_count == 1:
            return httpx.Response(401, json={"error": "unauthorized", "message": "A valid session is required."})
        return httpx.Response(200, json={"data": [], "total": 0})

    mock_portal.get("/portal/meters/search").mock(side_effect=search_handler)
    mock_portal.post("/login").mock(
        return_value=httpx.Response(
            200,
            headers={"Set-Cookie": "__Secure-better-auth.session_token=reauth_token; Path=/; HttpOnly; Secure"},
            text=LOGIN_SUCCESS_BODY,
        )
    )

    portal_client._is_authenticated = True
    portal_client._client.cookies.set("__Secure-better-auth.session_token", "expired_token")

    result = await portal_client.search_meters()
    assert result == {"data": [], "total": 0}
    assert search_call_count == 2
    assert portal_client.is_authenticated is True


@pytest.mark.asyncio
async def test_concurrent_requests_on_expired_session_single_login(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify multiple concurrent requests encountering expired session trigger only ONE reauthentication."""
    login_calls = 0

    def login_handler(request):
        nonlocal login_calls
        login_calls += 1
        return httpx.Response(
            200,
            headers={"Set-Cookie": f"__Secure-better-auth.session_token=token_{login_calls}; Path=/; HttpOnly; Secure"},
            text=LOGIN_SUCCESS_BODY,
        )

    mock_portal.post("/login").mock(side_effect=login_handler)

    # Concurrent search requests: requests with expired token return 401; requests with new token return 200
    def search_handler(request: httpx.Request):
        cookie = request.headers.get("cookie", "")
        if "token_" in cookie:
            return httpx.Response(200, json={"data": [], "total": 0})
        return httpx.Response(401, json={"error": "unauthorized"})

    mock_portal.get("/portal/meters/search").mock(side_effect=search_handler)

    portal_client._is_authenticated = True
    portal_client._client.cookies.set("__Secure-better-auth.session_token", "initial_expired_token")

    # Run 5 concurrent searches
    tasks = [portal_client.search_meters(query=f"meter_{i}") for i in range(5)]
    results = await asyncio.gather(*tasks)

    for r in results:
        assert r == {"data": [], "total": 0}

    # Crucial assertion: login was called only once despite 5 concurrent 401s!
    assert login_calls == 1


@pytest.mark.asyncio
async def test_prevent_infinite_retry_loop_on_persistent_auth_failure(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify client aborts with PortalSessionExpiredError if retry also fails."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    mock_portal.post("/login").mock(
        return_value=httpx.Response(
            200,
            headers={"Set-Cookie": "__Secure-better-auth.session_token=token; Path=/; HttpOnly; Secure"},
            text=LOGIN_SUCCESS_BODY,
        )
    )

    portal_client._is_authenticated = True

    with pytest.raises(PortalSessionExpiredError):
        await portal_client.search_meters()


@pytest.mark.asyncio
async def test_auth_login_api_endpoint(app_client: httpx.AsyncClient):
    """Verify POST /api/v1/auth/login endpoint establishes session."""
    response = await app_client.post("/api/v1/auth/login", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["session_active"] is True


@pytest.mark.asyncio
async def test_auth_login_custom_credentials_forbidden_in_production(app_client: httpx.AsyncClient, test_settings: Settings):
    """Verify passing custom credentials in production environment is forbidden."""
    test_settings.app_env = "production"
    response = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "attacker@external.com", "password": "stolen_password"}
    )
    assert response.status_code == 403
    assert "forbidden" in response.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_api_key_enforcement(app_client: httpx.AsyncClient, test_settings: Settings):
    """Verify that when api_key is configured, requests without key or with wrong key return 401."""
    test_settings.api_key = "secure_ops_secret_key"

    # 1. Missing API Key
    resp_missing = await app_client.get("/api/v1/meters")
    assert resp_missing.status_code == 401
    assert "Invalid or missing API Key" in resp_missing.json()["error"]["message"]

    # 2. Invalid API Key
    resp_invalid = await app_client.get("/api/v1/meters", headers={"X-API-Key": "wrong_key"})
    assert resp_invalid.status_code == 401

    # 3. Valid API Key
    resp_valid = await app_client.get("/api/v1/meters", headers={"X-API-Key": "secure_ops_secret_key"})
    assert resp_valid.status_code == 200
    assert "data" in resp_valid.json()
