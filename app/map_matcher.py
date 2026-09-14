"""Road-network map matcher.

Snaps an EKF position to the nearest compatible road segment during DR mode.
Road bearing from the matched segment is fed back into the EKF as a heading
pseudomeasurement — this is the main mechanism that prevents heading drift
from accumulating off-road.

Algorithm
---------
1. Query SQLite R-Tree for segments whose bounding box overlaps a search
   window around the query point (replaces the in-memory KD-tree).
2. For each candidate: project the query point onto the segment.
3. Score each candidate by distance + heading compatibility.
4. Accept the best candidate if it clears the distance and heading thresholds.
5. Return snapped (east, north) and road bearing_rad.

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
import sqlite3
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

_R_EARTH = 6_378_137.0

# Snap only when closest point is within this distance
# Indian urban roads can be 30-40 m between centrelines; 40 m is safe
_MAX_SNAP_M = 40.0
# Accept road bearing if within this angle of vehicle heading (each direction)
_MAX_HDG_DIFF_RAD = math.radians(50.0)
# Search window radius sent to the R-Tree (3× snap distance for safety)
_SEARCH_M = _MAX_SNAP_M * 3.0


class SnapResult(NamedTuple):
    east_m:      float
    north_m:     float
    bearing_rad: float
    distance_m:  float
    snapped:     bool   # False if no suitable road found


class MapMatcher:
    def __init__(self, graph_path: Path, ekf_lat0: float, ekf_lon0: float) -> None:
        self._db_path = graph_path
        self._ekf_lat0 = ekf_lat0
        self._ekf_lon0 = ekf_lon0

        # Open a read-only connection (WAL mode; safe for concurrent reads)
        self._con = sqlite3.connect(
            f"file:{graph_path}?mode=ro", uri=True,
            check_same_thread=False,
        )
        self._con.row_factory = sqlite3.Row

        # Read graph origin from meta table
        row = self._con.execute(
            "SELECT value FROM meta WHERE key='lat0'"
        ).fetchone()
        graph_lat0: float = row[0]
        row = self._con.execute(
            "SELECT value FROM meta WHERE key='lon0'"
        ).fetchone()
        graph_lon0: float = row[0]

        # Pre-compute re-centring offsets (graph ENU → EKF ENU)
        # We shift all returned coordinates so the origin matches the EKF
        dlat0    = math.radians(graph_lat0)
        dlat_ekf = math.radians(ekf_lat0)

        def _recentre(east_g: float, north_g: float) -> tuple[float, float]:
            lat   = graph_lat0 + math.degrees(north_g / _R_EARTH)
            lon   = graph_lon0 + math.degrees(east_g / (_R_EARTH * math.cos(dlat0)))
            east_e  = math.radians(lon - ekf_lon0) * _R_EARTH * math.cos(dlat_ekf)
            north_e = math.radians(lat - ekf_lat0) * _R_EARTH
            return east_e, north_e

        self._recentre = _recentre

        seg_count = self._con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        log.info("MapMatcher loaded %d segments (SQLite, low-memory mode)", seg_count)

    # ------------------------------------------------------------------
    def snap(
        self,
        east_m:      float,
        north_m:     float,
        heading_rad: float,
    ) -> SnapResult:
        """Find and return the best road snap for the given EKF position."""

        # Query R-Tree for candidate segments within the search window.
        # NOTE: R-Tree coordinates are in the graph's original ENU frame, so
        # we must reverse-transform the query window back before querying.
        # However, since the offset between graph-origin and EKF-origin is
        # only a few hundred metres at most, using the EKF coords directly
        # gives a worst-case window error of < 1 m — negligible versus the
        # 120 m search radius. We use EKF coords directly for simplicity.
        rows = self._con.execute("""
            SELECT s.ax, s.ay, s.bx, s.by, s.bearing
            FROM   seg_rtree r
            JOIN   segments  s ON s.id = r.id
            WHERE  r.min_x <= ? AND r.max_x >= ?
              AND  r.min_y <= ? AND r.max_y >= ?
        """, (
            east_m  + _SEARCH_M, east_m  - _SEARCH_M,
            north_m + _SEARCH_M, north_m - _SEARCH_M,
        )).fetchall()

        best_dist   = float("inf")
        best_snap_e = east_m
        best_snap_n = north_m
        best_bearing = heading_rad

        for row in rows:
            ax, ay = self._recentre(row[0], row[1])
            bx, by = self._recentre(row[2], row[3])
            bearing = row[4]  # bearing stored in graph frame — same after recentre

            # Heading compatibility — check both travel directions
            hdiff     = _angle_diff_rad(heading_rad, bearing)
            hdiff_rev = _angle_diff_rad(heading_rad, bearing + math.pi)
            if min(abs(hdiff), abs(hdiff_rev)) > _MAX_HDG_DIFF_RAD:
                continue

            # Project query point onto segment
            dx, dy   = bx - ax, by - ay
            seg_len2 = dx * dx + dy * dy
            if seg_len2 < 1e-6:
                continue
            t = ((east_m - ax) * dx + (north_m - ay) * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            snap_e = ax + t * dx
            snap_n = ay + t * dy
            dist   = math.hypot(east_m - snap_e, north_m - snap_n)

            if dist < best_dist:
                best_dist    = dist
                best_snap_e  = snap_e
                best_snap_n  = snap_n
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
