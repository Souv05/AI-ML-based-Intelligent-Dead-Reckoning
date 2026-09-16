"""Speed estimator — runs a TCN-GRU (or plain GRU) ONNX model on a rolling window.

Window length and scaler are read from the metadata JSON so no code change
is needed when the model is updated.

Feature order (12 channels):
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

_N_FEAT = 12


class GRUEngine:
    def __init__(self, onnx_path: Path, metadata_path: Path) -> None:
        meta = json.loads(metadata_path.read_text())

        # Window length comes from metadata — models may differ (e.g. 40 vs 60)
        self._window: int = int(meta.get("sequence_length", meta.get("window_length", 60)))

        # Scaler — load from a companion scaler.json if metadata points to one,
        # otherwise fall back to an inline "scaler" block for legacy models.
        scaler_ref = meta.get("scaler", "")
        if isinstance(scaler_ref, dict):
            sc = scaler_ref
        else:
            # scaler_ref may be "scaler.json" or "scaler.json (note...)" — take the first token
            fname = str(scaler_ref).split()[0] if scaler_ref else "scaler.json"
            if not fname.endswith(".json"):
                fname = "scaler.json"
            sc_path = metadata_path.parent / fname
            if not sc_path.exists():
                sc_path = metadata_path.parent / "scaler.json"
            sc = json.loads(sc_path.read_text())

        self._x_mean = np.array(sc["x_mean"], dtype=np.float32)
        self._x_std  = np.array(sc["x_std"],  dtype=np.float32)
        self._y_mean: float = float(sc["y_mean"])   # bias correction already baked in
        self._y_std:  float = float(sc["y_std"])

        self._sess = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self._input_name  = meta["input_name"]
        self._output_name = meta["output_name"]

        self._buf: deque[list[float]] = deque(maxlen=self._window)

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
        if len(self._buf) < self._window:
            return None

        x = np.array(self._buf, dtype=np.float32)    # (window, 12)
        x = (x - self._x_mean) / self._x_std         # z-score per channel
        x = x[np.newaxis]                             # (1, window, 12)

        out = self._sess.run([self._output_name], {self._input_name: x})
        y_norm = float(out[0][0])
        speed_ms = self._y_mean + y_norm * self._y_std
        return max(speed_ms, 0.0)
