"""Road-network map matcher.

Snaps an EKF position to the nearest compatible road segment during DR mode.
Road bearing from the matched segment is fed back into the EKF as a heading
pseudomeasurement — this is the main mechanism that prevents heading drift
from accumulating off-road.

Algorithm
---------
1. KD-tree built on segment midpoints (ENU, built once at load time).
2. For each query: find K nearest midpoints, retrieve their segments.
3. Project the query point onto each candidate segment.
4. Score each candidate by distance + heading compatibility.
5. Accept the best candidate if it clears the distance and heading thresholds.
6. Return snapped (east, north) and road bearing_rad.

Heading compatibility gate: if |query_heading - road_bearing| > 60°
(considering both travel directions), the segment is skipped.
This prevents snapping to a parallel road one block over.

ENU origin must match the EKF's lat0/lon0. The road graph stores its own
origin (set during download); the matcher re-centres it on the EKF origin
at load time so all coordinates are consistent.
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import NamedTuple

import numpy as np
from scipy.spatial import KDTree

log = logging.getLogger(__name__)

_R_EARTH = 6_378_137.0

# Snap only when closest point is within this distance
# Indian urban roads can be 30-40 m between centrelines; 40 m is safe
_MAX_SNAP_M = 40.0
# Accept road bearing if within this angle of vehicle heading (each direction)
_MAX_HDG_DIFF_RAD = math.radians(50.0)
# KD-tree neighbours to check
_K_NEIGHBOURS = 12


class SnapResult(NamedTuple):
    east_m:     float
    north_m:    float
    bearing_rad: float
    distance_m: float
    snapped:    bool   # False if no suitable road found


class MapMatcher:
    def __init__(self, graph_path: Path, ekf_lat0: float, ekf_lon0: float) -> None:
        with open(graph_path, "rb") as f:
            payload = pickle.load(f)

        graph_lat0: float = payload["lat0"]
        graph_lon0: float = payload["lon0"]
        segments: list[dict] = payload["segments"]

        # Re-centre graph coordinates from graph origin to EKF origin
        dlat0 = math.radians(graph_lat0)
        dlat_ekf = math.radians(ekf_lat0)

        def _recentre(east_g: float, north_g: float) -> tuple[float, float]:
            # graph ENU → lat/lon → EKF ENU
            lat = graph_lat0 + math.degrees(north_g / _R_EARTH)
            lon = graph_lon0 + math.degrees(east_g / (_R_EARTH * math.cos(dlat0)))
            east_e  = math.radians(lon - ekf_lon0) * _R_EARTH * math.cos(dlat_ekf)
            north_e = math.radians(lat - ekf_lat0) * _R_EARTH
            return east_e, north_e

        self._segs: list[dict] = []
        midpoints: list[tuple[float, float]] = []

        for seg in segments:
            ax, ay = _recentre(seg["ax"], seg["ay"])
            bx, by = _recentre(seg["bx"], seg["by"])
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy)
            if length < 0.5:
                continue
            bearing = math.atan2(dx, dy)
            self._segs.append({
                "ax": ax, "ay": ay,
                "bx": bx, "by": by,
                "bearing": bearing,
                "length": length,
            })
            midpoints.append(((ax + bx) * 0.5, (ay + by) * 0.5))

        self._tree = KDTree(np.array(midpoints, dtype=np.float64))
        log.info("MapMatcher loaded %d segments", len(self._segs))

    # ------------------------------------------------------------------
    def snap(
        self,
        east_m: float,
        north_m: float,
        heading_rad: float,
    ) -> SnapResult:
        """Find and return the best road snap for the given EKF position."""
        q = np.array([[east_m, north_m]])
        k = min(_K_NEIGHBOURS, len(self._segs))
        dists, idxs = self._tree.query(q, k=k)
        dists = dists[0]
        idxs  = idxs[0]

        best_dist = float("inf")
        best_snap_e = east_m
        best_snap_n = north_m
        best_bearing = heading_rad

        for raw_dist, idx in zip(dists, idxs):
            # Quick pre-filter on midpoint distance to avoid expensive projection
            if raw_dist > _MAX_SNAP_M * 3:
                break

            seg = self._segs[idx]
            ax, ay = seg["ax"], seg["ay"]
            bx, by = seg["bx"], seg["by"]
            bearing = seg["bearing"]

            # Heading compatibility — check both travel directions
            hdiff = _angle_diff_rad(heading_rad, bearing)
            hdiff_rev = _angle_diff_rad(heading_rad, bearing + math.pi)
            if min(abs(hdiff), abs(hdiff_rev)) > _MAX_HDG_DIFF_RAD:
                continue

            # Project query point onto segment
            dx, dy = bx - ax, by - ay
            seg_len2 = dx * dx + dy * dy
            if seg_len2 < 1e-6:
                continue
            t = ((east_m - ax) * dx + (north_m - ay) * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            snap_e = ax + t * dx
            snap_n = ay + t * dy
            dist = math.hypot(east_m - snap_e, north_m - snap_n)

            if dist < best_dist:
                best_dist = dist
                best_snap_e = snap_e
                best_snap_n = snap_n
                # Pick direction closest to vehicle heading
                if abs(hdiff_rev) < abs(hdiff):
                    best_bearing = (bearing + math.pi) % (2 * math.pi) - math.pi
                else:
                    best_bearing = bearing

        snapped = best_dist <= _MAX_SNAP_M
        return SnapResult(
            east_m      = best_snap_e if snapped else east_m,
            north_m     = best_snap_n if snapped else north_m,
            bearing_rad = best_bearing,
            distance_m  = best_dist,
            snapped     = snapped,
        )


def _angle_diff_rad(a: float, b: float) -> float:
    """Signed difference a - b, wrapped to [-π, π]."""
    d = a - b
    return (d + math.pi) % (2 * math.pi) - math.pi
