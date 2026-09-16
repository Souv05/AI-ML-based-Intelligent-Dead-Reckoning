"""CSV external-IMU adapter.

Reads a CSV file (or any iterable of dicts) with columns:
    timestamp, ax, ay, az, gx, gy, gz
    [optional: mx, my, mz, roll, pitch, yaw]

Unit declarations tell the adapter what to convert from:
    accel_unit : "m/s2" (default) or "g"
    gyro_unit  : "rad/s" (default) or "deg/s"

Example CSV:
    timestamp,ax,ay,az,gx,gy,gz
    0.000,0.12,-0.05,9.80,0.002,-0.001,0.010
    0.010,0.13,-0.04,9.79,0.003,-0.001,0.011

Usage:
    adapter = CSVIMUAdapter(accel_unit="g", gyro_unit="deg/s")
    for sample in adapter.from_file("external_imu.csv"):
        ...  # StandardIMUSample in FRD, m/s², rad/s
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterator

from .adapter import IMUAdapter
from .standard_imu import StandardIMUSample
from ..preprocessing.units import accel_to_ms2, gyro_to_rad_s


class CSVIMUAdapter(IMUAdapter):
    def __init__(
        self,
        accel_unit: str = "m/s2",
        gyro_unit:  str = "rad/s",
        source_frame: str = "FRD",
        accel_bias: tuple[float, float, float] = (0.0, 0.0, 0.0),
        gyro_bias:  tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self._accel_unit  = accel_unit
        self._gyro_unit   = gyro_unit
        self._source_frame = source_frame
        self._accel_bias  = accel_bias
        self._gyro_bias   = gyro_bias
        self._last_t: float | None = None

    def convert(self, raw: dict) -> StandardIMUSample:
        t = float(raw["timestamp"])
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
            frame  = self._source_frame,
            source = "csv",
        )

    def from_file(self, path: str | Path) -> Iterator[StandardIMUSample]:
        """Lazily yield StandardIMUSample from a CSV file."""
        self._last_t = None
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield self.convert(row)

    def reset(self) -> None:
        self._last_t = None
