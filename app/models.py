"""Normalized Pydantic request and response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code", example="UPSTREAM_TIMEOUT")
    message: str = Field(..., description="Human-readable explanation of error", example="The meter portal did not respond in time.")
    request_id: Optional[str] = Field(None, description="Unique trace identifier for request tracking", example="req_01h8x9p")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationMeta(BaseModel):
    limit: int = Field(..., description="Maximum items requested or returned", example=20)
    offset: int = Field(..., description="Zero-based offset into collection", example=0)
    total: Optional[int] = Field(None, description="Total items available upstream, or null if unknown", example=403)
    has_more: bool = Field(..., description="True if subsequent pages exist", example=True)


class MeterSummary(BaseModel):
    id: str = Field(..., description="Unique meter identifier", example="J100000")
    serial_number: str = Field(..., description="Hardware manufacturer serial number", example="SE33962")
    make: Optional[str] = Field(None, description="Manufacturer name", example="HPL")
    phase_type: Optional[str] = Field(None, description="Electrical phase type (single or three)", example="single")
    status: Optional[str] = Field(None, description="Installation or operational status", example="Installed")
    distribution_transformer_code: Optional[str] = Field(None, description="Linked Distribution Transformer code", example="DT-001")


class MeterListResponse(BaseModel):
    data: List[MeterSummary]
    pagination: PaginationMeta


class MeterLocation(BaseModel):
    latitude: Optional[float] = Field(None, description="Geographic latitude coordinate", example=26.938961)
    longitude: Optional[float] = Field(None, description="Geographic longitude coordinate", example=75.830957)


class MeterHierarchyInfo(BaseModel):
    zone: Optional[str] = Field(None, description="Administrative Zone", example="Jaipur Zone 1 (Z-01)")
    circle: Optional[str] = Field(None, description="Operational Circle", example="Circle 1 (C-01)")
    division: Optional[str] = Field(None, description="Division", example="Division 1 (D-01)")
    subdivision: Optional[str] = Field(None, description="Subdivision", example="Subdivision 1 (SD-01)")
    substation: Optional[str] = Field(None, description="Substation code/name", example="Substation 1 (SS-01)")
    feeder: Optional[str] = Field(None, description="Feeder code/name", example="Feeder 1 (F-001)")
    distribution_transformer: Optional[str] = Field(None, description="Distribution Transformer code/name", example="Malviya Nagar DT 1 (DT-001)")


class MeterDetail(BaseModel):
    id: str = Field(..., description="Unique meter identifier", example="J100000")
    serial_number: str = Field(..., description="Manufacturer hardware serial number", example="SE33962")
    make: Optional[str] = Field(None, description="Manufacturer make", example="HPL")
    phase_type: Optional[str] = Field(None, description="Single or three phase", example="single")
    status: Optional[str] = Field(None, description="Operational / installation status", example="Installed")
    installation_type: Optional[str] = Field(None, description="Whole Current or CT Operated", example="Whole Current")
    build_type: Optional[str] = Field(None, description="Upstream schema build generation (legacy, v2)", example="legacy")
    distribution_transformer_code: Optional[str] = Field(None, description="Distribution transformer identifier", example="DT-001")
    location: Optional[MeterLocation] = None
    hierarchy: Optional[MeterHierarchyInfo] = None
    attributes: Dict[str, str] = Field(default_factory=dict, description="Normalized source parameters and nameplate values")


class ConsumptionRecord(BaseModel):
    timestamp: datetime = Field(..., description="ISO 8601 formatted datetime of meter register reading", example="2026-06-24T00:00:00")
    raw_timestamp: str = Field(..., description="Exact string timestamp as reported upstream", example="24/06/2026 00:00")
    kwh: Optional[float] = Field(None, description="Active energy reading in kilowatt-hours (cumulative)", example=48439.16)
    kvah: Optional[float] = Field(None, description="Apparent energy reading in kilovolt-ampere-hours (cumulative)", example=52314.29)
    voltage_r: Optional[float] = Field(None, description="R-phase voltage in Volts", example=229.0)


class ConsumptionResponse(BaseModel):
    meter_id: str = Field(..., description="Meter identifier", example="J100000")
    reading_count: int = Field(..., description="Number of interval readings returned", example=48)
    unit_kwh: str = Field("kWh (cumulative)", description="Active energy register units")
    unit_kvah: str = Field("kVAh (cumulative)", description="Apparent energy register units")
    unit_voltage: str = Field("V (R-phase)", description="Voltage measurement units")
    readings: List[ConsumptionRecord]


class HierarchyNode(BaseModel):
    id: str = Field(..., description="Node unique code or identifier", example="DT-001")
    name: str = Field(..., description="Node label or station name", example="Malviya Nagar DT 1")
    type: str = Field(..., description="Topology level: distribution_transformer, feeder, substation, zone, meter", example="distribution_transformer")
    parent_id: Optional[str] = Field(None, description="Identifier of parent node in grid topology", example="F-001")
    children: List[HierarchyNode] = Field(default_factory=list, description="Child nodes in topology")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Capacity, phase, or technical telemetry")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HierarchyResponse(BaseModel):
    is_partial: bool = Field(..., description="Flag indicating whether hierarchy graph is partial or complete", example=False)
    summary: str = Field(..., description="Description of the topology graph scope", example="Distribution Transformers linked by Feeder")
    total_distribution_transformers: int = Field(..., description="Total DT nodes discovered", example=40)
    nodes: List[HierarchyNode]


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status", example="healthy")
    app_name: str = Field(..., example="Urja Meter Ops API")
    version: str = Field(..., example="1.0.0")
    environment: str = Field(..., example="development")
    upstream: Dict[str, Any] = Field(..., description="Connectivity check to upstream meter portal")


class LoginRequest(BaseModel):
    email: Optional[str] = Field(None, description="Optional portal email override", example="operator@urja.local")
    password: Optional[str] = Field(None, description="Optional portal password override", example="your-password")


class AuthResponse(BaseModel):
    authenticated: bool = Field(..., description="Whether authenticated upstream session is active", example=True)
    message: str = Field(..., example="Authenticated successfully with upstream portal.")
    session_active: bool = Field(..., example=True)
