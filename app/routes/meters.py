"""Meter collection, meter details, and consumption history endpoints."""

from datetime import datetime
import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.client import UrjaPortalClient
from app.dependencies import get_portal_client
from app.exceptions import (
    PortalNotFoundError,
    PortalParseError,
    PortalRateLimitError,
    PortalSessionExpiredError,
    PortalTimeoutError,
    PortalUpstreamError,
)
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meters", tags=["Meters"])

METER_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def validate_meter_id(meter_id: str) -> str:
    """Validate meter identifier format preventing path traversal or malformed paths."""
    clean_id = meter_id.strip()
    if not clean_id or not METER_ID_REGEX.match(clean_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid meter ID format. Identifier must be alphanumeric (1-64 chars) with optional dashes or dots."
        )
    return clean_id


@router.get(
    "",
    response_model=MeterListResponse,
    summary="List smart meters",
    description="Retrieve a normalized collection of meters from the legacy portal. Supports search queries and exact limit/offset pagination across upstream 20-item page boundaries."
)
async def list_meters(
    q: Optional[str] = Query(default="", description="Filter by meter ID, serial number, or make"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of meters to return per page"),
    offset: int = Query(default=0, ge=0, description="Offset index for pagination"),
    client: UrjaPortalClient = Depends(get_portal_client),
) -> MeterListResponse:
    """Retrieve normalized meters list from upstream portal with exact slice pagination."""
    offset_val = offset if isinstance(offset, int) else 0
    limit_val = limit if isinstance(limit, int) else 20
    query_str = q if isinstance(q, str) else ""

    if offset_val < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'offset' must be a non-negative integer."
        )
    if limit_val < 1 or limit_val > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'limit' must be between 1 and 100."
        )

    page_size = 20
    first_page = (offset_val // page_size) + 1

    # Fetch initial page
    raw_first = await client.search_meters(query=query_str, page=first_page)
    total = raw_first.get("total")
    first_items = raw_first.get("data", [])

    # If collection is empty or offset is beyond total, return immediately
    if total == 0 or not first_items or (total is not None and offset_val >= total):
        return MeterListResponse(
            data=[],
            pagination=PaginationMeta(
                limit=limit_val,
                offset=offset_val,
                total=total if total is not None else 0,
                has_more=False,
            ),
        )

    all_raw = list(first_items)
    buffer_start_offset = (first_page - 1) * page_size
    needed_in_buffer = (offset_val - buffer_start_offset) + limit_val
    reached_end = len(first_items) < page_size

    # Calculate exact pages needed to satisfy the requested slice
    needed_pages = ((offset_val + limit_val - 1) // page_size) - (offset_val // page_size) + 1
    max_pages_to_fetch = min(max(needed_pages, 6), 10)  # Bound while guaranteeing coverage

    if not reached_end and len(all_raw) < needed_in_buffer:
        current_page = first_page + 1
        pages_fetched = 1

        while len(all_raw) < needed_in_buffer and pages_fetched < max_pages_to_fetch:
            if total is not None and (buffer_start_offset + len(all_raw)) >= total:
                reached_end = True
                break
            next_raw = await client.search_meters(query=query_str, page=current_page)
            next_items = next_raw.get("data", [])
            if not next_items:
                reached_end = True
                break
            all_raw.extend(next_items)
            current_page += 1
            pages_fetched += 1
            if len(next_items) < page_size:
                reached_end = True
                break

    # Extract exact requested slice from buffer
    start_in_buffer = offset_val - buffer_start_offset
    end_in_buffer = start_in_buffer + limit_val
    sliced_items = all_raw[start_in_buffer:end_in_buffer]

    normalized = [normalize_meter_summary(item) for item in sliced_items]

    # Calculate whether more items exist beyond this slice
    has_more = False
    if total is not None:
        has_more = (offset_val + len(normalized)) < total
    else:
        has_more = len(normalized) == limit_val and not reached_end

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
    clean_id = validate_meter_id(meter_id)

    # 1. Fetch SvelteKit deval data
    deval_data = None
    html_fallback = None

    try:
        deval_data = await client.get_meter_deval_data(clean_id)
    except PortalNotFoundError:
        # Strict 404 semantics: do not catch or mask
        raise
    except PortalParseError:
        # Deval parsing failed: fall back to server-rendered HTML
        logger.warning("Deval parsing failed for meter %s, attempting HTML fallback", clean_id)
        try:
            html_fallback = await client.get_meter_html(clean_id)
        except PortalNotFoundError:
            raise
        except Exception as exc:
            raise PortalParseError(f"Both devalue and HTML parsing failed for meter {clean_id}: {exc}") from exc
    except (PortalTimeoutError, PortalUpstreamError, PortalSessionExpiredError, PortalRateLimitError):
        # Propagate service unavailability errors (502, 504, 429) without masking as successful blank meters
        raise

    # 2. Fetch Geo coordinates
    geo_data = None
    try:
        geo_data = await client.get_meter_geo(clean_id)
    except (PortalTimeoutError, PortalRateLimitError, PortalUpstreamError):
        raise
    except Exception as exc:
        logger.warning("Could not retrieve geo coordinates for meter %s: %s", clean_id, exc)
        geo_data = {}

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
    clean_id = validate_meter_id(meter_id)

    if from_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parameter 'from' date must be a valid calendar date in YYYY-MM-DD format."
            )

    if to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parameter 'to' date must be a valid calendar date in YYYY-MM-DD format."
            )

    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'from' date must be less than or equal to 'to' date."
        )

    raw_readings = await client.get_meter_energy(clean_id, from_date=from_date, to_date=to_date)
    return normalize_consumption(clean_id, raw_readings)
