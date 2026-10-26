"""Hierarchy endpoint for electrical network topology."""

from fastapi import APIRouter, Depends
from app.client import UrjaPortalClient
from app.dependencies import get_portal_client
from app.models import HierarchyResponse
from app.services.meter_service import build_hierarchy_tree

router = APIRouter(prefix="/hierarchy", tags=["Hierarchy"])


@router.get(
    "",
    response_model=HierarchyResponse,
    summary="Get electrical grid distribution hierarchy",
    description="Retrieve the reconstructed grid hierarchy organizing Distribution Transformers under their respective Feeders."
)
async def get_hierarchy(
    client: UrjaPortalClient = Depends(get_portal_client),
) -> HierarchyResponse:
    """Reconstruct grid hierarchy from upstream Distribution Transformers."""
    all_dts = []
    page = 1
    while True:
        resp = await client.get_distribution_transformers(page=page)
        items = resp.get("data", [])
        if not items:
            break
        all_dts.extend(items)
        total = resp.get("total", len(all_dts))
        if len(all_dts) >= total or len(items) < 20:
            break
        page += 1

    return build_hierarchy_tree(all_dts)
