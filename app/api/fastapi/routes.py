"""HTTP endpoints: /health, /route, /graph."""

from __future__ import annotations

import io
import logging
import math
import struct

import httpx
import numpy as np
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from app.api import state

log = logging.getLogger(__name__)

router = APIRouter()

_OSRM_URL      = "http://router.project-osrm.org/route/v1/driving"
_OSRM_TIMEOUT  = 5.0


# ── /health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    return {
        "status":               "ok",
        "onnx":                 str(state.ONNX_PATH),
        "onnx_exists":          state.ONNX_PATH.exists(),
        "road_graph_exists":    state.ROAD_GRAPH.exists(),
        "offline_router_ready": state.road_router is not None,
    }


# ── /route ────────────────────────────────────────────────────────────────────

@router.get("/route")
async def route(
    origin_lat: float = Query(...),
    origin_lon: float = Query(...),
    dest_lat:   float = Query(...),
    dest_lon:   float = Query(...),
) -> JSONResponse:
    """Return a road-snapped route polyline + basic steps.

    Strategy (in order):
      1. OSRM public API (5 s timeout) — full turn-by-turn
      2. Local offline A* on downloaded road graph — polyline only
      3. Straight line — last resort (no road graph available)
    """
    # ── 1. Try OSRM ───────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=_OSRM_TIMEOUT) as client:
            url = (
                f"{_OSRM_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
                "?overview=full&geometries=geojson&steps=true"
            )
            resp = await client.get(url, headers={"User-Agent": "SIH2026-IDR/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    r0       = data["routes"][0]
                    coords   = r0["geometry"]["coordinates"]
                    polyline = [[c[1], c[0]] for c in coords]   # [lat,lon]
                    return JSONResponse({
                        "source":     "osrm",
                        "polyline":   polyline,
                        "steps":      _parse_osrm_steps(r0),
                        "distance_m": r0["distance"],
                        "duration_s": r0["duration"],
                    })
    except Exception as exc:
        log.info("OSRM unavailable (%s) — falling back to offline router", exc)

    # ── 2. Offline A* ─────────────────────────────────────────────────────
    rr = state.road_router
    if rr is not None:
        ll_path = rr.route_latlon(origin_lat, origin_lon, dest_lat, dest_lon)
        if ll_path is not None:
            polyline = [[lat, lon] for lat, lon in ll_path]
            dist_m   = _path_distance_m(ll_path)
            return JSONResponse({
                "source":     "offline",
                "polyline":   polyline,
                "steps":      _straight_steps(origin_lat, origin_lon, dest_lat, dest_lon),
                "distance_m": dist_m,
                "duration_s": dist_m / 8.33,
            })
        log.warning("Offline router found no path — falling back to straight line")
    else:
        log.info("Offline router not ready yet — returning straight line")

    # ── 3. Straight line ──────────────────────────────────────────────────
    dist_m = _haversine_m(origin_lat, origin_lon, dest_lat, dest_lon)
    return JSONResponse({
        "source":     "straight",
        "polyline":   [[origin_lat, origin_lon], [dest_lat, dest_lon]],
        "steps":      _straight_steps(origin_lat, origin_lon, dest_lat, dest_lon),
        "distance_m": dist_m,
        "duration_s": dist_m / 8.33,
    })


# ── /graph ────────────────────────────────────────────────────────────────────

@router.get("/graph")
async def export_graph(
    radius_km: float = Query(default=10.0, ge=1.0, le=30.0),
) -> Response:
    """Export a radius-cropped routing graph as compact binary for on-device A*.

    Reads nodes and edges directly from the SQLite road graph — no in-memory
    arrays required. Only nodes within `radius_km` of the graph origin are
    exported, keeping the download small.

    Binary format (little-endian):
      [8 bytes] float64  lat0
      [8 bytes] float64  lon0
      [4 bytes] uint32   N  (number of nodes in cropped graph)
      [N*8 bytes]        float32 east_m, float32 north_m  per node
      [4 bytes] uint32   E  (total directed edge records)
      [E*12 bytes]       uint32 from_node, uint32 to_node, float32 cost_m  per edge
    Returns 503 if the offline router is not ready yet.
    """
    import sqlite3 as _sqlite3

    rr = state.road_router
    if rr is None:
        return Response(status_code=503, content=b"router not ready")

    radius_m = radius_km * 1000.0
    con: _sqlite3.Connection = rr._con  # reuse the open read-only connection

    # ── Load nodes within radius ──────────────────────────────────────────
    # nodes table: id INTEGER, x REAL (east_m), y REAL (north_m)
    rows = con.execute(
        "SELECT id, x, y FROM nodes WHERE (x * x + y * y) <= ?",
        (radius_m ** 2,),
    ).fetchall()

    if not rows:
        return Response(status_code=503, content=b"no nodes in radius")

    # Map old node id → new sequential index
    old_to_new: dict[int, int] = {}
    node_x: list[float] = []
    node_y: list[float] = []
    for new_idx, (old_id, x, y) in enumerate(rows):
        old_to_new[old_id] = new_idx
        node_x.append(x)
        node_y.append(y)
    N = len(node_x)

    # ── Load edges — fetch all, filter in Python to avoid SQLite var limit ─
    # edges table: src INTEGER, dst INTEGER, cost REAL
    edge_rows = con.execute("SELECT src, dst, cost FROM edges").fetchall()

    # ── Serialise ─────────────────────────────────────────────────────────
    buf      = io.BytesIO()
    edge_buf = io.BytesIO()

    buf.write(struct.pack("<ddI", rr._lat0, rr._lon0, N))
    for x, y in zip(node_x, node_y):
        # _recentre converts from graph-origin ENU to EKF-origin ENU
        re_e, re_n = rr._recentre(x, y)
        buf.write(struct.pack("<ff", re_e, re_n))

    E = 0
    for frm, to, cost in edge_rows:
        nf = old_to_new.get(frm, -1)
        nt = old_to_new.get(to,  -1)
        if nf < 0 or nt < 0:
            continue
        edge_buf.write(struct.pack("<IIf", nf, nt, float(cost)))
        E += 1

    buf.write(struct.pack("<I", E))
    buf.write(edge_buf.getvalue())
    data = buf.getvalue()

    log.info("/graph: serving %.1f MB (%d nodes, %d edges, radius %.0f km)",
             len(data) / 1e6, N, E, radius_km)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=road_graph.bin"},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_osrm_steps(route_obj: dict) -> list[dict]:
    steps = []
    for leg in route_obj.get("legs", []):
        for s in leg.get("steps", []):
            maneuver = s.get("maneuver", {})
            loc = maneuver.get("location", [0, 0])
            steps.append({
                "instruction": _build_instruction(
                    maneuver.get("type", ""),
                    maneuver.get("modifier", ""),
                    s.get("name", ""),
                ),
                "distance_m":    s.get("distance", 0),
                "duration_s":    s.get("duration", 0),
                "bearing_after": maneuver.get("bearing_after", 0),
                "lat":           loc[1],
                "lon":           loc[0],
            })
    return steps


def _straight_steps(olat: float, olon: float, dlat: float, dlon: float) -> list[dict]:
    dist = _haversine_m(olat, olon, dlat, dlon)
    bear = _bearing_deg(olat, olon, dlat, dlon)
    return [
        {"instruction": "Head towards destination", "distance_m": dist,
         "duration_s": dist / 8.33, "bearing_after": bear, "lat": olat, "lon": olon},
        {"instruction": "Arrive at destination", "distance_m": 0,
         "duration_s": 0, "bearing_after": bear, "lat": dlat, "lon": dlon},
    ]


def _build_instruction(type_: str, modifier: str, name: str) -> str:
    road = f" onto {name}" if name else ""
    return {
        "depart":     f"Head{road or ' along route'}",
        "arrive":     "Arrive at destination",
        "turn":       f"{modifier.capitalize()} turn{road}",
        "new name":   f"Continue{road}",
        "merge":      f"Merge{road}",
        "on ramp":    f"Take the ramp{road}",
        "off ramp":   f"Take the exit{road}",
        "fork":       f"Keep {'left' if 'left' in modifier else 'right'}{road}",
        "roundabout": f"Enter the roundabout{road}",
        "rotary":     f"Enter the rotary{road}",
    }.get(type_, f"Continue{road}")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r   = 6_371_000.0
    dl  = math.radians(lat2 - lat1)
    dlo = math.radians(lon2 - lon1)
    a   = (math.sin(dl / 2) ** 2
           + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
           * math.sin(dlo / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dlo = math.radians(lon2 - lon1)
    y   = math.sin(dlo) * math.cos(la2)
    x   = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _path_distance_m(ll_path: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(ll_path) - 1):
        a, b = ll_path[i], ll_path[i + 1]
        total += _haversine_m(a[0], a[1], b[0], b[1])
    return total
