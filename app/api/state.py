"""Shared server state: filesystem paths and road-router singleton.

Both the HTTP routes and the WebSocket handler need access to the road router.
This module holds the mutable singleton so neither layer imports the other.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from app.core.navigation.router import RoadRouter

log = logging.getLogger(__name__)

# ── Filesystem paths ──────────────────────────────────────────────────────────
_ROOT      = Path(__file__).parent.parent.parent
MODELS_DIR = _ROOT / "models"

# TCN-GRU hybrid (16B, real frozen weights, window=40)
_TCN_GRU_DIR = MODELS_DIR / "tcn_gru_hybrid_for_app"
ONNX_PATH    = _TCN_GRU_DIR / "tcn_gru_hybrid.onnx"
META_PATH    = _TCN_GRU_DIR / "tcn_gru_hybrid_metadata.json"

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


async def startup_event() -> None:
    """FastAPI startup hook — pre-build the road router from the graph's own origin."""
    global router_loading
    if not ROAD_GRAPH.exists():
        log.warning("startup: road_graph.sqlite not found — offline routing unavailable")
        return

    import sqlite3 as _sqlite3
    try:
        con  = _sqlite3.connect(f"file:{ROAD_GRAPH}?mode=ro", uri=True)
        lat0 = float(con.execute("SELECT value FROM meta WHERE key='lat0'").fetchone()[0])
        lon0 = float(con.execute("SELECT value FROM meta WHERE key='lon0'").fetchone()[0])
        con.close()
    except Exception as exc:
        log.warning("startup: could not read road graph origin: %s — skipping pre-build", exc)
        return

    router_loading = True
    threading.Thread(
        target=build_road_router,
        args=(lat0, lon0),
        daemon=True,
        name="road-router-startup",
    ).start()
    log.info("startup: offline router build started (origin %.4f, %.4f)", lat0, lon0)
