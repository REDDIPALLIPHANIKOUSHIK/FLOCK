"""Tests for meters collection, meter details, and normalization edge cases."""

import pytest
import httpx
import respx

from app.models import MeterDetail
from app.services.meter_service import (
    decode_sveltekit_deval,
    normalize_meter_detail,
    parse_meter_html,
)
from tests.fixtures.portal_responses import (
    METER_HTML_FIXTURE,
    METER_J100000_DEVAL,
    METER_J100020_DEVAL,
    METER_NOT_FOUND_DEVAL,
    METERS_SEARCH_PAGE_1,
)


@pytest.mark.asyncio
async def test_list_meters(app_client: httpx.AsyncClient):
    """Verify GET /api/v1/meters returns normalized collection with pagination."""
    response = await app_client.get("/api/v1/meters")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 3

    first_meter = data["data"][0]
    assert first_meter["id"] == "J100000"
    assert first_meter["serial_number"] == "SE33962"
    assert first_meter["make"] == "HPL"
    assert first_meter["phase_type"] == "single"
    assert first_meter["status"] == "Decommissioned"
    assert first_meter["distribution_transformer_code"] == "DT-001"

    pagination = data["pagination"]
    assert pagination["limit"] == 20
    assert pagination["offset"] == 0
    assert pagination["total"] == 403
    assert pagination["has_more"] is True


@pytest.mark.asyncio
async def test_get_meter_legacy_build(app_client: httpx.AsyncClient):
    """Verify GET /api/v1/meters/J100000 returns normalized legacy meter details."""
    response = await app_client.get("/api/v1/meters/J100000")
    assert response.status_code == 200
    meter = response.json()

    assert meter["id"] == "J100000"
    assert meter["serial_number"] == "SE33962"
    assert meter["make"] == "HPL"
    assert meter["phase_type"] == "single"
    assert meter["status"] == "Decommissioned"
    assert meter["installation_type"] == "Whole Current"
    assert meter["build_type"] == "legacy"
    assert meter["distribution_transformer_code"] == "DT-001"

    assert meter["location"]["latitude"] == pytest.approx(26.938961, rel=1e-4)
    assert meter["location"]["longitude"] == pytest.approx(75.830957, rel=1e-4)

    hierarchy = meter["hierarchy"]
    assert "Jaipur Zone 1" in hierarchy["zone"]
    assert "Circle 1" in hierarchy["circle"]
    assert "Feeder 1" in hierarchy["feeder"]


@pytest.mark.asyncio
async def test_get_meter_v2_classdata_build(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify meter details correctly normalizes v2 classData format."""
    mock_portal.get("/meters/J100020/__data.json").mock(
        return_value=httpx.Response(200, json=METER_J100020_DEVAL)
    )
    mock_portal.get("/portal/meters/J100020/geo").mock(
        return_value=httpx.Response(200, json={"data": {"latitude": "26.85", "longitude": "75.80"}})
    )

    response = await app_client.get("/api/v1/meters/J100020")
    assert response.status_code == 200
    meter = response.json()

    assert meter["id"] == "J100020"
    assert meter["serial_number"] == "AL20290"
    assert meter["make"] == "Allied"
    assert meter["phase_type"] == "three"
    assert meter["status"] == "Installed"
    assert meter["installation_type"] == "CT Operated"
    assert meter["build_type"] == "v2"


@pytest.mark.asyncio
async def test_get_meter_not_found(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify unknown meter ID returns 404 with standard error structure."""
    mock_portal.get("/meters/NON_EXISTENT/__data.json").mock(
        return_value=httpx.Response(200, json=METER_NOT_FOUND_DEVAL)
    )

    response = await app_client.get("/api/v1/meters/NON_EXISTENT")
    assert response.status_code == 404
    err = response.json()
    assert "error" in err
    assert err["error"]["code"] == "NOT_FOUND"
    assert "not found" in err["error"]["message"].lower()


def test_html_parsing_fallback():
    """Verify HTML parser correctly extracts nameplate table and breadcrumbs."""
    parsed = parse_meter_html(METER_HTML_FIXTURE)
    attrs = parsed["attributes"]
    assert attrs["Meter ID"] == "J100000"
    assert attrs["Serial No"] == "SE33962"
    assert attrs["Make"] == "HPL"
    assert attrs["Phase Type"] == "single"
    assert attrs["Installation Status"] == "Decommissioned"
    assert attrs["Installation Type"] == "Whole Current"
    assert len(parsed["hierarchy_items"]) == 3
