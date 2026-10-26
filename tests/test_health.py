"""Tests for health check and OpenAPI documentation endpoints."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_health_endpoint(app_client: httpx.AsyncClient):
    """Verify /health returns 200 with service metadata and upstream connectivity."""
    response = await app_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "upstream" in data
    assert data["upstream"]["reachable"] is True


@pytest.mark.asyncio
async def test_openapi_schema(app_client: httpx.AsyncClient):
    """Verify /openapi.json exports a valid OpenAPI 3.x schema."""
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert schema["openapi"].startswith("3.")
    assert "paths" in schema
    assert "/api/v1/meters" in schema["paths"]
    assert "/api/v1/meters/{meter_id}" in schema["paths"]
    assert "/api/v1/meters/{meter_id}/consumption" in schema["paths"]
    assert "/api/v1/hierarchy" in schema["paths"]


@pytest.mark.asyncio
async def test_swagger_ui_available(app_client: httpx.AsyncClient):
    """Verify Swagger UI docs endpoint loads at /docs."""
    response = await app_client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "swagger-ui" in response.text.lower()
