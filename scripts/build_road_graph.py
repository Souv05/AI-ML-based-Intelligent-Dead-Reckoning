"""Download OSM road network and build road_graph.sqlite in one step.

This replaces running download_road_graph.py + convert_to_sqlite.py separately.

Usage:
    python scripts/build_road_graph.py
    python scripts/build_road_graph.py --bbox 22.3,88.1,22.7,88.6   # custom area
    python scripts/build_road_graph.py --lat0 22.5 --lon0 88.35      # fixed origin

The output file is configs/road_graph.sqlite.
The server reads this file for both map-matching (MapMatcher) and offline
routing (RoadRouter). Run once before starting the server, or whenever you
want to refresh the road network for a different area.
"""

from __future__ import annotations

import argparse
import math
import pickle
import sqlite3
import sys
import tempfile
from pathlib import Path

import requests

_ROOT = Path(__file__).parent.parent
_DB   = _ROOT / "configs" / "road_graph.sqlite"

_DEFAULT_BBOX = (22.117, 87.751, 23.106, 89.119)   # Kolkata region

_ROAD_TYPES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential",
    "living_street", "service",
}

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_R_EARTH = 6_378_137.0
_SNAP_Q  = 2.0   # must match router.py


# ── helpers ───────────────────────────────────────────────────────────────────

def _latlon_to_enu(lat: float, lon: float, lat0: float, lon0: float):
    lat0_rad = math.radians(lat0)
    east  = math.radians(lon - lon0) * _R_EARTH * math.cos(lat0_rad)
    north = math.radians(lat - lat0) * _R_EARTH
    return east, north


def _quant(v: float) -> int:
    return round(v * _SNAP_Q)


# ── download ──────────────────────────────────────────────────────────────────

def _download_segments(bbox, lat0, lon0) -> list[dict]:
    s, w, n, e = bbox
    print(f"Querying Overpass API  bbox=({s},{w},{n},{e}) …")
    query = f"""
[out:json][timeout:180];
(
  way["highway"]({s},{w},{n},{e});
);
out geom;
"""
    headers = {"User-Agent": "SIH2026-DeadReckoning/1.0 (research)"}
    resp = requests.post(_OVERPASS_URL, data={"data": query},
                         headers=headers, timeout=240)
    resp.raise_for_status()
    data = resp.json()

    segments: list[dict] = []
    for way in data.get("elements", []):
        if way.get("type") != "way":
            continue
        tags = way.get("tags", {})
        if tags.get("highway", "") not in _ROAD_TYPES:
            continue
        if tags.get("access") in ("private", "no"):
            continue
        geometry = way.get("geometry", [])
        if len(geometry) < 2:
            continue
        pts = [_latlon_to_enu(nd["lat"], nd["lon"], lat0, lon0) for nd in geometry]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 0.5:
                continue
            segments.append({
                "ax": a[0], "ay": a[1],
                "bx": b[0], "by": b[1],
                "bearing": math.atan2(b[0] - a[0], b[1] - a[1]),
                "length": length,
                "highway": tags.get("highway", ""),
            })

    print(f"  {len(segments):,} road segments downloaded")
    return segments


# ── sqlite build ──────────────────────────────────────────────────────────────

def _build_sqlite(segments: list[dict], lat0: float, lon0: float,
                  bbox: tuple, db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # meta
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("lat0", lat0), ("lon0", lon0),
        ("bbox_s", bbox[0]), ("bbox_w", bbox[1]),
        ("bbox_n", bbox[2]), ("bbox_e", bbox[3]),
    ])

    # segments + R-Tree
    db.execute("""
        CREATE TABLE segments (
            id INTEGER PRIMARY KEY,
            ax REAL, ay REAL, bx REAL, by REAL,
            bearing REAL, length REAL, highway TEXT
        )""")
    db.execute("""
        CREATE VIRTUAL TABLE seg_rtree USING rtree(
            id, min_x, max_x, min_y, max_y)""")

    seg_rows, rtree_rows = [], []
    for i, seg in enumerate(segments):
        seg_rows.append((i, seg["ax"], seg["ay"], seg["bx"], seg["by"],
                         seg["bearing"], seg["length"], seg.get("highway")))
        rtree_rows.append((i,
                           min(seg["ax"], seg["bx"]), max(seg["ax"], seg["bx"]),
                           min(seg["ay"], seg["by"]), max(seg["ay"], seg["by"])))
    db.executemany("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?)", seg_rows)
    db.executemany("INSERT INTO seg_rtree VALUES (?,?,?,?,?)", rtree_rows)
    print(f"  segments: {len(seg_rows):,} rows")

    # nodes + edges for A* routing
    db.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, x REAL, y REAL)")
    db.execute("CREATE VIRTUAL TABLE node_rtree USING rtree(id, min_x, max_x, min_y, max_y)")
    db.execute("CREATE TABLE edges (src INTEGER, dst INTEGER, cost REAL)")
    db.execute("CREATE INDEX edges_src ON edges(src)")

    node_xy:  list[tuple[float, float]] = []
    node_idx: dict[tuple[int, int], int] = {}

    def _node(x: float, y: float) -> int:
        key = (_quant(x), _quant(y))
        if key not in node_idx:
            node_idx[key] = len(node_xy)
            node_xy.append((x, y))
        return node_idx[key]

    edge_rows = []
    for seg in segments:
        na = _node(seg["ax"], seg["ay"])
        nb = _node(seg["bx"], seg["by"])
        edge_rows.extend([(na, nb, seg["length"]), (nb, na, seg["length"])])

    db.executemany("INSERT INTO nodes VALUES (?,?,?)",
                   [(i, x, y) for i, (x, y) in enumerate(node_xy)])
    db.executemany("INSERT INTO node_rtree VALUES (?,?,?,?,?)",
                   [(i, x, x, y, y) for i, (x, y) in enumerate(node_xy)])
    db.executemany("INSERT INTO edges VALUES (?,?,?)", edge_rows)
    print(f"  nodes: {len(node_xy):,}   edges: {len(edge_rows):,}")

    db.commit()
    db.close()
    size_mb = db_path.stat().st_size / 1_048_576
    print(f"\nDone → {db_path}  ({size_mb:.1f} MB)")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bbox", default=None,
                        help="south,west,north,east  e.g. 22.3,88.1,22.7,88.6")
    parser.add_argument("--lat0", type=float, default=None,
                        help="ENU origin latitude  (default: bbox centre)")
    parser.add_argument("--lon0", type=float, default=None,
                        help="ENU origin longitude (default: bbox centre)")
    parser.add_argument("--out", default=str(_DB),
                        help=f"output .sqlite path  (default: {_DB})")
    args = parser.parse_args()

    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        bbox = tuple(parts)
    else:
        bbox = _DEFAULT_BBOX

    s, w, n, e = bbox
    lat0 = args.lat0 if args.lat0 is not None else (s + n) / 2
    lon0 = args.lon0 if args.lon0 is not None else (w + e) / 2

    print(f"ENU origin: lat0={lat0:.5f}  lon0={lon0:.5f}")
    segments = _download_segments(bbox, lat0, lon0)
    if not segments:
        print("ERROR: no segments returned — check bbox or Overpass availability.")
        sys.exit(1)

    _build_sqlite(segments, lat0, lon0, bbox, Path(args.out))


if __name__ == "__main__":
    main()
