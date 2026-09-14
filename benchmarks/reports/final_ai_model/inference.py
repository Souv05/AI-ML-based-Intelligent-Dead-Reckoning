"""
GRU v2 — Frozen Inference Module
Step 16E freeze. Do NOT modify this file or the checkpoint.
"""

import json
import numpy as np
from pathlib import Path

# Torch is optional at import time; loaded lazily so callers can import the
# module without GPU/CUDA being present (e.g., unit tests that mock predict).
_TORCH_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:
    pass

# ── Model ────────────────────────────────────────────────────────────────────

class GRURegressor(nn.Module if _TORCH_AVAILABLE else object):
    """Exact architecture as trained in Step 16A (GRU2-E05c-T60)."""

    def __init__(self, input_size=12, hidden_size=128, num_layers=2, dropout=0.2):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.gru(x)
        return self.head(out[:, -1, :]).squeeze(-1)


# ── Loader ───────────────────────────────────────────────────────────────────

_PACKAGE_DIR = Path(__file__).resolve().parent

_scaler  = None
_model   = None
_device  = None


def _load_assets(package_dir=None):
    global _scaler, _model, _device
    if _model is not None:
        return

    if not _TORCH_AVAILABLE:
        raise ImportError("PyTorch is required for inference.")

    d = Path(package_dir) if package_dir else _PACKAGE_DIR
    _scaler = json.load(open(d / "scaler.json"))

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    m = GRURegressor(input_size=12, hidden_size=128, num_layers=2, dropout=0.2)
    state = torch.load(d / "gru_v2_best.pt", map_location=_device)
    if isinstance(state, dict) and "model_state_dict" in state:
        m.load_state_dict(state["model_state_dict"])
    else:
        m.load_state_dict(state)
    m.to(_device)
    m.eval()
    _model = m


# ── Public API ────────────────────────────────────────────────────────────────

def predict_forward_speed(window, package_dir=None):
    """
    Predict forward speed from one T=60 IMU window.

    Parameters
    ----------
    window : array-like, shape (60, 12)
        Raw IMU channels in the order defined in feature_config.json:
        [acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z,
         mag_x, mag_y, mag_z, roll, pitch, yaw]
    package_dir : str or Path, optional
        Path to the frozen package directory.
        Defaults to the directory containing this file.

    Returns
    -------
    float
        Predicted forward speed in m/s.
    """
    _load_assets(package_dir)

    arr = np.asarray(window, dtype=np.float32)
    if arr.shape != (60, 12):
        raise ValueError(f"Expected window shape (60, 12), got {arr.shape}")

    x_mean = np.array(_scaler["x_mean"], dtype=np.float32)
    x_std  = np.array(_scaler["x_std"],  dtype=np.float32)
    y_mean = float(_scaler["y_mean"])
    y_std  = float(_scaler["y_std"])

    arr_norm = (arr - x_mean) / x_std
    t = torch.from_numpy(arr_norm[np.newaxis]).to(_device)   # (1, 60, 12)

    with torch.no_grad():
        out_norm = _model(t).item()

    speed_mps = out_norm * y_std + y_mean
    return float(speed_mps)


def predict_forward_speed_batch(windows, package_dir=None):
    """
    Predict forward speed for a batch of T=60 IMU windows.

    Parameters
    ----------
    windows : array-like, shape (N, 60, 12)

    Returns
    -------
    np.ndarray, shape (N,)  — forward speeds in m/s
    """
    _load_assets(package_dir)

    arr = np.asarray(windows, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[1:] != (60, 12):
        raise ValueError(f"Expected shape (N, 60, 12), got {arr.shape}")

    x_mean = np.array(_scaler["x_mean"], dtype=np.float32)
    x_std  = np.array(_scaler["x_std"],  dtype=np.float32)
    y_mean = float(_scaler["y_mean"])
    y_std  = float(_scaler["y_std"])

    arr_norm = (arr - x_mean) / x_std
    t = torch.from_numpy(arr_norm).to(_device)

    with torch.no_grad():
        out_norm = _model(t).cpu().numpy()

    return (out_norm * y_std + y_mean).astype(np.float64)
