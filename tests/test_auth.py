"""Tests for authentication, cookie persistence, and session lifecycle."""

import pytest
import httpx
import respx

from app.client import UrjaPortalClient
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
    # First search request returns 401
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

    # Initial state: authenticated
    portal_client._is_authenticated = True
    portal_client._client.cookies.set("__Secure-better-auth.session_token", "expired_token")

    result = await portal_client.search_meters()
    assert result == {"data": [], "total": 0}
    assert search_call_count == 2
    assert portal_client.is_authenticated is True


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
async def test_auth_login_api_endpoint(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify POST /api/v1/auth/login endpoint."""
    response = await app_client.post("/api/v1/auth/login", json={"email": "operator@urja.local", "password": "urja-ops-2026"})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["session_active"] is True
