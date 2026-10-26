"""Shared pytest fixtures, mock transports, and test client configurations."""

import pytest
import pytest_asyncio
import respx
import httpx
from fastapi import FastAPI

from app.client import UrjaPortalClient
from app.config import Settings, get_settings
from app.dependencies import get_portal_client
from app.main import app
from tests.fixtures.portal_responses import (
    LOGIN_SUCCESS_BODY,
    METERS_SEARCH_PAGE_1,
    METER_J100000_DEVAL,
    METER_J100000_GEO,
    METER_J100000_ENERGY,
    DTS_RESPONSE,
)


@pytest.fixture
def test_settings() -> Settings:
    """Return isolated test settings."""
    return Settings(
        app_name="Urja Meter Ops API (Test)",
        app_version="1.0.0-test",
        app_env="test",
        log_level="DEBUG",
        urja_base_url="https://urja-ops.flockenergy.tech",
        urja_username="operator@urja.local",
        urja_password="urja-ops-2026",
        upstream_timeout_seconds=5.0,
        upstream_max_retries=1,
        mock_mode=False,
    )


@pytest_asyncio.fixture
async def portal_client(test_settings: Settings) -> UrjaPortalClient:
    """Provide an initialized UrjaPortalClient for unit tests."""
    client = UrjaPortalClient(test_settings)
    await client.start()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def mock_portal():
    """Mock the upstream legacy Urja portal with respx."""
    async with respx.mock(base_url="https://urja-ops.flockenergy.tech", assert_all_called=False) as respx_mock:
        # Standard mock routes
        respx_mock.post("/login").mock(
            return_value=httpx.Response(
                200,
                headers={"Set-Cookie": "__Secure-better-auth.session_token=test_session_token_123; Path=/; HttpOnly; Secure"},
                text=LOGIN_SUCCESS_BODY
            )
        )
        respx_mock.get("/portal/meters/search").mock(
            return_value=httpx.Response(200, json=METERS_SEARCH_PAGE_1)
        )
        respx_mock.get("/meters/J100000/__data.json").mock(
            return_value=httpx.Response(200, json=METER_J100000_DEVAL)
        )
        respx_mock.get("/portal/meters/J100000/geo").mock(
            return_value=httpx.Response(200, json=METER_J100000_GEO)
        )
        respx_mock.get("/portal/meters/J100000/energy").mock(
            return_value=httpx.Response(200, json=METER_J100000_ENERGY)
        )
        respx_mock.get("/portal/dts").mock(
            return_value=httpx.Response(200, json=DTS_RESPONSE)
        )
        respx_mock.get("/").mock(
            return_value=httpx.Response(200, text="<!doctype html><html><body>Urja Ops</body></html>")
        )

        yield respx_mock


@pytest_asyncio.fixture
async def app_client(test_settings: Settings, mock_portal) -> httpx.AsyncClient:
    """Async HTTP test client for the FastAPI app."""
    # Override settings and portal client dependency with test configuration
    test_client = UrjaPortalClient(test_settings)
    await test_client.start()
    # Pre-authenticate client with mock cookie
    test_client._client.cookies.set("__Secure-better-auth.session_token", "test_token_123")
    test_client._is_authenticated = True

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_portal_client] = lambda: test_client

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        yield client

    await test_client.close()
    app.dependency_overrides.clear()
