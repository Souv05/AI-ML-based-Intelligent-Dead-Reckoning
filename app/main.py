"""FastAPI navigation server.

WebSocket endpoint: ws://<host>:8000/ws/navigation

Phone -> server  (JSON, each IMU tick ~50 Hz):
{
  "acc_x": float,   "acc_y": float,   "acc_z": float,    // m/s^2
  "gyro_x": float,  "gyro_y": float,  "gyro_z": float,   // rad/s
  "mag_x": float,   "mag_y": float,   "mag_z": float,    // uT
  "roll": float,    "pitch": float,   "yaw": float,      // degrees
  "lat": float,     "lon": float,
  "heading_deg": float,
  "gnss_speed_ms": float,
  "gnss_accuracy_m": float,
  "gnss_valid": bool,
  "t_ms": int
}

Server -> phone  (JSON, ~10 Hz):
{
  "lat": float, "lon": float,
  "east_m": float, "north_m": float,
  "speed_fwd": float,
  "heading_deg": float,
  "gru_speed": float,
  "mode": "GNSS_AIDED" | "DR_ACTIVE" | "GNSS_REACQUIRE",
  "gnss_valid": bool,
  "gnss_health": "OK" | "DEGRADED" | "OUTAGE",
  "position_std_m": float,
  "sample_index": int
}
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import numpy as np
from typing import Optional

import httpx
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

import concurrent.futures
import threading

from app.ekf_fusion import EKFFusion
from app.gru_engine import GRUEngine
from app.imu_filter import ImuFilter
from app.map_matcher import MapMatcher
from app.router import RoadRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_ROOT        = Path(__file__).parent.parent
_MODELS      = _ROOT / "models"
_ONNX        = _MODELS / "exported" / "onnx" / "gru_v2.onnx"
_META        = _MODELS / "gru" / "gru_v2_metadata.json"
_ROAD_GRAPH  = _ROOT / "configs" / "road_graph.sqlite"

_PUBLISH_DT = 1.0 / 10   # 10 Hz output rate

app = FastAPI(title="Dead-Reckoning Navigation Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
_OSRM_TIMEOUT_S = 5.0

# Shared offline router — built once after EKF acquires its GNSS origin.
# Accessed from multiple coroutines; assignment is atomic under the GIL.
_road_router: Optional[RoadRouter] = None
_router_loading = False


@app.on_event("startup")
async def _startup() -> None:
    """Pre-build the offline router at startup using the road graph's own origin.

    This ensures offline routing is available even before any WebSocket client
    connects (and before a GNSS fix is acquired).  The SQLite-backed router
    opens the database file without loading it into RAM, so startup is fast.
    """
    if _ROAD_GRAPH.exists():
        import sqlite3 as _sqlite3
        try:
            _con = _sqlite3.connect(f"file:{_ROAD_GRAPH}?mode=ro", uri=True)
            _lat0 = float(_con.execute("SELECT value FROM meta WHERE key='lat0'").fetchone()[0])
            _lon0 = float(_con.execute("SELECT value FROM meta WHERE key='lon0'").fetchone()[0])
            _con.close()
        except Exception as _exc:
            log.warning("startup: could not read road graph origin: %s — skipping pre-build", _exc)
            return
        global _router_loading
        _router_loading = True
        import threading as _threading
        _threading.Thread(
            target=_build_road_router,
            args=(_lat0, _lon0),
            daemon=True,
            name="road-router-startup",
        ).start()
        log.info("startup: offline router build started (origin %.4f, %.4f)", _lat0, _lon0)
    else:
        log.warning("startup: road_graph.sqlite not found — offline routing unavailable")


def _build_road_router(lat0: float, lon0: float) -> None:
    global _road_router, _router_loading
    try:
        log.info("Building offline road router in background …")
        r = RoadRouter(_ROAD_GRAPH, lat0, lon0)
        _road_router = r
        log.info("Offline road router ready")
    except Exception as exc:
        log.warning("Offline road router failed: %s", exc)
    finally:
        _router_loading = False


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "onnx": str(_ONNX),
        "onnx_exists": _ONNX.exists(),
        "road_graph_exists": _ROAD_GRAPH.exists(),
        "offline_router_ready": _road_router is not None,
    }


@app.get("/route")
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
        async with httpx.AsyncClient(timeout=_OSRM_TIMEOUT_S) as client:
            url = (
                f"{_OSRM_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
                "?overview=full&geometries=geojson&steps=true"
            )
            resp = await client.get(url, headers={"User-Agent": "SIH2026-IDR/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    r0   = data["routes"][0]
                    coords = r0["geometry"]["coordinates"]
                    polyline = [[c[1], c[0]] for c in coords]   # [lat,lon]
                    steps = _parse_osrm_steps(r0)
                    return JSONResponse({
                        "source":       "osrm",
                        "polyline":     polyline,
                        "steps":        steps,
                        "distance_m":   r0["distance"],
                        "duration_s":   r0["duration"],
                    })
    except Exception as exc:
        log.info("OSRM unavailable (%s) — falling back to offline router", exc)

    # ── 2. Offline A* ─────────────────────────────────────────────────────
    router = _road_router
    if router is not None:
        ll_path = router.route_latlon(origin_lat, origin_lon, dest_lat, dest_lon)
        if ll_path is not None:
            polyline = [[lat, lon] for lat, lon in ll_path]
            dist_m   = _path_distance_m(ll_path)
            return JSONResponse({
                "source":     "offline",
                "polyline":   polyline,
                "steps":      _straight_steps(origin_lat, origin_lon, dest_lat, dest_lon),
                "distance_m": dist_m,
                "duration_s": dist_m / 8.33,   # assume 30 km/h average
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


# ── Route helper functions ────────────────────────────────────────────────────

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
        "depart":   f"Head{road or ' along route'}",
        "arrive":   "Arrive at destination",
        "turn":     f"{modifier.capitalize()} turn{road}",
        "new name": f"Continue{road}",
        "merge":    f"Merge{road}",
        "on ramp":  f"Take the ramp{road}",
        "off ramp": f"Take the exit{road}",
        "fork":     f"Keep {'left' if 'left' in modifier else 'right'}{road}",
        "roundabout": f"Enter the roundabout{road}",
        "rotary":   f"Enter the rotary{road}",
    }.get(type_, f"Continue{road}")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    dl = math.radians(lat2 - lat1)
    dlo = math.radians(lon2 - lon1)
    a = math.sin(dl / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlo / 2)**2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dlo = math.radians(lon2 - lon1)
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _path_distance_m(ll_path: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(ll_path) - 1):
        a, b = ll_path[i], ll_path[i + 1]
        total += _haversine_m(a[0], a[1], b[0], b[1])
    return total


@app.get("/graph")
async def export_graph(
    radius_km: float = Query(default=10.0, ge=1.0, le=30.0),
) -> Response:
    """Export a radius-cropped routing graph as compact binary for on-device A*.

    Only nodes within `radius_km` of the graph origin are exported, keeping
    the download small (~5-15 MB for a 10 km radius in a dense urban area).

    Binary format (little-endian):
      [8 bytes] float64  lat0
      [8 bytes] float64  lon0
      [4 bytes] uint32   N  (number of nodes in cropped graph)
      [N*8 bytes]        float32 east_m, float32 north_m  per node
      [4 bytes] uint32   E  (total directed edge records)
      [E*12 bytes]       uint32 from_node, uint32 to_node, float32 cost_m  per edge
    Returns 503 if the offline router is not ready yet.
    """
    if _road_router is None:
        return Response(status_code=503, content=b"router not ready")

    import struct as _struct
    import io as _io

    rr = _road_router
    all_xy: np.ndarray = rr._node_xy   # (N_full, 2) float64: [east_m, north_m]
    adj_full: list = rr._adj

    # ── Crop to radius ────────────────────────────────────────────────────
    radius_m = radius_km * 1000.0
    dist_sq = all_xy[:, 0] ** 2 + all_xy[:, 1] ** 2   # distance from ENU origin
    keep_mask = dist_sq <= radius_m ** 2
    old_ids = np.where(keep_mask)[0]                   # original node indices to keep
    new_id = np.full(len(all_xy), -1, dtype=np.int32)
    new_id[old_ids] = np.arange(len(old_ids), dtype=np.int32)

    node_xy_crop = all_xy[old_ids]   # (N_crop, 2)
    N = len(node_xy_crop)

    # ── Build cropped edge list ───────────────────────────────────────────
    buf = _io.BytesIO()
    buf.write(_struct.pack("<ddI", rr._lat0, rr._lon0, N))
    buf.write(node_xy_crop.astype(np.float32).tobytes())

    edge_buf = _io.BytesIO()
    E = 0
    for old_frm in old_ids:
        new_frm = int(new_id[old_frm])
        for old_to, cost in adj_full[old_frm]:
            new_to = int(new_id[old_to])
            if new_to < 0:
                continue   # destination outside radius — skip edge
            edge_buf.write(_struct.pack("<IIf", new_frm, new_to, float(cost)))
            E += 1

    buf.write(_struct.pack("<I", E))
    buf.write(edge_buf.getvalue())

    data = buf.getvalue()
    log.info("/graph: serving %.1f MB (%d nodes, %d edges, radius %.0f km)",
             len(data) / 1e6, N, E, radius_km)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=road_graph.bin"},
    )


@app.websocket("/ws/navigation")
async def ws_navigation(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Client connected: %s", ws.client)

    gru  = GRUEngine(_ONNX, _META)
    ekf  = EKFFusion()
    filt = ImuFilter()

    # Map matcher: loaded in a background thread (2.9M segments take ~8s to index)
    # Once ready, _matcher_holder[0] is set atomically — no lock needed (GIL).
    _matcher_holder: list[MapMatcher | None] = [None]
    _matcher_ready = threading.Event()
    map_available = _ROAD_GRAPH.exists()
    if not map_available:
        log.warning("Road graph not found at %s — map matching disabled. "
                    "Run scripts/download_road_graph.py to enable it.", _ROAD_GRAPH)

    def _load_matcher(lat0: float, lon0: float) -> None:
        try:
            log.info("Loading road graph in background …")
            m = MapMatcher(_ROAD_GRAPH, lat0, lon0)
            _matcher_holder[0] = m
            _matcher_ready.set()
            log.info("Map matcher ready — %d segments indexed", len(m._segs))
        except Exception as exc:
            log.warning("Map matcher failed: %s", exc)
            _matcher_ready.set()

    _loader_thread: threading.Thread | None = None

    sample_index  = 0
    last_publish  = time.monotonic()
    last_imu_t: float | None = None
    gru_speed: float = 0.0
    snapped: bool = False

    # ── GNSS hysteresis ───────────────────────────────────────────────────
    # Require N consecutive bad/good readings before switching mode.
    # Prevents a single satellite glitch from toggling DR ACTIVE.
    _GNSS_BAD_THRESH  = 5   # consecutive bad readings → DR ACTIVE
    _GNSS_GOOD_THRESH = 3   # consecutive good readings → GNSS AIDED
    _gnss_bad_streak  = 0
    _gnss_good_streak = 0
    _gnss_debounced   = False   # debounced validity (what the EKF/mode logic sees
    import math as _math

    try:
        async for raw in ws.iter_text():
            msg = json.loads(raw)
            now = time.monotonic()
            dt  = (now - last_imu_t) if last_imu_t is not None else 0.02
            last_imu_t = now

            # ── Stage 1: low-pass filter + pothole detection ──────────────
            raw_sample = [
                float(msg.get("acc_x",  0)), float(msg.get("acc_y",  0)), float(msg.get("acc_z",  0)),
                float(msg.get("gyro_x", 0)), float(msg.get("gyro_y", 0)), float(msg.get("gyro_z", 0)),
                float(msg.get("mag_x",  0)), float(msg.get("mag_y",  0)), float(msg.get("mag_z",  0)),
                float(msg.get("roll",   0)), float(msg.get("pitch",  0)), float(msg.get("yaw",    0)),
            ]
            filtered, pothole = filt.push(raw_sample)
            if pothole:
                gru.reset()
                log.debug("Pothole detected — GRU window reset")

            # ── Stage 2: GRU speed estimate ───────────────────────────────
            result = gru.push(*filtered)
            if result is not None:
                gru_speed = result

            # ── Stage 3: EKF predict + update ────────────────────────────
            heading_deg = float(msg.get("heading_deg", ekf.heading_deg))
            heading_rad = _math.radians(heading_deg)
            gnss_valid_raw = bool(msg.get("gnss_valid", False))

            # Apply hysteresis: debounce rapid GNSS valid/invalid flips
            if gnss_valid_raw:
                _gnss_good_streak += 1
                _gnss_bad_streak   = 0
                if _gnss_good_streak >= _GNSS_GOOD_THRESH:
                    _gnss_debounced = True
            else:
                _gnss_bad_streak  += 1
                _gnss_good_streak  = 0
                if _gnss_bad_streak >= _GNSS_BAD_THRESH:
                    _gnss_debounced = False

            gnss_valid    = _gnss_debounced
            lat           = float(msg.get("lat", 0))
            lon           = float(msg.get("lon", 0))
            gnss_speed    = float(msg.get("gnss_speed_ms", 0))
            gnss_acc      = float(msg.get("gnss_accuracy_m", 50))
            gnss_hdg_deg  = float(msg.get("gnss_heading_deg", 0))

            # Initialise EKF on first valid GNSS fix
            if not ekf.initialised and gnss_valid and (lat != 0.0 or lon != 0.0):
                ekf.init_from_gnss(lat, lon, heading_deg, gnss_speed, gnss_acc)
                # Kick off background road-graph load now that ENU origin is known
                if map_available and _loader_thread is None:
                    t = threading.Thread(
                        target=_load_matcher,
                        args=(ekf.lat0, ekf.lon0),
                        daemon=True,
                    )
                    t.start()
                    _loader_thread = t  # noqa: F841 — keeps reference alive

                # Build offline router in background (shares the same road graph)
                global _road_router, _router_loading
                if map_available and _road_router is None and not _router_loading:
                    _router_loading = True
                    threading.Thread(
                        target=_build_road_router,
                        args=(ekf.lat0, ekf.lon0),
                        daemon=True,
                    ).start()

            if ekf.initialised:
                # Predict with NHC kinematics
                ekf.predict(heading_rad, gru_speed, dt)

                # Always fuse IMU heading and GRU speed
                ekf.update_imu_heading(heading_rad)
                if result is not None:
                    ekf.update_gru_speed(gru_speed)

                # ZUPT: detect stationarity from raw IMU, NOT from GRU speed.
                # GRU can output 5-6 m/s even on a stationary phone (model artefact).
                # True stationarity = accel ≈ 1g (gravity only) + gyro near zero.
                _acc_x, _acc_y, _acc_z = filtered[0], filtered[1], filtered[2]
                _gyr_x, _gyr_y, _gyr_z = filtered[3], filtered[4], filtered[5]
                _accel_mag = _math.sqrt(_acc_x**2 + _acc_y**2 + _acc_z**2)
                _gyro_mag  = _math.sqrt(_gyr_x**2 + _gyr_y**2 + _gyr_z**2)
                _is_stationary = (
                    abs(_accel_mag - 9.81) < 0.5 and   # gravity-only accel
                    _gyro_mag < 0.08                    # <~5 deg/s rotation
                )
                if _is_stationary:
                    ekf.update_zupt()

                # Fuse GNSS when available
                if gnss_valid and (lat != 0.0 or lon != 0.0):
                    ekf.update_gnss_position(lat, lon, gnss_acc)
                    ekf.update_gnss_speed(gnss_speed)
                    # GPS course-over-ground: much more reliable than magnetometer
                    # when moving. Only valid when speed > 1.5 m/s and heading != 0.
                    if gnss_speed > 1.5 and gnss_hdg_deg > 0:
                        ekf.update_gnss_heading(_math.radians(gnss_hdg_deg))

                # ── Map matching (DR mode only) ───────────────────────────
                snapped = False
                matcher = _matcher_holder[0]   # None until background load completes
                if matcher is not None and not gnss_valid:
                    snap = matcher.snap(ekf.east_m, ekf.north_m, _math.radians(ekf.heading_deg))
                    if snap.snapped:
                        # Inject snapped position directly into EKF state
                        # (treat as a high-accuracy measurement: road width ~3 m)
                        ekf.update_gnss_position(
                            ekf.lat0 + _math.degrees(snap.north_m / 6_378_137.0),
                            ekf.lon0 + _math.degrees(snap.east_m / (6_378_137.0 * _math.cos(_math.radians(ekf.lat0)))),
                            3.0,  # road-width accuracy
                        )
                        ekf.update_road_bearing(snap.bearing_rad)
                        snapped = True

            # ── Stage 4: determine mode ───────────────────────────────────
            if not ekf.initialised:
                mode        = "GNSS_REACQUIRE"
                gnss_health = "OUTAGE"
            elif gnss_valid:
                mode        = "GNSS_AIDED"
                gnss_health = "OK"
            else:
                mode        = "DR_ACTIVE"
                gnss_health = "OUTAGE"

            # ── Publish at 10 Hz ──────────────────────────────────────────
            if now - last_publish < _PUBLISH_DT:
                continue

            last_publish  = now
            sample_index += 1

            await ws.send_text(json.dumps({
                "lat":            ekf.lat,
                "lon":            ekf.lon,
                "east_m":         round(ekf.east_m,      2),
                "north_m":        round(ekf.north_m,     2),
                "speed_fwd":      round(ekf.speed_ms,    3),
                "heading_deg":    round(ekf.heading_deg, 1),
                "gru_speed":      round(gru_speed,       3),
                "mode":           mode,
                "gnss_valid":     gnss_valid,
                "gnss_health":    gnss_health,
                "position_std_m": round(ekf.pos_std_m,   1),
                "map_matched":    snapped,
                "sample_index":   sample_index,
            }))

    except WebSocketDisconnect:
        log.info("Client disconnected: %s", ws.client)
    except Exception as exc:
        log.exception("Error in ws_navigation: %s", exc)
        await ws.close(code=1011)
