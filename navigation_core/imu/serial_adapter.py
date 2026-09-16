"""Serial (UART) IMU adapter.

Reads line-delimited JSON or CSV frames from a serial port.
Designed for microcontroller IMUs (Arduino, STM32, ESP32, VectorNav, etc.)
that stream data over USB-serial or hardware UART.

Supported wire formats (auto-detected per line):
    1. JSON line:  {"timestamp":1.23,"ax":0.1,"ay":0.0,"az":9.8,"gx":0.0,"gy":0.0,"gz":0.01}
    2. CSV line:   1.23,0.1,0.0,9.8,0.0,0.0,0.01   (columns set by csv_columns)

Default csv_columns order matches most Arduino IMU sketches:
    timestamp, ax, ay, az, gx, gy, gz

Requires: pyserial  (pip install pyserial)

Usage:
    adapter = SerialIMUAdapter(port="COM3", baud=115200, accel_unit="g", gyro_unit="deg/s")
    for sample in adapter.stream():
        engine.push(sample)

To find available ports:
    python -m serial.tools.list_ports
"""

from __future__ import annotations

import json
import time
from typing import Iterator

from .adapter import IMUAdapter
from .standard_imu import StandardIMUSample
from ..preprocessing.units import accel_to_ms2, gyro_to_rad_s

_DEFAULT_CSV_COLUMNS = ["timestamp", "ax", "ay", "az", "gx", "gy", "gz"]


class SerialIMUAdapter(IMUAdapter):
    def __init__(
        self,
        port: str,
        baud: int = 115200,
        accel_unit: str = "m/s2",
        gyro_unit:  str = "rad/s",
        source_frame: str = "FRD",
        accel_bias: tuple[float, float, float] = (0.0, 0.0, 0.0),
        gyro_bias:  tuple[float, float, float] = (0.0, 0.0, 0.0),
        csv_columns: list[str] | None = None,
        timeout_s: float = 2.0,
        add_host_timestamp: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        port              : Serial port name, e.g. "COM3", "/dev/ttyUSB0"
        baud              : Baud rate (must match the sender)
        accel_unit        : "m/s2" or "g"
        gyro_unit         : "rad/s" or "deg/s"
        source_frame      : Canonical frame of the sensor ("FRD", "FLU", etc.)
        accel_bias        : (bx, by, bz) in m/s² — subtracted after unit conversion
        gyro_bias         : (bx, by, bz) in rad/s
        csv_columns       : Column order for CSV-format lines (default: timestamp,ax,ay,az,gx,gy,gz)
        timeout_s         : Serial read timeout in seconds
        add_host_timestamp: If True and no 'timestamp' field in packet, use host time.time()
        """
        self._port              = port
        self._baud              = baud
        self._accel_unit        = accel_unit
        self._gyro_unit         = gyro_unit
        self._frame             = source_frame
        self._accel_bias        = accel_bias
        self._gyro_bias         = gyro_bias
        self._csv_columns       = csv_columns or _DEFAULT_CSV_COLUMNS
        self._timeout_s         = timeout_s
        self._add_host_ts       = add_host_timestamp
        self._last_t: float | None = None

    def convert(self, raw: dict) -> StandardIMUSample:
        if "timestamp" not in raw and self._add_host_ts:
            raw = dict(raw, timestamp=time.time())

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
            source = f"serial:{self._port}",
        )

    def _parse_line(self, line: str) -> dict | None:
        """Parse one text line as JSON or CSV. Returns None on parse failure."""
        line = line.strip()
        if not line:
            return None
        # Try JSON first
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return None
        # Try CSV
        parts = line.split(",")
        if len(parts) < len(self._csv_columns):
            return None
        try:
            return {col: float(parts[i]) for i, col in enumerate(self._csv_columns)}
        except ValueError:
            return None   # header row or garbage

    def stream(self) -> Iterator[StandardIMUSample]:
        """Blocking generator — yields samples as serial lines arrive."""
        try:
            import serial
        except ImportError:
            raise ImportError(
                "pyserial is required for SerialIMUAdapter. "
                "Install with: pip install pyserial"
            )

        print(f"[SerialIMUAdapter] Opening {self._port} @ {self._baud} baud …")
        with serial.Serial(self._port, self._baud, timeout=self._timeout_s) as ser:
            print(f"[SerialIMUAdapter] Connected. Streaming …")
            while True:
                try:
                    raw_line = ser.readline().decode("utf-8", errors="replace")
                except Exception:
                    continue
                raw = self._parse_line(raw_line)
                if raw is None:
                    continue
                try:
                    yield self.convert(raw)
                except (KeyError, ValueError):
                    continue   # missing required field — skip

    def reset(self) -> None:
        self._last_t = None
