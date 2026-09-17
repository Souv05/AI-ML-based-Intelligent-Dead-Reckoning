"""Shared server state: filesystem paths and road-router singleton.

Both the HTTP routes and the WebSocket handler need access to the road router.
This module holds the mutable singleton so neither layer imports the other.
"""

from __future__ import annotations

import logging
import os
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from app.core.navigation.router import RoadRouter

log = logging.getLogger(__name__)

# Set ROAD_GRAPH_URL on Render (or any host) to the public URL of your
# pre-built road_graph.sqlite (e.g. a GitHub Release asset).
# The file is downloaded once at startup if not already present.
# Example:
#   ROAD_GRAPH_URL=https://github.com/<org>/<repo>/releases/download/v1/road_graph.sqlite
ROAD_GRAPH_URL: str = os.environ.get("ROAD_GRAPH_URL", "")

# ── Filesystem paths ──────────────────────────────────────────────────────────
_ROOT      = Path(__file__).parent.parent.parent
MODELS_DIR = _ROOT / "models"

# GRU v2 (16E frozen, window=60, GRU2-E05c-T60 — primary server model)
ONNX_PATH = MODELS_DIR / "exported" / "onnx" / "gru_v2.onnx"
META_PATH = MODELS_DIR / "gru" / "gru_v2_metadata.json"

ROAD_GRAPH = _ROOT / "configs" / "road_graph.sqlite"

PUBLISH_DT = 1.0 / 10   # 10 Hz output rate

# ── Road-router singleton ─────────────────────────────────────────────────────
# Assignment is atomic under the GIL; no explicit lock needed.
road_router: Optional[RoadRouter] = None
router_loading: bool = False


def build_road_router(lat0: float, lon0: float) -> None:
    """Build (or rebuild) the road router in the calling thread."""
    global road_router, router_loading
    try:
        log.info("Building offline road router in background …")
        r = RoadRouter(ROAD_GRAPH, lat0, lon0)
        road_router = r
        log.info("Offline road router ready")
    except Exception as exc:
        log.warning("Offline road router failed: %s", exc)
    finally:
        router_loading = False


def _ensure_road_graph() -> None:
    """Download road_graph.sqlite from ROAD_GRAPH_URL if not already present.

    Called in a background thread at startup.  After a successful download the
    road router is built immediately so the server doesn't need a restart.
    """
    if ROAD_GRAPH.exists():
        log.info("Road graph already present: %.1f MB", ROAD_GRAPH.stat().st_size / 1e6)
        _maybe_build_router()
        return
    if not ROAD_GRAPH_URL:
        log.warning(
            "road_graph.sqlite not found and ROAD_GRAPH_URL is not set.\n"
            "  Map matching and /graph will be disabled.\n"
            "  Set ROAD_GRAPH_URL to a public download URL and redeploy."
        )
        return

    log.info("Downloading road_graph.sqlite from %s …", ROAD_GRAPH_URL)
    ROAD_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROAD_GRAPH.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(ROAD_GRAPH_URL, tmp)
        tmp.rename(ROAD_GRAPH)
        size_mb = ROAD_GRAPH.stat().st_size / 1_048_576
        log.info("Road graph downloaded: %.1f MB → %s", size_mb, ROAD_GRAPH)
        _maybe_build_router()
    except Exception as exc:
        log.error("Failed to download road graph: %s — map matching disabled", exc)
        if tmp.exists():
            tmp.unlink()


def _maybe_build_router() -> None:
    """Build the road router if not already built/building."""
    global router_loading
    if road_router is not None or router_loading:
        return
    try:
        import sqlite3 as _sqlite3
        con  = _sqlite3.connect(f"file:{ROAD_GRAPH}?mode=ro", uri=True)
        lat0 = float(con.execute("SELECT value FROM meta WHERE key='lat0'").fetchone()[0])
        lon0 = float(con.execute("SELECT value FROM meta WHERE key='lon0'").fetchone()[0])
        con.close()
    except Exception as exc:
        log.warning("Could not read road graph origin: %s", exc)
        return
    router_loading = True
    threading.Thread(
        target=build_road_router,
        args=(lat0, lon0),
        daemon=True,
        name="road-router-build",
    ).start()
    log.info("Road router build started (origin %.4f, %.4f)", lat0, lon0)


async def startup_event() -> None:
    """FastAPI startup hook.

    Spawns a single background thread that:
      1. Downloads road_graph.sqlite from ROAD_GRAPH_URL if the file is absent.
      2. Builds the RoadRouter once the file is present.

    The server accepts connections immediately; /graph returns 503 until the
    router is ready (typically 30-120 s after a cold Render start).
    """
    threading.Thread(
        target=_ensure_road_graph, daemon=True, name="road-graph-init"
    ).start()
    log.info("startup: road graph initialisation thread launched")
