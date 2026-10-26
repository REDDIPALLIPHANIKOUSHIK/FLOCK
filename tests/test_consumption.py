"""Tests for consumption readings, date filters, and energy normalization."""

import pytest
import httpx
import respx

from app.services.meter_service import normalize_consumption


@pytest.mark.asyncio
async def test_get_consumption(app_client: httpx.AsyncClient):
    """Verify consumption endpoint returns validated interval records."""
    response = await app_client.get("/api/v1/meters/J100000/consumption")
    assert response.status_code == 200
    data = response.json()

    assert data["meter_id"] == "J100000"
    assert data["reading_count"] == 3
    assert data["unit_kwh"] == "kWh (cumulative)"
    assert data["unit_kvah"] == "kVAh (cumulative)"
    assert data["unit_voltage"] == "V (R-phase)"

    readings = data["readings"]
    assert len(readings) == 3

    first = readings[0]
    assert first["timestamp"].startswith("2026-06-24T00:00:00")
    assert first["raw_timestamp"] == "24/06/2026 00:00"
    assert first["kwh"] == 48439.16
    assert first["kvah"] == 52314.29
    assert first["voltage_r"] == 229.0


@pytest.mark.asyncio
async def test_consumption_date_filtering(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify from/to query parameters are passed upstream."""
    mock_portal.get("/portal/meters/J100000/energy").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"timestamp": "25/06/2026 00:00", "kwh": "48500.00", "kvah": "52400.00", "voltR": "230"}]}
        )
    )

    response = await app_client.get("/api/v1/meters/J100000/consumption?from=2026-06-25&to=2026-06-26")
    assert response.status_code == 200
    data = response.json()
    assert data["reading_count"] == 1
    assert data["readings"][0]["kwh"] == 48500.00


@pytest.mark.asyncio
async def test_consumption_invalid_date_order(app_client: httpx.AsyncClient):
    """Verify from > to returns 400 Bad Request."""
    response = await app_client.get("/api/v1/meters/J100000/consumption?from=2026-06-30&to=2026-06-01")
    assert response.status_code == 400
    err = response.json()
    assert "error" in err
    assert "less than or equal to" in err["error"]["message"]


def test_consumption_normalization_robustness():
    """Verify parser handles missing readings, dashes '—', and empty strings gracefully."""
    raw = [
        {"timestamp": "24/06/2026 00:00", "kwh": "—", "kvah": "", "voltR": None},
        {"timestamp": "invalid_date_format", "kwh": "100.0"},
        {"timestamp": "24/06/2026 00:30", "kwh": "48439.58", "kvah": "52314.75", "voltR": "220"},
    ]
    res = normalize_consumption("TEST_METER", raw)
    assert res.reading_count == 2
    r1, r2 = res.readings
    assert r1.kwh is None
    assert r1.kvah is None
    assert r1.voltage_r is None
    assert r2.kwh == 48439.58


@pytest.mark.asyncio
async def test_consumption_invalid_meter_id(app_client: httpx.AsyncClient):
    """Verify consumption rejects invalid meter identifier with 400 Bad Request."""
    response = await app_client.get("/api/v1/meters/bad;drop/consumption")
    assert response.status_code == 400
    assert "Invalid meter ID format" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_consumption_invalid_calendar_date(app_client: httpx.AsyncClient):
    """Verify invalid calendar dates like 2026-02-31 are rejected with 400 Bad Request."""
    response = await app_client.get("/api/v1/meters/J100000/consumption?from=2026-02-31")
    assert response.status_code == 400
    assert "valid calendar date" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_consumption_empty_readings(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify empty readings array returns 200 with reading_count=0."""
    mock_portal.get("/portal/meters/J100000/energy").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    response = await app_client.get("/api/v1/meters/J100000/consumption")
    assert response.status_code == 200
    data = response.json()
    assert data["reading_count"] == 0
    assert data["readings"] == []

