"""Tests for grid distribution hierarchy reconstruction."""

import pytest
import httpx
import respx

from app.services.meter_service import build_hierarchy_tree
from tests.fixtures.portal_responses import DTS_RESPONSE


@pytest.mark.asyncio
async def test_get_hierarchy(app_client: httpx.AsyncClient):
    """Verify hierarchy endpoint reconstructs tree topology of Feeders and DTs."""
    response = await app_client.get("/api/v1/hierarchy")
    assert response.status_code == 200
    data = response.json()

    assert data["is_partial"] is False
    assert data["total_distribution_transformers"] == 3
    assert len(data["nodes"]) == 2  # Feeder F-001 and Feeder F-002

    feeder_f001 = next(n for n in data["nodes"] if n["id"] == "F-001")
    assert len(feeder_f001["children"]) == 2  # DT-001 and DT-003
    assert feeder_f001["type"] == "feeder"

    feeder_f002 = next(n for n in data["nodes"] if n["id"] == "F-002")
    assert len(feeder_f002["children"]) == 1  # DT-002


def test_build_hierarchy_tree_edge_cases():
    """Verify hierarchy reconstruction handles missing feeder codes or capacities."""
    raw = [
        {"code": "DT-100", "name": "Isolated DT", "capacityKva": None},
        {"code": "DT-101", "name": "Feeder DT", "feederCode": "F-999", "capacityKva": 500},
    ]
    tree = build_hierarchy_tree(raw)
    assert tree.total_distribution_transformers == 2
    nodes = {n.id: n for n in tree.nodes}
    assert "UNKNOWN_FEEDER" in nodes
    assert "F-999" in nodes
    assert nodes["F-999"].children[0].metadata["capacity_kva"] == 500


def test_build_hierarchy_deduplicates_and_handles_empty():
    """Verify hierarchy deduplicates duplicate DT entries and handles empty lists."""
    # Empty collection
    assert build_hierarchy_tree([]).total_distribution_transformers == 0
    assert build_hierarchy_tree([]).nodes == []

    # Duplicates and blanks
    raw = [
        {"code": "DT-001", "name": "DT 1", "feederCode": "F-1"},
        {"code": "DT-001", "name": "Duplicate DT 1", "feederCode": "F-1"},
        {"code": "", "name": "Blank Code", "feederCode": "F-1"},
        {"code": "DT-002", "name": "DT 2", "feederCode": "F-1"},
    ]
    tree = build_hierarchy_tree(raw)
    assert tree.total_distribution_transformers == 2
    feeder_node = tree.nodes[0]
    assert len(feeder_node.children) == 2
    assert [c.id for c in feeder_node.children] == ["DT-001", "DT-002"]


@pytest.mark.asyncio
async def test_hierarchy_multi_page_data(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify hierarchy endpoint fetches across multiple upstream pages."""
    page_1 = [
        {"code": f"DT-{i:03d}", "name": f"DT {i}", "feederCode": "F-01", "capacityKva": 100}
        for i in range(1, 21)
    ]
    page_2 = [
        {"code": f"DT-{i:03d}", "name": f"DT {i}", "feederCode": "F-02", "capacityKva": 200}
        for i in range(21, 31)
    ]

    def dts_side_effect(request: httpx.Request):
        url = str(request.url)
        if "page=2" in url:
            return httpx.Response(200, json={"data": page_2, "total": 30})
        return httpx.Response(200, json={"data": page_1, "total": 30})

    mock_portal.get("/portal/dts").mock(side_effect=dts_side_effect)

    response = await app_client.get("/api/v1/hierarchy")
    assert response.status_code == 200
    data = response.json()
    assert data["total_distribution_transformers"] == 30
    assert len(data["nodes"]) == 2  # Feeders F-01 and F-02
    feeder_1 = next(n for n in data["nodes"] if n["id"] == "F-01")
    assert len(feeder_1["children"]) == 20
    feeder_2 = next(n for n in data["nodes"] if n["id"] == "F-02")
    assert len(feeder_2["children"]) == 10


@pytest.mark.asyncio
async def test_hierarchy_upstream_failure_during_pagination(app_client: httpx.AsyncClient, mock_portal: respx.MockRouter):
    """Verify upstream failure on page 2 returns 502 rather than an incomplete partial tree."""
    page_1 = [
        {"code": f"DT-{i:03d}", "name": f"DT {i}", "feederCode": "F-01"}
        for i in range(1, 21)
    ]

    def dts_side_effect(request: httpx.Request):
        url = str(request.url)
        if "page=2" in url:
            return httpx.Response(500, text="Internal Server Error on page 2")
        return httpx.Response(200, json={"data": page_1, "total": 40})

    mock_portal.get("/portal/dts").mock(side_effect=dts_side_effect)

    response = await app_client.get("/api/v1/hierarchy")
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_ERROR"

