"""Sensor bias calibration.

Calibration belongs to the sensor/session, not the model.
Call estimate_static() with N stationary samples to compute biases,
or load them from a JSON file saved from a previous session.

Corrects:
    accel_corrected = accel_raw - accel_bias
    gyro_corrected  = gyro_raw  - gyro_bias

Accel bias is estimated as (mean - [0,0,g]) from a flat-stationary window.
Gyro bias is the mean of all gyro readings during the stationary window.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

from ..imu.standard_imu import StandardIMUSample

_G = 9.80665


class IMUCalibration:
    def __init__(self) -> None:
        self.accel_bias = np.zeros(3, dtype=np.float64)
        self.gyro_bias  = np.zeros(3, dtype=np.float64)

    def estimate_static(
        self,
        samples: Iterable[StandardIMUSample],
        gravity_axis: str = "z",   # which axis points up/down when stationary
    ) -> None:
        """Estimate biases from a window of stationary samples."""
        a_buf, g_buf = [], []
        for s in samples:
            a_buf.append([s.ax, s.ay, s.az])
            g_buf.append([s.gx, s.gy, s.gz])

        if not a_buf:
            return

        a_mean = np.mean(a_buf, axis=0)
        g_mean = np.mean(g_buf, axis=0)

        # Accel bias = mean - expected gravity vector
        # In FRD frame, gravity is [0, 0, +9.80665] (down = +Z)
        expected = np.array([0.0, 0.0, _G])
        self.accel_bias = a_mean - expected
        self.gyro_bias  = g_mean

    def apply(self, s: StandardIMUSample) -> StandardIMUSample:
        """Return a new sample with biases subtracted."""
        return StandardIMUSample(
            timestamp=s.timestamp, dt=s.dt,
            ax=s.ax - self.accel_bias[0],
            ay=s.ay - self.accel_bias[1],
            az=s.az - self.accel_bias[2],
            gx=s.gx - self.gyro_bias[0],
            gy=s.gy - self.gyro_bias[1],
            gz=s.gz - self.gyro_bias[2],
            mx=s.mx, my=s.my, mz=s.mz,
            roll=s.roll, pitch=s.pitch, yaw=s.yaw,
            frame=s.frame, source=s.source,
        )

    def save(self, path: str | Path) -> None:
        data = {
            "accel_bias": self.accel_bias.tolist(),
            "gyro_bias":  self.gyro_bias.tolist(),
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text())
        self.accel_bias = np.array(data["accel_bias"], dtype=np.float64)
        self.gyro_bias  = np.array(data["gyro_bias"],  dtype=np.float64)
