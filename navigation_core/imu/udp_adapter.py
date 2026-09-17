"""UDP IMU adapter.

Listens on a UDP socket for JSON datagrams from an external IMU sender.
Each datagram is one JSON object with at minimum:
    timestamp, ax, ay, az, gx, gy, gz

Optional fields: mx, my, mz, roll, pitch, yaw

Supports any unit/frame combination via constructor args (same as CSVIMUAdapter).

Example sender (Python, on the IMU host):
    import socket, json, time
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        pkt = {"timestamp": time.time(), "ax": 0.1, "ay": 0.0, "az": 9.8,
               "gx": 0.0, "gy": 0.0, "gz": 0.01}
        sock.sendto(json.dumps(pkt).encode(), ("192.168.1.100", 5005))
        time.sleep(0.01)  # 100 Hz

Usage (blocking stream):
    adapter = UDPIMUAdapter(host="0.0.0.0", port=5005)
    for sample in adapter.stream():
        engine.push(sample)

Usage (async — yields samples as they arrive, call from asyncio):
    async for sample in adapter.astream():
        engine.push(sample)
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from typing import Iterator

from .adapter import IMUAdapter
from .standard_imu import StandardIMUSample
from ..preprocessing.units import accel_to_ms2, gyro_to_rad_s

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 5005
_BUFSIZE = 4096


class UDPIMUAdapter(IMUAdapter):
    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        accel_unit: str = "m/s2",
        gyro_unit:  str = "rad/s",
        source_frame: str = "FRD",
        accel_bias: tuple[float, float, float] = (0.0, 0.0, 0.0),
        gyro_bias:  tuple[float, float, float] = (0.0, 0.0, 0.0),
        timeout_s: float = 5.0,
    ) -> None:
        self._host        = host
        self._port        = port
        self._accel_unit  = accel_unit
        self._gyro_unit   = gyro_unit
        self._frame       = source_frame
        self._accel_bias  = accel_bias
        self._gyro_bias   = gyro_bias
        self._timeout_s   = timeout_s
        self._last_t: float | None = None

    def convert(self, raw: dict) -> StandardIMUSample:
        t  = float(raw["timestamp"])
        dt = (t - self._last_t) if self._last_t is not None else 0.01
        dt = max(0.001, min(dt, 0.5))
        self._last_t = t

        ax = accel_to_ms2(float(raw["ax"]), self._accel_unit) - self._accel_bias[0]
        ay = accel_to_ms2(float(raw["ay"]), self._accel_unit) - self._accel_bias[1]
        az = accel_to_ms2(float(raw["az"]), self._accel_unit) - self._accel_bias[2]
        gx = gyro_to_rad_s(float(raw["gx"]), self._gyro_unit) - self._gyro_bias[0]
        gy = gyro_to_rad_s(float(raw["gy"]), self._gyro_unit) - self._gyro_bias[1]
        gz = gyro_to_rad_s(float(raw["gz"]), self._gyro_unit) - self._gyro_bias[2]

        return StandardIMUSample(
            timestamp = t,
            dt        = dt,
            ax=ax, ay=ay, az=az,
            gx=gx, gy=gy, gz=gz,
            mx    = float(raw.get("mx", 0.0) or 0.0),
            my    = float(raw.get("my", 0.0) or 0.0),
            mz    = float(raw.get("mz", 0.0) or 0.0),
            roll  = float(raw["roll"])  if "roll"  in raw else float("nan"),
            pitch = float(raw["pitch"]) if "pitch" in raw else float("nan"),
            yaw   = float(raw["yaw"])   if "yaw"   in raw else float("nan"),
            frame  = self._frame,
            source = f"udp:{self._host}:{self._port}",
        )

    def stream(self) -> Iterator[StandardIMUSample]:
        """Blocking generator — yields samples as UDP datagrams arrive."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(self._timeout_s)
        sock.bind((self._host, self._port))
        print(f"[UDPIMUAdapter] Listening on {self._host}:{self._port} …")
        try:
            while True:
                try:
                    data, _ = sock.recvfrom(_BUFSIZE)
                    raw = json.loads(data.decode("utf-8"))
                    yield self.convert(raw)
                except socket.timeout:
                    continue   # keep waiting
                except json.JSONDecodeError:
                    continue   # malformed packet — skip
        finally:
            sock.close()

    async def astream(self):
        """Async generator — yields samples without blocking the event loop."""
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        sock.bind((self._host, self._port))
        print(f"[UDPIMUAdapter] Async listening on {self._host}:{self._port} …")
        try:
            while True:
                data = await loop.sock_recv(sock, _BUFSIZE)
                try:
                    raw = json.loads(data.decode("utf-8"))
                    yield self.convert(raw)
                except json.JSONDecodeError:
                    continue
        finally:
            sock.close()

    def reset(self) -> None:
        self._last_t = None
