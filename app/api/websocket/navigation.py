"""WebSocket handler: /ws/navigation

Phone -> server  (JSON, each IMU tick ~50 Hz):
{
  "acc_x": float,   "acc_y": float,   "acc_z": float,    // m/s^2
  "gyro_x": float,  "gyro_y": float,  "gyro_z": float,   // rad/s
  "mag_x": float,   "mag_y": float,   "mag_z": float,    // uT
  "roll": float,    "pitch": float,   "yaw": float,      // degrees
  "lat": float,     "lon": float,
  "heading_deg": float,              // compass/IMU heading (degrees)
  "gnss_heading_deg": float,         // GPS course-over-ground (degrees); send 0 when unavailable
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
import threading
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.api import state
from app.core.fusion.ekf_fusion import EKFFusion
from app.core.inference.gru_engine import GRUEngine
from app.core.map.map_matcher import MapMatcher
from app.core.preprocessing.imu_filter import ImuFilter

log = logging.getLogger(__name__)


async def ws_navigation(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Client connected: %s", ws.client)

    gru  = GRUEngine(state.ONNX_PATH, state.META_PATH)
    ekf  = EKFFusion()
    filt = ImuFilter()

    # Map matcher: loaded in a background thread (2.9M segments take ~8s to index).
    # Once ready, _matcher_holder[0] is set atomically — no lock needed (GIL).
    _matcher_holder: list[MapMatcher | None] = [None]
    map_available = state.ROAD_GRAPH.exists()
    if not map_available:
        log.warning(
            "Road graph not found at %s — map matching disabled. "
            "Run scripts/download_road_graph.py to enable it.",
            state.ROAD_GRAPH,
        )

    def _load_matcher(lat0: float, lon0: float) -> None:
        try:
            log.info("Loading road graph in background …")
            m = MapMatcher(state.ROAD_GRAPH, lat0, lon0)
            _matcher_holder[0] = m
            log.info("Map matcher ready — %d segments indexed", len(m._segs))
        except Exception as exc:
            log.warning("Map matcher failed: %s", exc)

    _loader_thread: threading.Thread | None = None

    sample_index  = 0
    last_publish  = time.monotonic()
    last_imu_t: float | None = None
    gru_speed: float = 0.0
    snapped: bool = False

    # ── GNSS hysteresis ───────────────────────────────────────────────────
    # Require N consecutive bad/good readings before switching mode.
    _GNSS_BAD_THRESH  = 5
    _GNSS_GOOD_THRESH = 3
    _gnss_bad_streak  = 0
    _gnss_good_streak = 0
    _gnss_debounced   = False
    _gnss_was_valid   = False   # tracks previous debounced state for reacquisition detection
    _reacq_fixes_left = 0       # countdown for inflated R during reacquisition blending

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
            heading_deg    = float(msg.get("heading_deg", ekf.heading_deg))
            heading_rad    = math.radians(heading_deg)
            gnss_valid_raw = bool(msg.get("gnss_valid", False))

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

            gnss_valid   = _gnss_debounced
            lat          = float(msg.get("lat", 0))
            lon          = float(msg.get("lon", 0))
            gnss_speed   = float(msg.get("gnss_speed_ms", 0))
            # Fix 3: floor accuracy at 8 m — Android often over-reports precision
            gnss_acc     = max(float(msg.get("gnss_accuracy_m", 50)), 8.0)
            gnss_hdg_deg = float(msg.get("gnss_heading_deg", 0))

            # Fix 2: detect reacquisition — inflate position noise for first 5 fixes
            # so the EKF blends back gradually instead of snapping
            if gnss_valid and not _gnss_was_valid:
                _reacq_fixes_left = 5
            _gnss_was_valid = gnss_valid

            if not ekf.initialised and gnss_valid and (lat != 0.0 or lon != 0.0):
                ekf.init_from_gnss(lat, lon, heading_deg, gnss_speed, gnss_acc)

                if map_available and _loader_thread is None:
                    t = threading.Thread(
                        target=_load_matcher,
                        args=(ekf.lat0, ekf.lon0),
                        daemon=True,
                    )
                    t.start()
                    _loader_thread = t

                # Build offline router in background if not already running
                if map_available and state.road_router is None and not state.router_loading:
                    state.router_loading = True
                    threading.Thread(
                        target=state.build_road_router,
                        args=(ekf.lat0, ekf.lon0),
                        daemon=True,
                    ).start()

            if ekf.initialised:
                ekf.predict(heading_rad, gru_speed, dt)
                ekf.update_imu_heading(heading_rad)
                if result is not None:
                    ekf.update_gru_speed(gru_speed)

                # ZUPT: detect stationarity from raw IMU, NOT from GRU speed.
                # GRU can output 5-6 m/s even on a stationary phone (model artefact).
                _acc_x, _acc_y, _acc_z = filtered[0], filtered[1], filtered[2]
                _gyr_x, _gyr_y, _gyr_z = filtered[3], filtered[4], filtered[5]
                _accel_mag = math.sqrt(_acc_x**2 + _acc_y**2 + _acc_z**2)
                _gyro_mag  = math.sqrt(_gyr_x**2 + _gyr_y**2 + _gyr_z**2)
                if abs(_accel_mag - 9.81) < 0.5 and _gyro_mag < 0.08:
                    ekf.update_zupt()

                if gnss_valid and (lat != 0.0 or lon != 0.0):
                    # Fix 2: ramp down inflated reacquisition noise over first 5 fixes
                    if _reacq_fixes_left > 0:
                        blend_acc = gnss_acc + 20.0 * (_reacq_fixes_left / 5)
                        _reacq_fixes_left -= 1
                    else:
                        blend_acc = gnss_acc
                    ekf.update_gnss_position(lat, lon, blend_acc)
                    ekf.update_gnss_speed(gnss_speed)
                    if gnss_speed > 1.5 and gnss_hdg_deg > 0:
                        ekf.update_gnss_heading(math.radians(gnss_hdg_deg))

                # Fix 1: map-matching runs in all modes.
                # During GNSS_AIDED: loose snap noise (15 m) so GNSS dominates but
                # lateral drift is still gently penalised via road bearing.
                # During DR_ACTIVE: tight snap noise (3 m) as primary position anchor.
                snapped = False
                matcher = _matcher_holder[0]
                if matcher is not None:
                    snap = matcher.snap(ekf.east_m, ekf.north_m, math.radians(ekf.heading_deg))
                    if snap.snapped:
                        snap_noise = 3.0 if not gnss_valid else 15.0
                        ekf.update_gnss_position(
                            ekf.lat0 + math.degrees(snap.north_m / 6_378_137.0),
                            ekf.lon0 + math.degrees(
                                snap.east_m / (6_378_137.0 * math.cos(math.radians(ekf.lat0)))
                            ),
                            snap_noise,
                        )
                        ekf.update_road_bearing(snap.bearing_rad)
                        snapped = True

            # ── Stage 4: determine mode ───────────────────────────────────
            if not ekf.initialised:
                mode        = "GNSS_REACQUIRE"
                gnss_health = "OUTAGE"
            elif gnss_valid and _reacq_fixes_left > 0:
                mode        = "GNSS_REACQUIRE"   # blending back — not yet fully aided
                gnss_health = "DEGRADED"
            elif gnss_valid:
                mode        = "GNSS_AIDED"
                gnss_health = "OK"
            else:
                mode        = "DR_ACTIVE"
                gnss_health = "OUTAGE"

            # ── Publish at 10 Hz ──────────────────────────────────────────
            if now - last_publish < state.PUBLISH_DT:
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
