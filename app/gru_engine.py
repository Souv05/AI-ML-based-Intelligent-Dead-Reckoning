"""On-device GRU-v2 speed estimator — runs ONNX model on a rolling 60-sample window.

Feature order (12 channels, from gru_v2_metadata.json):
  acc_x, acc_y, acc_z   [m/s²]
  gyro_x, gyro_y, gyro_z [rad/s]
  mag_x, mag_y, mag_z   [µT]
  roll, pitch, yaw       [degrees]
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime as ort

_WINDOW = 60
_N_FEAT = 12


class GRUEngine:
    def __init__(self, onnx_path: Path, metadata_path: Path) -> None:
        meta = json.loads(metadata_path.read_text())
        sc = meta["scaler"]
        self._x_mean = np.array(sc["x_mean"], dtype=np.float32)
        self._x_std  = np.array(sc["x_std"],  dtype=np.float32)
        self._y_mean: float = sc["y_mean"]
        self._y_std:  float = sc["y_std"]

        self._sess = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self._input_name  = meta["input_name"]   # "sensor_window"
        self._output_name = meta["output_name"]  # "speed_normalised"

        # Rolling buffer — deque keeps exactly WINDOW rows
        self._buf: deque[list[float]] = deque(maxlen=_WINDOW)

    def reset(self) -> None:
        """Clear the rolling window (call after a pothole/shock or sensor gap)."""
        self._buf.clear()

    def push(
        self,
        acc_x: float, acc_y: float, acc_z: float,
        gyro_x: float, gyro_y: float, gyro_z: float,
        mag_x: float, mag_y: float, mag_z: float,
        roll: float, pitch: float, yaw: float,
    ) -> float | None:
        """Append one sample and return speed (m/s) once the window is full."""
        self._buf.append([acc_x, acc_y, acc_z,
                          gyro_x, gyro_y, gyro_z,
                          mag_x, mag_y, mag_z,
                          roll, pitch, yaw])
        if len(self._buf) < _WINDOW:
            return None

        x = np.array(self._buf, dtype=np.float32)   # (60, 12)
        x = (x - self._x_mean) / self._x_std        # z-score per channel
        x = x[np.newaxis]                            # (1, 60, 12)

        out = self._sess.run([self._output_name], {self._input_name: x})
        y_norm = float(out[0][0])
        speed_ms = self._y_mean + y_norm * self._y_std
        return max(speed_ms, 0.0)
