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
