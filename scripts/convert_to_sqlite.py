"""Convert configs/road_graph.pkl → configs/road_graph.sqlite

Run once before starting (or re-starting) the server after a new road-graph
download:

    python scripts/convert_to_sqlite.py

The resulting .sqlite file replaces road_graph.pkl as the road-network source.
It contains three logical layers:

    meta         – lat0, lon0, bbox
    segments     – every road segment for map-matching
    seg_rtree    – R-Tree virtual table on segment bounding boxes
    nodes        – unique road intersection / endpoint nodes
    node_rtree   – R-Tree virtual table on node positions
    edges        – directed adjacency list for A* routing

All ENU coordinates are stored in metres, bearing in radians.
"""

from __future__ import annotations

import math
import pickle
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PKL  = _ROOT / "configs" / "road_graph.pkl"
_DB   = _ROOT / "configs" / "road_graph.sqlite"

_SNAP_Q = 2.0   # must match router.py


def _quant(v: float) -> int:
    return round(v * _SNAP_Q)


def convert(pkl_path: Path, db_path: Path) -> None:
    print(f"Loading {pkl_path} …")
    with open(pkl_path, "rb") as f:
        payload = pickle.load(f)

    lat0: float      = payload["lat0"]
    lon0: float      = payload["lon0"]
    bbox: tuple      = payload["bbox"]
    segments: list   = payload["segments"]
    print(f"  {len(segments):,} road segments, origin lat0={lat0} lon0={lon0}")

    if db_path.exists():
        db_path.unlink()

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # ── meta ──────────────────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE meta (
            key   TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("lat0", lat0), ("lon0", lon0),
        ("bbox_s", bbox[0]), ("bbox_w", bbox[1]),
        ("bbox_n", bbox[2]), ("bbox_e", bbox[3]),
    ])

    # ── segments (for MapMatcher) ─────────────────────────────────────────
    db.execute("""
        CREATE TABLE segments (
            id      INTEGER PRIMARY KEY,
            ax      REAL NOT NULL,
            ay      REAL NOT NULL,
            bx      REAL NOT NULL,
            by      REAL NOT NULL,
            bearing REAL NOT NULL,
            length  REAL NOT NULL,
            highway TEXT
        )
    """)
    # R-Tree on segment bounding boxes  (minX, maxX, minY, maxY)
    db.execute("""
        CREATE VIRTUAL TABLE seg_rtree USING rtree(
            id,
            min_x, max_x,
            min_y, max_y
        )
    """)

    seg_rows   = []
    rtree_rows = []
    for i, seg in enumerate(segments):
        ax, ay = seg["ax"], seg["ay"]
        bx, by = seg["bx"], seg["by"]
        seg_rows.append((
            i,
            ax, ay, bx, by,
            seg["bearing"],
            seg["length"],
            seg.get("highway"),
        ))
        rtree_rows.append((
            i,
            min(ax, bx), max(ax, bx),
            min(ay, by), max(ay, by),
        ))

    db.executemany(
        "INSERT INTO segments VALUES (?,?,?,?,?,?,?,?)", seg_rows)
    db.executemany(
        "INSERT INTO seg_rtree VALUES (?,?,?,?,?)", rtree_rows)
    print(f"  segments table: {len(seg_rows):,} rows")

    # ── nodes + edges (for RoadRouter) ────────────────────────────────────
    db.execute("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            x  REAL NOT NULL,
            y  REAL NOT NULL
        )
    """)
    db.execute("""
        CREATE VIRTUAL TABLE node_rtree USING rtree(
            id,
            min_x, max_x,
            min_y, max_y
        )
    """)
    db.execute("""
        CREATE TABLE edges (
            src    INTEGER NOT NULL,
            dst    INTEGER NOT NULL,
            cost   REAL    NOT NULL
        )
    """)
    db.execute("CREATE INDEX edges_src ON edges(src)")

    node_xy:  list[tuple[float, float]]  = []
    node_idx: dict[tuple[int, int], int] = {}

    def _node(ex: float, ny: float) -> int:
        key = (_quant(ex), _quant(ny))
        if key not in node_idx:
            node_idx[key] = len(node_xy)
            node_xy.append((ex, ny))
        return node_idx[key]

    edge_rows: list[tuple[int, int, float]] = []

    for seg in segments:
        ax, ay = seg["ax"], seg["ay"]
        bx, by = seg["bx"], seg["by"]
        length = math.hypot(bx - ax, by - ay)
        if length < 0.1:
            continue
        na = _node(ax, ay)
        nb = _node(bx, by)
        edge_rows.append((na, nb, length))
        edge_rows.append((nb, na, length))

    node_rows  = [(i, x, y) for i, (x, y) in enumerate(node_xy)]
    nrtree_rows = [(i, x, x, y, y) for i, (x, y) in enumerate(node_xy)]

    db.executemany("INSERT INTO nodes VALUES (?,?,?)", node_rows)
    db.executemany("INSERT INTO node_rtree VALUES (?,?,?,?,?)", nrtree_rows)
    db.executemany("INSERT INTO edges VALUES (?,?,?)", edge_rows)
    print(f"  nodes table:    {len(node_rows):,} rows")
    print(f"  edges table:    {len(edge_rows):,} rows")

    db.commit()
    db.close()

    size_mb = db_path.stat().st_size / 1_048_576
    print(f"\nDone -> {db_path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    pkl = Path(sys.argv[1]) if len(sys.argv) > 1 else _PKL
    db  = Path(sys.argv[2]) if len(sys.argv) > 2 else _DB
    convert(pkl, db)
