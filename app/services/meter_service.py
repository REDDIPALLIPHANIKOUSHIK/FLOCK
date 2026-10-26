"""Normalization and business logic service for Urja Meter Ops."""

from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from app.exceptions import PortalParseError
from app.models import (
    ConsumptionRecord,
    ConsumptionResponse,
    HierarchyNode,
    HierarchyResponse,
    MeterDetail,
    MeterHierarchyInfo,
    MeterLocation,
    MeterSummary,
    PaginationMeta,
)

logger = logging.getLogger(__name__)


def decode_sveltekit_deval(deval_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Decodes SvelteKit devalue serialized format from /meters/{id}/__data.json.
    Reconstructs the graph of referenced objects and strings.
    """
    nodes = deval_json.get("nodes", [])
    data_node = None
    for n in nodes:
        if n and n.get("type") == "data" and "data" in n:
            raw_data = n["data"]
            if isinstance(raw_data, list) and len(raw_data) > 0 and isinstance(raw_data[0], dict):
                if "meterId" in raw_data[0]:
                    data_node = raw_data
                    break

    if not data_node:
        return None

    def resolve(idx: Any) -> Any:
        if not isinstance(idx, int) or idx < 0 or idx >= len(data_node):
            return idx
        val = data_node[idx]
        if isinstance(val, dict):
            return {k: resolve(v) for k, v in val.items()}
        if isinstance(val, list):
            return [resolve(v) for v in val]
        return val

    root = data_node[0]
    meter_id = resolve(root.get("meterId"))
    detail_raw = resolve(root.get("detail"))
    hierarchy_raw = resolve(root.get("hierarchy"))

    attributes: Dict[str, str] = {}
    installation_type: Optional[str] = None
    build_type: str = "legacy"

    if isinstance(detail_raw, dict):
        # Case A: Build v2 with classData JSON string
        if "classData" in detail_raw:
            build_type = "v2"
            try:
                parsed = json.loads(detail_raw["classData"])
                installed = parsed.get("installed_meter", {})
                for k, v in installed.items():
                    attributes[k] = str(v).strip()
                    if k.lower() == "installationtype":
                        installation_type = str(v).strip()
            except Exception as e:
                logger.warning("Could not parse classData JSON in deval: %s", e)
        # Case B: Build legacy with list of parameterName / parameterValue pairs
        elif "data" in detail_raw and isinstance(detail_raw["data"], list):
            build_type = "legacy"
            for item in detail_raw["data"]:
                if isinstance(item, dict):
                    name = item.get("parameterName")
                    val = item.get("parameterValue")
                    if name:
                        attributes[str(name).strip()] = str(val).strip() if val is not None else ""
                        if str(name).strip().lower() == "installation type":
                            installation_type = str(val).strip()

    hierarchy_dict: Dict[str, str] = {}
    if isinstance(hierarchy_raw, dict):
        for k, v in hierarchy_raw.items():
            if isinstance(v, str):
                hierarchy_dict[k.strip()] = v.strip()

    return {
        "meter_id": str(meter_id).strip() if meter_id else None,
        "attributes": attributes,
        "hierarchy": hierarchy_dict,
        "installation_type": installation_type,
        "build_type": build_type,
    }


def parse_meter_html(html_text: str) -> Dict[str, Any]:
    """
    Parses meter nameplate table and breadcrumb hierarchy from HTML SSR response.
    Acts as a verified fallback when __data.json is not directly consumed.
    """
    soup = BeautifulSoup(html_text, "html.parser")

    # Extract Breadcrumbs / Hierarchy
    nav = soup.find("nav", class_=lambda c: c and "flex-wrap" in c)
    hierarchy_items: List[str] = []
    if nav:
        for span in nav.find_all("span", recursive=False):
            txt = span.get_text(strip=True)
            if txt and txt != "›":
                hierarchy_items.append(txt)

    # Extract Nameplate dl
    attributes: Dict[str, str] = {}
    dl = soup.find("dl")
    if dl:
        for row in dl.find_all("div"):
            dt = row.find("dt")
            dd = row.find("dd")
            if dt and dd:
                attributes[dt.get_text(strip=True)] = dd.get_text(strip=True)

    return {
        "hierarchy_items": hierarchy_items,
        "attributes": attributes,
    }


def normalize_meter_summary(raw: Dict[str, Any]) -> MeterSummary:
    """Normalize raw meter record from search endpoint."""
    return MeterSummary(
        id=str(raw.get("meterId", "")).strip(),
        serial_number=str(raw.get("serialNo", "")).strip(),
        make=raw.get("make") or None,
        phase_type=raw.get("phaseType") or None,
        status=raw.get("installStatus") or None,
        distribution_transformer_code=raw.get("dtCode") or None,
    )


def normalize_meter_detail(
    meter_id: str,
    deval_data: Optional[Dict[str, Any]] = None,
    html_fallback: Optional[str] = None,
    geo_data: Optional[Dict[str, Any]] = None,
) -> MeterDetail:
    """
    Merge deval data, HTML fallback, and geo coordinates into a single validated MeterDetail model.
    """
    attributes: Dict[str, str] = {}
    hierarchy_dict: Dict[str, str] = {}
    installation_type: Optional[str] = None
    build_type: str = "legacy"

    if deval_data:
        decoded = decode_sveltekit_deval(deval_data)
        if decoded:
            attributes.update(decoded.get("attributes", {}))
            hierarchy_dict.update(decoded.get("hierarchy", {}))
            installation_type = decoded.get("installation_type")
            build_type = decoded.get("build_type", "legacy")

    # If attributes are empty, try HTML parsing fallback
    if not attributes and html_fallback:
        parsed_html = parse_meter_html(html_fallback)
        attributes.update(parsed_html.get("attributes", {}))

    # Extract serial number and make from attributes if available
    serial_no = (
        attributes.get("Serial No")
        or attributes.get("SerialNo")
        or attributes.get("serial_number")
        or "UNKNOWN"
    )
    make = attributes.get("Make") or attributes.get("make")
    phase_type = attributes.get("Phase Type") or attributes.get("PhaseType") or attributes.get("phase_type")
    status = (
        attributes.get("Installation Status")
        or attributes.get("InstallationStatus")
        or attributes.get("install_status")
    )
    if not installation_type:
        installation_type = (
            attributes.get("Installation Type")
            or attributes.get("InstallationType")
        )

    # Location
    location = None
    if geo_data:
        try:
            lat = float(geo_data.get("latitude") or geo_data.get("lat"))
            lng = float(geo_data.get("longitude") or geo_data.get("lng"))
            location = MeterLocation(latitude=lat, longitude=lng)
        except (ValueError, TypeError):
            location = None

    # Hierarchy Info
    hierarchy = None
    if hierarchy_dict:
        hierarchy = MeterHierarchyInfo(
            zone=hierarchy_dict.get("Zone"),
            circle=hierarchy_dict.get("Circle"),
            division=hierarchy_dict.get("Division"),
            subdivision=hierarchy_dict.get("Subdivision"),
            substation=hierarchy_dict.get("Sub Station") or hierarchy_dict.get("Substation"),
            feeder=hierarchy_dict.get("Feeder"),
            distribution_transformer=hierarchy_dict.get("DT"),
        )

    # Extract DT Code from DT field e.g. 'Malviya Nagar DT 1 (DT-001)'
    dt_code = None
    dt_str = hierarchy_dict.get("DT", "")
    dt_match = re.search(r'\((DT-[^)]+)\)', dt_str)
    if dt_match:
        dt_code = dt_match.group(1)

    return MeterDetail(
        id=meter_id,
        serial_number=serial_no,
        make=make,
        phase_type=phase_type,
        status=status,
        installation_type=installation_type,
        build_type=build_type,
        distribution_transformer_code=dt_code,
        location=location,
        hierarchy=hierarchy,
        attributes=attributes,
    )


def normalize_consumption(meter_id: str, raw_readings: List[Dict[str, Any]]) -> ConsumptionResponse:
    """
    Parses and normalizes raw energy readings.
    Timestamps in source: 'DD/MM/YYYY HH:MM'
    Values: cumulative kWh, cumulative kVAh, and R-phase voltage.
    """
    records: List[ConsumptionRecord] = []

    for item in raw_readings:
        raw_ts = item.get("timestamp", "").strip()
        if not raw_ts:
            continue

        try:
            dt = datetime.strptime(raw_ts, "%d/%m/%Y %H:%M")
        except ValueError:
            try:
                dt = datetime.fromisoformat(raw_ts)
            except ValueError:
                # Unable to safely interpret timestamp, skip malformed record
                continue

        def safe_float(val: Any) -> Optional[float]:
            if val is None or val == "" or val == "—":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        kwh = safe_float(item.get("kwh"))
        kvah = safe_float(item.get("kvah"))
        volt_r = safe_float(item.get("voltR") or item.get("volt_r"))

        records.append(
            ConsumptionRecord(
                timestamp=dt,
                raw_timestamp=raw_ts,
                kwh=kwh,
                kvah=kvah,
                voltage_r=volt_r,
            )
        )

    # Sort chronological by datetime
    records.sort(key=lambda r: r.timestamp)

    return ConsumptionResponse(
        meter_id=meter_id,
        reading_count=len(records),
        readings=records,
    )


def build_hierarchy_tree(dts: List[Dict[str, Any]]) -> HierarchyResponse:
    """
    Reconstructs electrical grid hierarchy from Distribution Transformer records.
    Groups Distribution Transformers under their respective Feeders.
    Guarantees acyclic graph, deduplicates DT codes, and handles missing fields.
    """
    if not dts:
        return HierarchyResponse(
            is_partial=False,
            summary="Distribution Transformer topology mapped to Feeders",
            total_distribution_transformers=0,
            nodes=[],
        )

    feeders: Dict[str, List[HierarchyNode]] = {}
    seen_dt_codes = set()
    valid_dt_count = 0

    for dt in dts:
        if not isinstance(dt, dict):
            continue
        dt_code = str(dt.get("code") or "").strip()
        if not dt_code or dt_code in seen_dt_codes:
            # Skip invalid or duplicate DT nodes
            continue
        seen_dt_codes.add(dt_code)
        valid_dt_count += 1

        dt_name = str(dt.get("name") or dt_code).strip()
        feeder_code = str(dt.get("feederCode") or "UNKNOWN_FEEDER").strip()
        capacity = dt.get("capacityKva")

        dt_node = HierarchyNode(
            id=dt_code,
            name=dt_name,
            type="distribution_transformer",
            parent_id=feeder_code,
            children=[],
            metadata={"capacity_kva": capacity} if capacity is not None else {},
        )

        feeders.setdefault(feeder_code, []).append(dt_node)

    root_nodes: List[HierarchyNode] = []
    for feeder_code, child_dts in sorted(feeders.items()):
        child_dts.sort(key=lambda x: x.id)
        feeder_node = HierarchyNode(
            id=feeder_code,
            name=f"Feeder {feeder_code}" if feeder_code != "UNKNOWN_FEEDER" else "Unassigned Feeder",
            type="feeder",
            parent_id=None,
            children=child_dts,
            metadata={"dt_count": len(child_dts)},
        )
        root_nodes.append(feeder_node)

    return HierarchyResponse(
        is_partial=False,
        summary="Distribution Transformer topology mapped to Feeders",
        total_distribution_transformers=valid_dt_count,
        nodes=root_nodes,
    )
