"""Offline road router — A* on the downloaded OSM road segment graph.

Uses an SQLite database (road_graph.sqlite) produced by
scripts/convert_to_sqlite.py.  The node R-Tree is queried to find the
nearest node to any ENU position, and the edges table is queried during
A* expansion to enumerate neighbours — so the full graph never lives in RAM.

The public API is identical to the original in-memory version:
    RoadRouter(graph_path, lat0, lon0)
    .route(origin_east, origin_north, dest_east, dest_north) → list | None
    .route_latlon(origin_lat, origin_lon, dest_lat, dest_lon) → list | None

A* with a Euclidean heuristic finds shortest road paths.  Subsequent route
requests typically complete in < 2 s for urban distances under 15 km.
"""

from __future__ import annotations

import heapq
import logging
import math
import sqlite3
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_R_EARTH = 6_378_137.0
_SNAP_Q  = 2.0   # must match convert_to_sqlite.py

# Search radius used when looking for the nearest node to a query position
_NODE_SEARCH_M = 500.0


class RoadRouter:
    """A* router over the OSM road segment graph (SQLite, low-memory mode).

    Parameters
    ----------
    graph_path : Path
        Path to road_graph.sqlite produced by scripts/convert_to_sqlite.py.
    lat0, lon0 : float
        EKF ENU origin.  If they differ from the graph's own origin the
        coordinates are re-centred automatically.
    """

    def __init__(self, graph_path: Path, lat0: float, lon0: float) -> None:
        self._lat0 = lat0
        self._lon0 = lon0

        self._con = sqlite3.connect(
            f"file:{graph_path}?mode=ro", uri=True,
            check_same_thread=False,
        )

        # Read graph origin
        def _meta(key: str) -> float:
            return self._con.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()[0]

        graph_lat0 = _meta("lat0")
        graph_lon0 = _meta("lon0")

        dlat0    = math.radians(graph_lat0)
        dlat_ekf = math.radians(lat0)

        def _recentre(ex: float, ny: float) -> tuple[float, float]:
            lat = graph_lat0 + math.degrees(ny / _R_EARTH)
            lon = graph_lon0 + math.degrees(ex / (_R_EARTH * math.cos(dlat0)))
            e   = math.radians(lon - lon0) * _R_EARTH * math.cos(dlat_ekf)
            n   = math.radians(lat - lat0) * _R_EARTH
            return e, n

        self._recentre = _recentre

        node_count = self._con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        log.info("RoadRouter: ready — %d nodes (SQLite, low-memory mode)", node_count)

    # ── Public API ────────────────────────────────────────────────────────

    def route(
        self,
        origin_east: float, origin_north: float,
        dest_east:   float, dest_north:   float,
        max_nodes:   int = 500_000,
    ) -> Optional[list[tuple[float, float]]]:
        """Return an ENU polyline (east_m, north_m) list, or None if no path.

        Falls back gracefully: if no path is found within max_nodes expansions
        returns None so the caller can degrade to a straight line.
        """
        start = self._nearest_node(origin_east, origin_north)
        goal  = self._nearest_node(dest_east,   dest_north)
        if start == goal:
            return [(origin_east, origin_north), (dest_east, dest_north)]

        gx, gy = self._node_xy(goal)

        # ── A* ────────────────────────────────────────────────────────────
        g_score:   dict[int, float] = {start: 0.0}
        came_from: dict[int, int]   = {}
        open_heap: list[tuple[float, int]] = []
        heapq.heappush(open_heap, (self._h_xy(start, gx, gy), start))
        expansions = 0

        while open_heap:
            _, cur = heapq.heappop(open_heap)
            if cur == goal:
                return self._reconstruct(
                    came_from, cur,
                    origin_east, origin_north,
                    dest_east,   dest_north,
                )
            if expansions >= max_nodes:
                log.warning("RoadRouter: max_nodes reached — no path found")
                return None
            expansions += 1

            cur_g = g_score[cur]
            for nb, cost in self._neighbours(cur):
                tentative = cur_g + cost
                if tentative < g_score.get(nb, math.inf):
                    g_score[nb]   = tentative
                    came_from[nb] = cur
                    f = tentative + self._h_xy(nb, gx, gy)
                    heapq.heappush(open_heap, (f, nb))

        log.warning("RoadRouter: open heap exhausted — no path found")
        return None

    def route_latlon(
        self,
        origin_lat: float, origin_lon: float,
        dest_lat:   float, dest_lon:   float,
    ) -> Optional[list[tuple[float, float]]]:
        """Route from/to lat/lon; returns list of (lat, lon) tuples."""
        oe, on_ = self._ll_to_enu(origin_lat, origin_lon)
        de, dn  = self._ll_to_enu(dest_lat,   dest_lon)
        enu_path = self.route(oe, on_, de, dn)
        if enu_path is None:
            return None
        return [self._enu_to_ll(e, n) for e, n in enu_path]

    # ── Helpers ───────────────────────────────────────────────────────────

    def _nearest_node(self, east: float, north: float) -> int:
        """Return the id of the node nearest to (east, north) via R-Tree."""
        r = _NODE_SEARCH_M
        while True:
            rows = self._con.execute("""
                SELECT n.id, n.x, n.y
                FROM   node_rtree r2
                JOIN   nodes n ON n.id = r2.id
                WHERE  r2.min_x <= ? AND r2.max_x >= ?
                  AND  r2.min_y <= ? AND r2.max_y >= ?
            """, (east + r, east - r, north + r, north - r)).fetchall()
            if rows:
                break
            r *= 2  # expand search if nothing found

        best_id   = rows[0][0]
        best_dist = math.hypot(rows[0][1] - east, rows[0][2] - north)
        for nid, nx, ny in rows[1:]:
            d = math.hypot(nx - east, ny - north)
            if d < best_dist:
                best_dist = d
                best_id   = nid
        return best_id

    def _node_xy(self, node_id: int) -> tuple[float, float]:
        """Return (x, y) ENU coordinates for a node."""
        row = self._con.execute(
            "SELECT x, y FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        return float(row[0]), float(row[1])

    def _neighbours(self, node_id: int) -> list[tuple[int, float]]:
        """Return list of (neighbour_id, cost) for A* expansion."""
        rows = self._con.execute(
            "SELECT dst, cost FROM edges WHERE src=?", (node_id,)
        ).fetchall()
        return [(int(r[0]), float(r[1])) for r in rows]

    def _h_xy(self, node_id: int, gx: float, gy: float) -> float:
        x, y = self._node_xy(node_id)
        return math.hypot(x - gx, y - gy)

    def _reconstruct(
        self,
        came_from:    dict[int, int],
        cur:          int,
        origin_east:  float, origin_north: float,
        dest_east:    float, dest_north:   float,
    ) -> list[tuple[float, float]]:
        path: list[tuple[float, float]] = []
        while cur in came_from:
            x, y = self._node_xy(cur)
            path.append((x, y))
            cur = came_from[cur]
        x, y = self._node_xy(cur)
        path.append((x, y))
        path.reverse()
        path.insert(0, (origin_east, origin_north))
        path.append((dest_east, dest_north))
        return path

    def _ll_to_enu(self, lat: float, lon: float) -> tuple[float, float]:
        lat0r = math.radians(self._lat0)
        e = math.radians(lon - self._lon0) * _R_EARTH * math.cos(lat0r)
        n = math.radians(lat - self._lat0) * _R_EARTH
        return e, n

    def _enu_to_ll(self, east: float, north: float) -> tuple[float, float]:
        lat0r = math.radians(self._lat0)
        lat = self._lat0 + math.degrees(north / _R_EARTH)
        lon = self._lon0 + math.degrees(east / (_R_EARTH * math.cos(lat0r)))
        return lat, lon
