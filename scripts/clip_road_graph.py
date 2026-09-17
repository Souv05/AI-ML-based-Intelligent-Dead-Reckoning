"""Clip road_graph.sqlite to a smaller bounding box for production deployment.

Reads the full state-wide SQLite and writes a compact one covering only the
demo area.  The output is suitable for hosting on GitHub Releases and
downloading at Render startup via ROAD_GRAPH_URL.

Target size for the default Kolkata bbox: ~15–40 MB vs 800 MB full state.

Usage:
    python scripts/clip_road_graph.py                        # default Kolkata bbox
    python scripts/clip_road_graph.py --bbox 22.3,88.1,22.7,88.6

Does NOT require the R-tree extension — queries directly on segment columns.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_SRC  = _ROOT / "configs" / "road_graph.sqlite"
_DST  = _ROOT / "configs" / "road_graph_kolkata.sqlite"

# ~50 km × 50 km block centred on Kolkata (south, west, north, east)
_DEFAULT_BBOX = (22.3, 88.1, 22.7, 88.6)
_R_EARTH      = 6_378_137.0
_BATCH        = 50_000


def _to_enu(lat: float, lon: float, lat0: float, lon0: float):
    east  = math.radians(lon - lon0) * _R_EARTH * math.cos(math.radians(lat0))
    north = math.radians(lat - lat0) * _R_EARTH
    return east, north


def _progress(label: str, i: int, total: int) -> None:
    pct = 100 * i // total
    bar = "#" * (pct // 4)
    print(f"\r  {label}: [{bar:<25}] {pct:3d}%  ({i:,}/{total:,})", end="", flush=True)


def clip(src_path: Path, dst_path: Path, bbox: tuple) -> None:
    if not src_path.exists():
        sys.exit(f"ERROR: source not found: {src_path}")

    print(f"\nSource : {src_path}  ({src_path.stat().st_size / 1e6:.0f} MB)")
    print(f"Bbox   : S={bbox[0]}  W={bbox[1]}  N={bbox[2]}  E={bbox[3]}")

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    meta  = dict(src.execute("SELECT key, value FROM meta").fetchall())
    lat0  = float(meta["lat0"])
    lon0  = float(meta["lon0"])
    print(f"Origin : lat0={lat0}  lon0={lon0}")

    s, w, n, e = bbox
    ex_min, _ = _to_enu(s, w, lat0, lon0)
    ex_max, _ = _to_enu(s, e, lat0, lon0)
    _, ey_min  = _to_enu(s, w, lat0, lon0)
    _, ey_max  = _to_enu(n, w, lat0, lon0)
    print(f"ENU    : east=[{ex_min:.0f}, {ex_max:.0f}]  north=[{ey_min:.0f}, {ey_max:.0f}]")

    # ── 1. Select segments fully inside bbox ──────────────────────────────────
    print("\n[1/4] Selecting segments …")
    segs = src.execute("""
        SELECT id, ax, ay, bx, by, bearing, length, highway
        FROM segments
        WHERE ax BETWEEN ? AND ?
          AND bx BETWEEN ? AND ?
          AND ay BETWEEN ? AND ?
          AND by BETWEEN ? AND ?
    """, (ex_min, ex_max, ex_min, ex_max,
          ey_min, ey_max, ey_min, ey_max)).fetchall()

    if not segs:
        sys.exit("ERROR: no segments in bbox — verify --bbox or source file.")
    print(f"\n  {len(segs):,} segments selected")

    # ── 2. Collect unique node IDs referenced by kept edges ───────────────────
    print("[2/4] Collecting nodes in bbox …")
    nodes = src.execute("""
        SELECT id, x, y FROM nodes
        WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?
    """, (ex_min, ex_max, ey_min, ey_max)).fetchall()

    node_ids = {r[0] for r in nodes}
    print(f"  {len(nodes):,} nodes selected")

    # ── 3. Select edges where both endpoints are in bbox ─────────────────────
    # Use a temp table to avoid huge IN() literals (SQLite limit ~999 params)
    print("[3/4] Collecting edges …")
    src_rw = sqlite3.connect(src_path)   # need read-write for temp table
    src_rw.execute("PRAGMA temp_store=MEMORY")
    src_rw.execute("CREATE TEMP TABLE _keep_nodes (id INTEGER PRIMARY KEY)")
    for batch_start in range(0, len(nodes), _BATCH):
        chunk = [(r[0],) for r in nodes[batch_start:batch_start + _BATCH]]
        src_rw.executemany("INSERT INTO _keep_nodes VALUES (?)", chunk)
    src_rw.commit()

    edges = src_rw.execute("""
        SELECT e.src, e.dst, e.cost FROM edges e
        JOIN _keep_nodes ka ON e.src = ka.id
        JOIN _keep_nodes kb ON e.dst = kb.id
    """).fetchall()
    src_rw.close()
    src.close()
    print(f"  {len(edges):,} edges selected")

    # ── 4. Write output ───────────────────────────────────────────────────────
    print("[4/4] Writing output …")
    if dst_path.exists():
        dst_path.unlink()
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    dst = sqlite3.connect(dst_path)
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA synchronous=NORMAL")
    dst.execute("PRAGMA cache_size=-65536")   # 64 MB page cache

    dst.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    dst.executemany("INSERT INTO meta VALUES (?,?)", [
        ("lat0", lat0), ("lon0", lon0),
        ("bbox_s", bbox[0]), ("bbox_w", bbox[1]),
        ("bbox_n", bbox[2]), ("bbox_e", bbox[3]),
    ])

    dst.execute("""CREATE TABLE segments (
        id INTEGER PRIMARY KEY,
        ax REAL, ay REAL, bx REAL, by REAL,
        bearing REAL, length REAL, highway TEXT)""")

    # R-tree: only create if the extension is available
    has_rtree = _has_rtree(dst)
    if has_rtree:
        dst.execute("CREATE VIRTUAL TABLE seg_rtree USING rtree(id, min_x, max_x, min_y, max_y)")
        dst.execute("CREATE VIRTUAL TABLE node_rtree USING rtree(id, min_x, max_x, min_y, max_y)")
    else:
        # Fallback: plain covering index (map_matcher.py also falls back to this)
        dst.execute("CREATE INDEX seg_bbox ON segments(ax, bx, ay, by)")
        print("  NOTE: R-tree not available — using plain index (snap will still work)")

    # Insert segments in batches
    seg_data  = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in segs]
    for i in range(0, len(seg_data), _BATCH):
        dst.executemany("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?)", seg_data[i:i+_BATCH])
        _progress("segments", min(i + _BATCH, len(seg_data)), len(seg_data))
    print()

    if has_rtree:
        rtree_data = [(r[0], min(r[1],r[3]), max(r[1],r[3]),
                              min(r[2],r[4]), max(r[2],r[4])) for r in segs]
        for i in range(0, len(rtree_data), _BATCH):
            dst.executemany("INSERT INTO seg_rtree VALUES (?,?,?,?,?)", rtree_data[i:i+_BATCH])

    dst.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, x REAL, y REAL)")
    for i in range(0, len(nodes), _BATCH):
        dst.executemany("INSERT INTO nodes VALUES (?,?,?)", nodes[i:i+_BATCH])
        _progress("nodes   ", min(i + _BATCH, len(nodes)), len(nodes))
    print()

    if has_rtree:
        node_rt = [(r[0], r[1], r[1], r[2], r[2]) for r in nodes]
        for i in range(0, len(node_rt), _BATCH):
            dst.executemany("INSERT INTO node_rtree VALUES (?,?,?,?,?)", node_rt[i:i+_BATCH])

    dst.execute("CREATE TABLE edges (src INTEGER, dst INTEGER, cost REAL)")
    dst.execute("CREATE INDEX edges_src ON edges(src)")
    for i in range(0, len(edges), _BATCH):
        dst.executemany("INSERT INTO edges VALUES (?,?,?)", edges[i:i+_BATCH])
        _progress("edges   ", min(i + _BATCH, len(edges)), len(edges))
    print()

    dst.commit()
    dst.close()

    size_mb = dst_path.stat().st_size / 1_048_576
    print(f"\nOutput : {dst_path}")
    print(f"Size   : {size_mb:.1f} MB  (was {src_path.stat().st_size / 1e6:.0f} MB)")
    print(f"Counts : {len(segs):,} segments  {len(nodes):,} nodes  {len(edges):,} edges")


def _has_rtree(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE _rtree_test USING rtree(id, x0, x1)")
        conn.execute("DROP TABLE _rtree_test")
        return True
    except sqlite3.OperationalError:
        return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src",  default=str(_SRC))
    p.add_argument("--out",  default=str(_DST))
    p.add_argument("--bbox", default=None,
                   help="south,west,north,east  (default: Kolkata 22.3,88.1,22.7,88.6)")
    args = p.parse_args()

    bbox = _DEFAULT_BBOX
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            p.error("--bbox needs exactly 4 values: south,west,north,east")
        bbox = tuple(parts)

    clip(Path(args.src), Path(args.out), bbox)


if __name__ == "__main__":
    main()
