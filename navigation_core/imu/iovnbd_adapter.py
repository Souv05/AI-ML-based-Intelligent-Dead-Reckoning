"""IO-VNBD dataset adapter.

Converts a loaded PhoneLog (from app.core.iovnbd.loader) into a stream of
StandardIMUSample objects — exactly the same contract as PhoneIMUAdapter and
CSVIMUAdapter.

The dataset phone CSV already has:
    acc_x, acc_y, acc_z   m/s²  (raw accelerometer, gravity included)
    gyro_x, gyro_y, gyro_z rad/s
    mag_x, mag_y, mag_z   µT    (optional — present in most trips)
    ori_yaw, ori_pitch, ori_roll  degrees  (optional)
    t                     seconds from session start (filled by loader)

No unit conversion needed — the loader already standardised them.
"""

from __future__ import annotations

import math
from typing import Iterator

import numpy as np

from .standard_imu import StandardIMUSample


class IOVNBDAdapter:
    """Yield StandardIMUSample from an IO-VNBD PhoneLog."""

    def __init__(self, source_label: str = "iovnbd") -> None:
        self._source = source_label

    def stream(self, phone_log) -> Iterator[StandardIMUSample]:
        """Lazily yield one StandardIMUSample per row in the PhoneLog."""
        df = phone_log.df
        t_arr = df["t"].to_numpy(dtype=float)

        has_mag = all(c in df.columns for c in ("mag_x", "mag_y", "mag_z"))
        has_ori = all(c in df.columns for c in ("ori_yaw", "ori_pitch", "ori_roll"))

        prev_t: float | None = None

        for i in range(len(df)):
            row = df.iloc[i]
            t = float(t_arr[i])
            dt = (t - prev_t) if prev_t is not None else 0.1
            dt = max(0.001, min(dt, 0.5))
            prev_t = t

            yield StandardIMUSample(
                timestamp = t,
                dt        = dt,
                ax = float(row.get("acc_x",  0.0) or 0.0),
                ay = float(row.get("acc_y",  0.0) or 0.0),
                az = float(row.get("acc_z",  0.0) or 0.0),
                gx = float(row.get("gyro_x", 0.0) or 0.0),
                gy = float(row.get("gyro_y", 0.0) or 0.0),
                gz = float(row.get("gyro_z", 0.0) or 0.0),
                mx = float(row.get("mag_x",  0.0) or 0.0) if has_mag else 0.0,
                my = float(row.get("mag_y",  0.0) or 0.0) if has_mag else 0.0,
                mz = float(row.get("mag_z",  0.0) or 0.0) if has_mag else 0.0,
                roll  = float(row.get("ori_roll",  float("nan")) or float("nan")) if has_ori else float("nan"),
                pitch = float(row.get("ori_pitch", float("nan")) or float("nan")) if has_ori else float("nan"),
                yaw   = float(row.get("ori_yaw",   float("nan")) or float("nan")) if has_ori else float("nan"),
                frame  = "phone_native",
                source = self._source,
            )
