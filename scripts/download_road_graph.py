"""Download OSM road network for the map-matching area via Overpass API.

Saves a compact binary file: configs/road_graph.pkl
containing a list of road segments as ENU-projected polylines.

Run once before starting the server:
    python scripts/download_road_graph.py

Bounding box matches the bundled map.mbtiles:
    Kolkata region  87.751E - 89.119E, 22.117N - 23.106N

Road types included: motorway, trunk, primary, secondary, tertiary,
    unclassified, residential, living_street, service
(footpaths and pedestrian ways excluded — vehicles only)
"""

from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

import requests

_ROOT = Path(__file__).parent.parent

# Bounding box (south, west, north, east) — matches map.mbtiles
_BBOX = (22.117, 87.751, 23.106, 89.119)

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


def _latlon_to_enu(lat, lon, lat0, lon0):
    lat0_rad = math.radians(lat0)
    east  = math.radians(lon - lon0) * _R_EARTH * math.cos(lat0_rad)
    north = math.radians(lat - lat0) * _R_EARTH
    return east, north


def download(bbox: tuple[float, float, float, float], out_path: Path) -> None:
    s, w, n, e = bbox
    lat0, lon0 = (s + n) / 2, (w + e) / 2  # ENU origin = bbox centre

    print(f"Querying Overpass API for bbox {bbox} ...")
    query = f"""
[out:json][timeout:120];
(
  way["highway"]({s},{w},{n},{e});
);
out geom;
"""
    headers = {"User-Agent": "SIH2026-DeadReckoning/1.0 (research project)"}
    resp = requests.post(_OVERPASS_URL, data={"data": query},
                         headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()

    segments: list[dict] = []
    for way in data.get("elements", []):
        if way.get("type") != "way":
            continue
        tags = way.get("tags", {})
        highway = tags.get("highway", "")
        if highway not in _ROAD_TYPES:
            continue
        if tags.get("access") in ("private", "no"):
            continue

        geometry = way.get("geometry", [])
        if len(geometry) < 2:
            continue

        # Convert all nodes to ENU
        pts_enu = []
        for node in geometry:
            east, north = _latlon_to_enu(node["lat"], node["lon"], lat0, lon0)
            pts_enu.append((east, north))

        # Store as consecutive segments (pairs of ENU points)
        for i in range(len(pts_enu) - 1):
            a, b = pts_enu[i], pts_enu[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 0.5:  # skip degenerate segments < 0.5 m
                continue
            bearing = math.atan2(dx, dy)  # radians, 0=north, clockwise
            segments.append({
                "ax": a[0], "ay": a[1],
                "bx": b[0], "by": b[1],
                "bearing": bearing,
                "highway": highway,
                "length": length,
            })

    payload = {
        "lat0": lat0, "lon0": lon0,
        "bbox": bbox,
        "segments": segments,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"Saved {len(segments):,} road segments → {out_path}")
    print(f"ENU origin: lat0={lat0}, lon0={lon0}")


if __name__ == "__main__":
    out = _ROOT / "configs" / "road_graph.pkl"
    download(_BBOX, out)
