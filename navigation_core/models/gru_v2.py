"""GRU-v2 speed estimator — sensor-agnostic interface.

Accepts StandardIMUSample objects.  Never knows about phone, CSV, or any
specific sensor.  Input features are derived from the canonical FRD frame.

Feature vector (6 channels, matches frozen model training order):
    [ax, ay, az, gx, gy, gz]   — FRD frame, m/s², rad/s

If magnetometer and orientation are present they are NOT fed to this model
(frozen GRU-v2 was trained on 6 IMU channels only).  A future GRU-v3 may
optionally include them.

Model metadata JSON must contain:
    sequence_length (or window_length)
    input_name, output_name
    scaler → {x_mean, x_std, y_mean, y_std}  (or companion scaler.json)
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ..imu.standard_imu import StandardIMUSample

_N_FEAT = 12  # ax, ay, az, gx, gy, gz, mx, my, mz, roll, pitch, yaw


class GRUv2:
    def __init__(self, onnx_path: Path, metadata_path: Path) -> None:
        meta = json.loads(metadata_path.read_text())
        self._window: int = int(
            meta.get("sequence_length", meta.get("window_length", 60))
        )

        # Load scaler
        scaler_ref = meta.get("scaler", "")
        if isinstance(scaler_ref, dict):
            sc = scaler_ref
        else:
            fname = str(scaler_ref).split()[0] if scaler_ref else "scaler.json"
            if not fname.endswith(".json"):
                fname = "scaler.json"
            sc_path = metadata_path.parent / fname
            if not sc_path.exists():
                sc_path = metadata_path.parent / "scaler.json"
            sc = json.loads(sc_path.read_text())

        x_mean = np.array(sc["x_mean"], dtype=np.float32)
        x_std  = np.array(sc["x_std"],  dtype=np.float32)
        self._x_mean = x_mean[:_N_FEAT]
        self._x_std  = x_std[:_N_FEAT]
        self._y_mean: float = float(sc["y_mean"])
        self._y_std:  float = float(sc["y_std"])

        self._sess = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self._input_name  = meta["input_name"]
        self._output_name = meta["output_name"]
        self._buf: deque[list[float]] = deque(maxlen=self._window)

        # Frozen model version tag (for logging/debugging)
        self.version: str = meta.get("version", "v2")
        self.feature_order: list[str] = [
            "ax", "ay", "az", "gx", "gy", "gz",
            "mx", "my", "mz", "roll", "pitch", "yaw",
        ]

    def push(self, sample: StandardIMUSample) -> float | None:
        """Append one StandardIMUSample; return speed (m/s) once window is full."""
        import math
        self._buf.append([
            sample.ax, sample.ay, sample.az,
            sample.gx, sample.gy, sample.gz,
            sample.mx, sample.my, sample.mz,
            0.0 if math.isnan(sample.roll)  else sample.roll,
            0.0 if math.isnan(sample.pitch) else sample.pitch,
            0.0 if math.isnan(sample.yaw)   else sample.yaw,
        ])
        if len(self._buf) < self._window:
            return None

        x = np.array(self._buf, dtype=np.float32)        # (window, 6)
        x = (x - self._x_mean) / (self._x_std + 1e-8)   # z-score
        x = x[np.newaxis]                                  # (1, window, 6)

        out = self._sess.run([self._output_name], {self._input_name: x})
        y_norm = float(out[0][0])
        speed_ms = self._y_mean + y_norm * self._y_std
        return max(speed_ms, 0.0)

    def reset(self) -> None:
        self._buf.clear()

    @property
    def window_size(self) -> int:
        return self._window

    @property
    def is_warm(self) -> bool:
        return len(self._buf) >= self._window
