"""Build road_graph.sqlite from a local .osm.pbf file (Geofabrik extract).

Replaces build_road_graph.py — no live Overpass query, no timeouts.

=== QUICK START ===

Step 1 — Download a regional extract from Geofabrik (pick the smallest one
         that covers your demo route):
  https://download.geofabrik.de/asia/india/west-bengal-latest.osm.pbf

  Direct download command (Windows PowerShell / curl):
    curl -L -o west-bengal-latest.osm.pbf ^
      https://download.geofabrik.de/asia/india/west-bengal-latest.osm.pbf
  (~130 MB for West Bengal)

Step 2 — (Recommended) Clip to your demo area using osmium-tool CLI to keep
          the SQLite small and fast. Install osmium-tool:
    Windows: https://osmcode.org/osmium-tool/  (pre-built .exe in ZIP)
    Linux:   sudo apt install osmium-tool

  Clip command (bbox = minlon,minlat,maxlon,maxlat):
    osmium extract -b 88.1,22.3,88.6,22.7 ^
        west-bengal-latest.osm.pbf -o kolkata_demo.osm.pbf

  Typical clipped size: 5-15 MB for a ~50 km x 50 km area.

Step 3 — Build the SQLite road graph:
    python scripts/build_road_graph_from_pbf.py --pbf kolkata_demo.osm.pbf

  With a custom bbox filter (useful if you skipped Step 2):
    python scripts/build_road_graph_from_pbf.py ^
        --pbf west-bengal-latest.osm.pbf ^
        --bbox 22.3,88.1,22.7,88.6

  With a fixed ENU origin (optional — defaults to bbox centre):
    python scripts/build_road_graph_from_pbf.py --pbf ... --lat0 22.5 --lon0 88.35

Step 4 — Verify:
    python scripts/build_road_graph_from_pbf.py --verify

Output: configs/road_graph.sqlite  (identical format to build_road_graph.py)

=== REQUIREMENTS ===
    pip install osmium
(osmium-tool CLI is only needed for Step 2 clipping; not needed by this script)
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DB   = _ROOT / "configs" / "road_graph.sqlite"

_DEFAULT_BBOX = (22.3, 88.1, 22.7, 88.6)   # central Kolkata (demo area)

_ROAD_TYPES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential",
    "living_street", "service",
}

_R_EARTH = 6_378_137.0
_SNAP_Q  = 2.0   # quantisation for node deduplication — must match router.py


# ── helpers ───────────────────────────────────────────────────────────────────

def _latlon_to_enu(lat: float, lon: float, lat0: float, lon0: float):
    lat0_rad = math.radians(lat0)
    east  = math.radians(lon - lon0) * _R_EARTH * math.cos(lat0_rad)
    north = math.radians(lat - lat0) * _R_EARTH
    return east, north


def _quant(v: float) -> int:
    return round(v * _SNAP_Q)


# ── PBF parser ────────────────────────────────────────────────────────────────

def _parse_pbf(
    pbf_path: str | Path,
    bbox: tuple[float, float, float, float] | None,
    lat0: float,
    lon0: float,
) -> list[dict]:
    """Parse road segments from a .osm.pbf file.

    bbox: (south, west, north, east) bounding box filter, or None to accept all.
    Returns a list of segment dicts with keys: ax, ay, bx, by, bearing, length, highway.
    """
    try:
        import osmium
    except ImportError:
        print(
            "ERROR: osmium is not installed.\n"
            "Install it with:  pip install osmium\n"
            "or:               pip install osmium-tool",
            file=sys.stderr,
        )
        sys.exit(1)

    s, w, n, e = bbox if bbox else (-90, -180, 90, 180)

    segments: list[dict] = []

    class _RoadHandler(osmium.SimpleHandler):
        def way(self, way) -> None:
            highway = way.tags.get("highway", "")
            if highway not in _ROAD_TYPES:
                return
            if way.tags.get("access") in ("private", "no"):
                return

            # Collect valid node locations (osmium sets lat=nan for missing nodes)
            pts: list[tuple[float, float]] = []
            for n_ref in way.nodes:
                if not n_ref.location.valid():
                    continue
                lat_pt = n_ref.location.lat
                lon_pt = n_ref.location.lon
                # Bbox filter
                if bbox and not (s <= lat_pt <= n and w <= lon_pt <= e):
                    pts = []
                    break
                pts.append((lat_pt, lon_pt))

            if len(pts) < 2:
                return

            for i in range(len(pts) - 1):
                la, loa = pts[i]
                lb, lob = pts[i + 1]
                ea, na_ = _latlon_to_enu(la, loa, lat0, lon0)
                eb, nb_ = _latlon_to_enu(lb, lob, lat0, lon0)
                length = math.hypot(eb - ea, nb_ - na_)
                if length < 0.5:
                    continue
                bearing = math.atan2(eb - ea, nb_ - na_)  # 0=north, clockwise
                segments.append({
                    "ax": ea, "ay": na_,
                    "bx": eb, "by": nb_,
                    "bearing": bearing,
                    "length": length,
                    "highway": highway,
                })

    handler = _RoadHandler()
    print(f"Parsing {pbf_path} …")
    # locations=True: osmium resolves node coordinates for ways automatically
    handler.apply_file(str(pbf_path), locations=True, idx="flex_mem")
    print(f"  {len(segments):,} road segments extracted")
    return segments


# ── SQLite build ──────────────────────────────────────────────────────────────

def _build_sqlite(
    segments: list[dict],
    lat0: float,
    lon0: float,
    bbox: tuple,
    db_path: Path,
) -> None:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # ── meta ──────────────────────────────────────────────────────────────────
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value REAL NOT NULL)")
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("lat0", lat0), ("lon0", lon0),
        ("bbox_s", bbox[0]), ("bbox_w", bbox[1]),
        ("bbox_n", bbox[2]), ("bbox_e", bbox[3]),
    ])

    # ── segments + R-Tree ─────────────────────────────────────────────────────
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
        seg_rows.append((i,
                         seg["ax"], seg["ay"], seg["bx"], seg["by"],
                         seg["bearing"], seg["length"], seg.get("highway")))
        rtree_rows.append((i,
                           min(seg["ax"], seg["bx"]), max(seg["ax"], seg["bx"]),
                           min(seg["ay"], seg["by"]), max(seg["ay"], seg["by"])))

    db.executemany("INSERT INTO segments VALUES (?,?,?,?,?,?,?,?)", seg_rows)
    db.executemany("INSERT INTO seg_rtree VALUES (?,?,?,?,?)", rtree_rows)
    print(f"  segments inserted: {len(seg_rows):,}")

    # ── nodes + edges for A* routing ──────────────────────────────────────────
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


# ── offline verify ────────────────────────────────────────────────────────────

def _verify(db_path: Path) -> None:
    """Quick sanity check — no network required."""
    if not db_path.exists():
        print(f"ERROR: {db_path} does not exist — run build first.", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    n_segs  = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    n_nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    n_edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    con.close()

    print(f"Road graph: {db_path}")
    print(f"  ENU origin  : lat0={meta.get('lat0'):.5f}  lon0={meta.get('lon0'):.5f}")
    print(f"  Bbox        : S={meta.get('bbox_s')}  W={meta.get('bbox_w')}"
          f"  N={meta.get('bbox_n')}  E={meta.get('bbox_e')}")
    print(f"  Segments    : {n_segs:,}")
    print(f"  Nodes       : {n_nodes:,}")
    print(f"  Edges       : {n_edges:,}")
    print(f"  File size   : {db_path.stat().st_size / 1_048_576:.1f} MB")

    if n_segs == 0:
        print("WARNING: no segments — road graph is empty.", file=sys.stderr)
    elif n_segs < 1_000:
        print(f"WARNING: only {n_segs} segments — bbox may be too small or wrong area.")
    else:
        print("OK — road graph looks healthy.")

    # Test a snap at the ENU origin
    import math as _math
    from app.core.map.map_matcher import MapMatcher
    lat0 = meta["lat0"]
    lon0 = meta["lon0"]
    try:
        mm = MapMatcher(db_path, lat0, lon0)
        result = mm.snap(0.0, 0.0, 0.0)  # snap origin, heading north
        if result.snapped:
            print(f"  Snap test   : OK — nearest road {result.distance_m:.1f} m away, "
                  f"bearing {_math.degrees(result.bearing_rad):.1f}°")
        else:
            print("  Snap test   : no road within 40 m of graph origin (may be water/park)")
    except Exception as exc:
        print(f"  Snap test   : SKIP ({exc})")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--pbf",    default=None,
                   help=".osm.pbf file from Geofabrik (required unless --verify)")
    p.add_argument("--bbox",   default=None,
                   help="south,west,north,east filter  e.g. 22.3,88.1,22.7,88.6  "
                        "(default: accept all nodes in the PBF)")
    p.add_argument("--lat0",   type=float, default=None,
                   help="ENU origin latitude  (default: bbox centre)")
    p.add_argument("--lon0",   type=float, default=None,
                   help="ENU origin longitude (default: bbox centre)")
    p.add_argument("--out",    default=str(_DB),
                   help=f"output .sqlite path  (default: {_DB})")
    p.add_argument("--verify", action="store_true",
                   help="verify an existing road_graph.sqlite and exit")
    args = p.parse_args()

    if args.verify:
        _verify(Path(args.out))
        return

    if not args.pbf:
        p.error("--pbf is required (path to .osm.pbf file)")

    pbf_path = Path(args.pbf)
    if not pbf_path.exists():
        print(f"ERROR: file not found: {pbf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse bbox
    bbox: tuple | None = None
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            p.error("--bbox must be south,west,north,east (4 values)")
        bbox = tuple(parts)
    else:
        bbox = _DEFAULT_BBOX
        print(f"No --bbox given — using default Kolkata demo area {bbox}")

    s, w, n, e = bbox
    lat0 = args.lat0 if args.lat0 is not None else (s + n) / 2
    lon0 = args.lon0 if args.lon0 is not None else (w + e) / 2
    print(f"ENU origin: lat0={lat0:.5f}  lon0={lon0:.5f}")

    segments = _parse_pbf(pbf_path, bbox, lat0, lon0)
    if not segments:
        print("ERROR: no road segments found — check --bbox or PBF file.", file=sys.stderr)
        sys.exit(1)

    _build_sqlite(segments, lat0, lon0, bbox, Path(args.out))
    print()
    _verify(Path(args.out))


if __name__ == "__main__":
    main()
