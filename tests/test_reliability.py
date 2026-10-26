"""Tests for reliability, upstream errors, timeouts, rate limits, and security."""

import pytest
import httpx
import respx

from app.client import UrjaPortalClient
from app.exceptions import (
    PortalNotFoundError,
    PortalRateLimitError,
    PortalTimeoutError,
    PortalUpstreamError,
)


@pytest.mark.asyncio
async def test_upstream_timeout(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify httpx.TimeoutException maps to PortalTimeoutError (504)."""
    mock_portal.get("/portal/meters/search").mock(side_effect=httpx.ReadTimeout("Connection timed out"))
    portal_client._is_authenticated = True

    with pytest.raises(PortalTimeoutError):
        await portal_client.search_meters()


@pytest.mark.asyncio
async def test_upstream_rate_limiting(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify HTTP 429 maps to PortalRateLimitError with Retry-After header."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "30"}, text="Too Many Requests")
    )
    portal_client._is_authenticated = True

    with pytest.raises(PortalRateLimitError) as exc_info:
        await portal_client.search_meters()
    assert exc_info.value.retry_after == 30
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_upstream_500_error(portal_client: UrjaPortalClient, mock_portal: respx.MockRouter):
    """Verify upstream 500 server error maps to PortalUpstreamError."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    portal_client._is_authenticated = True

    with pytest.raises(PortalUpstreamError) as exc_info:
        await portal_client.search_meters()
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_secret_redaction_in_error_responses(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify error responses never leak passwords or session tokens."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(500, text="Crash with secret password=urja-ops-2026")
    )

    response = await app_client.get("/api/v1/meters")
    assert response.status_code == 502
    data = response.json()
    assert "error" in data
    error_text = str(data)
    assert "urja-ops-2026" not in error_text
    assert "session_token" not in error_text
