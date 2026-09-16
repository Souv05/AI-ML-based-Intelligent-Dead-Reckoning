"""Dead-Reckoning Navigation Server — entry point.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

The actual logic lives in:
    app/api/fastapi/routes.py   — HTTP endpoints (/health, /route, /graph)
    app/api/websocket/navigation.py — WebSocket handler (/ws/navigation)
    app/api/state.py            — shared road-router singleton + paths
    app/core/                   — EKF, GRU, IMU filter, map matcher, router
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import state
from app.api.fastapi.routes import router
from app.api.websocket.navigation import ws_navigation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Dead-Reckoning Navigation Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    await state.startup_event()


app.include_router(router)
app.add_api_websocket_route("/ws/navigation", ws_navigation)
