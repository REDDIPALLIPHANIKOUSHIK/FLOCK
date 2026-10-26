"""Meter collection, meter details, and consumption history endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.client import UrjaPortalClient
from app.dependencies import get_portal_client
from app.exceptions import PortalNotFoundError
from app.models import (
    ConsumptionResponse,
    MeterDetail,
    MeterListResponse,
    PaginationMeta,
)
from app.services.meter_service import (
    normalize_consumption,
    normalize_meter_detail,
    normalize_meter_summary,
)

router = APIRouter(prefix="/meters", tags=["Meters"])


@router.get(
    "",
    response_model=MeterListResponse,
    summary="List smart meters",
    description="Retrieve a normalized collection of meters from the legacy portal. Supports search queries and pagination."
)
async def list_meters(
    q: Optional[str] = Query(default="", description="Filter by meter ID, serial number, or make"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of meters to return per page"),
    offset: int = Query(default=0, ge=0, description="Offset index for pagination"),
    client: UrjaPortalClient = Depends(get_portal_client),
) -> MeterListResponse:
    """Retrieve normalized meters list from upstream portal."""
    # Extract raw values if called directly in tests/scripts
    offset_val = offset if isinstance(offset, int) else 0
    limit_val = limit if isinstance(limit, int) else 20
    query_str = q if isinstance(q, str) else ""

    # Upstream portal paginates by page index (20 items/page)
    page = (offset_val // 20) + 1
    raw = await client.search_meters(query=query_str, page=page)

    data_items = raw.get("data", [])
    total = raw.get("total")

    normalized = [normalize_meter_summary(item) for item in data_items]

    # Calculate whether more items exist
    has_more = False
    if total is not None:
        has_more = (offset_val + len(normalized)) < total
    else:
        has_more = len(normalized) == 20

    return MeterListResponse(
        data=normalized,
        pagination=PaginationMeta(
            limit=limit_val,
            offset=offset_val,
            total=total,
            has_more=has_more,
        ),
    )


@router.get(
    "/{meter_id}",
    response_model=MeterDetail,
    summary="Get meter details",
    description="Fetch single normalized meter details including nameplate attributes, electrical hierarchy, and geographic coordinates."
)
async def get_meter(
    meter_id: str,
    client: UrjaPortalClient = Depends(get_portal_client),
) -> MeterDetail:
    """Fetch single meter by identifier with normalized nameplate and hierarchy."""
    clean_id = meter_id.strip()
    if not clean_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meter ID cannot be blank.")

    # 1. Fetch SvelteKit deval data
    deval_data = None
    html_fallback = None
    try:
        deval_data = await client.get_meter_deval_data(clean_id)
    except PortalNotFoundError:
        raise
    except Exception:
        # Fallback to HTML if deval fails
        try:
            html_fallback = await client.get_meter_html(clean_id)
        except Exception:
            pass

    # 2. Fetch Geo coordinates concurrently or sequentially
    geo_data = await client.get_meter_geo(clean_id)

    return normalize_meter_detail(
        meter_id=clean_id,
        deval_data=deval_data,
        html_fallback=html_fallback,
        geo_data=geo_data,
    )


@router.get(
    "/{meter_id}/consumption",
    response_model=ConsumptionResponse,
    summary="Get meter consumption telemetry",
    description="Retrieve 30-minute interval readings for cumulative active/apparent energy and voltage, with date range filters."
)
async def get_meter_consumption(
    meter_id: str,
    from_date: Optional[str] = Query(
        None,
        alias="from",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter readings starting from date (YYYY-MM-DD)",
        examples=["2026-06-25"]
    ),
    to_date: Optional[str] = Query(
        None,
        alias="to",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter readings ending at date (YYYY-MM-DD)",
        examples=["2026-06-26"]
    ),
    client: UrjaPortalClient = Depends(get_portal_client),
) -> ConsumptionResponse:
    """Retrieve interval consumption history for the specified meter."""
    clean_id = meter_id.strip()
    if not clean_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meter ID cannot be blank.")

    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'from' date must be less than or equal to 'to' date."
        )

    raw_readings = await client.get_meter_energy(clean_id, from_date=from_date, to_date=to_date)
    return normalize_consumption(clean_id, raw_readings)
