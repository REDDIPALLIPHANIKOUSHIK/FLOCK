"""Tests for meters collection, meter details, pagination slices, and validation."""

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
async def test_pagination_exact_slice_limit_2_offset_1(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify limit=2, offset=1 produces exact slice of 2 items from index 1."""
    full_20 = [
        {"meterId": f"J10000{i:02d}", "serialNo": f"SE{i:05d}", "make": "HPL", "phaseType": "single", "installStatus": "Installed", "dtCode": "DT-001"}
        for i in range(20)
    ]
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(200, json={"data": full_20, "total": 100})
    )

    response = await app_client.get("/api/v1/meters?limit=2&offset=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["data"][0]["id"] == "J1000001"
    assert data["data"][1]["id"] == "J1000002"
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 1
    assert data["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_pagination_across_page_boundary(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify offset spanning page boundary fetches additional pages to satisfy limit."""
    page_1 = [
        {"meterId": f"J10000{i:02d}", "serialNo": f"SE{i:05d}", "make": "HPL", "phaseType": "single", "installStatus": "Installed", "dtCode": "DT-001"}
        for i in range(20)
    ]
    page_2 = [
        {"meterId": f"J1000{20+i}", "serialNo": f"SE{20+i:05d}", "make": "L&T", "phaseType": "three", "installStatus": "Installed", "dtCode": "DT-002"}
        for i in range(20)
    ]

    def search_side_effect(request: httpx.Request):
        url = str(request.url)
        if "page=1" in url or "page=" not in url:
            return httpx.Response(200, json={"data": page_1, "total": 40})
        elif "page=2" in url:
            return httpx.Response(200, json={"data": page_2, "total": 40})
        return httpx.Response(200, json={"data": [], "total": 40})

    mock_portal.get("/portal/meters/search").mock(side_effect=search_side_effect)

    # Offset 19, limit 3: should take index 19 from page 1, and indices 0, 1 from page 2
    response = await app_client.get("/api/v1/meters?limit=3&offset=19")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3
    assert data["data"][0]["id"] == "J1000019"
    assert data["data"][1]["id"] == "J100020"
    assert data["data"][2]["id"] == "J100021"
    assert data["pagination"]["offset"] == 19
    assert data["pagination"]["limit"] == 3
    assert data["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_pagination_empty_results(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify query with no results returns empty data list with has_more=False."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0})
    )

    response = await app_client.get("/api/v1/meters?q=NON_EXISTENT")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
    assert data["pagination"]["total"] == 0
    assert data["pagination"]["has_more"] is False


@pytest.mark.asyncio
async def test_pagination_offset_past_total(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify offset beyond total returns empty slice without extra fetches."""
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 50})
    )

    response = await app_client.get("/api/v1/meters?offset=100&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
    assert data["pagination"]["has_more"] is False


@pytest.mark.asyncio
async def test_pagination_final_page(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify final page returns remaining items and has_more=False."""
    last_page = [
        {"meterId": f"J1000{400+i}", "serialNo": f"SE{400+i:05d}", "make": "Secure", "phaseType": "single", "installStatus": "Installed", "dtCode": "DT-005"}
        for i in range(3)
    ]
    mock_portal.get("/portal/meters/search").mock(
        return_value=httpx.Response(200, json={"data": last_page, "total": 403})
    )

    response = await app_client.get("/api/v1/meters?offset=400&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3
    assert data["pagination"]["has_more"] is False


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


@pytest.mark.asyncio
async def test_get_meter_invalid_id_format(app_client: httpx.AsyncClient):
    """Verify malformed meter ID raises 400 Bad Request."""
    response = await app_client.get("/api/v1/meters/bad@id!val$")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "BAD_REQUEST"
    assert "Invalid meter ID format" in data["error"]["message"]


@pytest.mark.asyncio
async def test_get_meter_does_not_swallow_upstream_error(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify 502/504 upstream error is propagated and NOT masked as an empty meter."""
    mock_portal.get("/meters/J100000/__data.json").mock(
        return_value=httpx.Response(502, text="Bad Gateway upstream crash")
    )

    response = await app_client.get("/api/v1/meters/J100000")
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_ERROR"


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
