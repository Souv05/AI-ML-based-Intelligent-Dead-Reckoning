"""Offline road router — A* on the downloaded OSM road segment graph.

Builds a node/edge graph from the flat segment list in road_graph.pkl by
snapping segment endpoints to shared nodes (quantised to 0.5 m grid).
A* is then run with a Euclidean heuristic to find the shortest road path
between two ENU positions.

The graph is built once at first call and cached in memory (~2-5 s for
2.9 M segments).  Subsequent route requests typically complete in < 300 ms
for urban distances under 15 km.
"""

from __future__ import annotations

import heapq
import logging
import math
import pickle
import struct
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_R_EARTH = 6_378_137.0
_SNAP_M  = 0.5          # endpoints within 0.5 m → same node
_SNAP_Q  = 2.0          # quantisation step (1 / _SNAP_Q metres per grid cell)


def _quant(v: float) -> int:
    return round(v * _SNAP_Q)


class RoadRouter:
    """A* router over the OSM road segment graph.

    Parameters
    ----------
    graph_path : Path
        Path to road_graph.pkl produced by scripts/download_road_graph.py.
    lat0, lon0 : float
        EKF ENU origin.  If they differ from the graph's own origin the
        coordinates are re-centred automatically.
    """

    def __init__(self, graph_path: Path, lat0: float, lon0: float) -> None:
        # Cache path — keyed by graph mtime + origin so it's invalidated on re-download
        cache_path = graph_path.parent / f"routing_cache_{graph_path.stat().st_mtime_ns}_{round(lat0*1e4)}_{round(lon0*1e4)}.pkl"

        if cache_path.exists():
            log.info("RoadRouter: loading pre-built routing cache from %s …", cache_path)
            t0 = __import__("time").monotonic()
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            self._node_xy: np.ndarray = cached["node_xy"]
            self._adj     = cached["adj"]
            self._lat0    = lat0
            self._lon0    = lon0
            log.info("RoadRouter: cache loaded in %.1fs — %d nodes",
                     __import__("time").monotonic() - t0, len(self._node_xy))
            return

        log.info("RoadRouter: building routing graph from %s …", graph_path)
        t0 = __import__("time").monotonic()

        with open(graph_path, "rb") as f:
            payload = pickle.load(f)

        graph_lat0: float = payload["lat0"]
        graph_lon0: float = payload["lon0"]
        segments: list[dict] = payload["segments"]

        dlat0     = math.radians(graph_lat0)
        dlat_ekf  = math.radians(lat0)

        def _recentre(ex: float, ny: float) -> tuple[float, float]:
            lat = graph_lat0 + math.degrees(ny / _R_EARTH)
            lon = graph_lon0 + math.degrees(ex / (_R_EARTH * math.cos(dlat0)))
            e   = math.radians(lon - lon0) * _R_EARTH * math.cos(dlat_ekf)
            n   = math.radians(lat - lat0) * _R_EARTH
            return e, n

        # ── Build node table ──────────────────────────────────────────────
        node_xy: list[tuple[float, float]] = []
        node_idx: dict[tuple[int, int], int] = {}

        def _node(ex: float, ny: float) -> int:
            key = (_quant(ex), _quant(ny))
            if key not in node_idx:
                node_idx[key] = len(node_xy)
                node_xy.append((ex, ny))
            return node_idx[key]

        # ── Build adjacency list ──────────────────────────────────────────
        adj: list[list[tuple[int, float]]] = []

        for seg in segments:
            ax, ay = _recentre(seg["ax"], seg["ay"])
            bx, by = _recentre(seg["bx"], seg["by"])
            length  = math.hypot(bx - ax, by - ay)
            if length < 0.1:
                continue

            na = _node(ax, ay)
            nb = _node(bx, by)

            while len(adj) <= max(na, nb):
                adj.append([])

            adj[na].append((nb, length))
            adj[nb].append((na, length))

        self._node_xy = np.array(node_xy, dtype=np.float64)
        self._adj     = adj
        self._lat0    = lat0
        self._lon0    = lon0
        build_time = __import__("time").monotonic() - t0
        log.info("RoadRouter: built %d nodes in %.1fs — saving cache",
                 len(node_xy), build_time)

        # Persist for next server start
        try:
            with open(cache_path, "wb") as f:
                pickle.dump({"node_xy": self._node_xy, "adj": adj},
                            f, protocol=pickle.HIGHEST_PROTOCOL)
            log.info("RoadRouter: cache saved → %s", cache_path)
        except Exception as exc:
            log.warning("RoadRouter: cache save failed: %s", exc)

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

        gx, gy = self._node_xy[goal]

        # ── A* ────────────────────────────────────────────────────────────
        g_score: dict[int, float] = {start: 0.0}
        came_from: dict[int, int] = {}
        open_heap: list[tuple[float, int]] = []
        heapq.heappush(open_heap, (self._h(start, gx, gy), start))
        expansions = 0

        while open_heap:
            _, cur = heapq.heappop(open_heap)
            if cur == goal:
                return self._reconstruct(came_from, cur,
                                         origin_east, origin_north,
                                         dest_east, dest_north)
            if expansions >= max_nodes:
                log.warning("RoadRouter: max_nodes reached — no path found")
                return None
            expansions += 1

            cur_g = g_score[cur]
            for nb, cost in self._adj[cur]:
                tentative = cur_g + cost
                if tentative < g_score.get(nb, math.inf):
                    g_score[nb] = tentative
                    came_from[nb] = cur
                    f = tentative + self._h(nb, gx, gy)
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
        xy  = self._node_xy
        dx  = xy[:, 0] - east
        dy  = xy[:, 1] - north
        return int(np.argmin(dx * dx + dy * dy))

    def _h(self, node: int, gx: float, gy: float) -> float:
        x, y = self._node_xy[node]
        return math.hypot(x - gx, y - gy)

    def _reconstruct(
        self,
        came_from: dict[int, int],
        cur: int,
        origin_east: float, origin_north: float,
        dest_east:   float, dest_north:   float,
    ) -> list[tuple[float, float]]:
        path: list[tuple[float, float]] = []
        while cur in came_from:
            path.append(tuple(self._node_xy[cur]))  # type: ignore[arg-type]
            cur = came_from[cur]
        path.append(tuple(self._node_xy[cur]))  # type: ignore[arg-type]
        path.reverse()
        # Prepend exact origin and append exact destination
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
