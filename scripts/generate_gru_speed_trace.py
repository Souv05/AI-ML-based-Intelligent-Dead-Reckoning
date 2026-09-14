"""
Pre-compute a 640-point GRU speed trace from the real Vw02 test sequence.
Output: assets/models/gru_speed_trace.json  (bundled in the Flutter app)

The trace maps to IdrSimulation.progress (0..1) with 640 evenly-spaced
samples, so the demo shows real GRU model output for every frame.
"""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd

REPO_ROOT   = Path(r"D:\SIH 2026")
MODEL_PATH  = REPO_ROOT / "gru_v2_flutter_integration" / "assets" / "models" / "gru_v2.onnx"
SCALER_PATH = REPO_ROOT / "gru_v2_flutter_integration" / "assets" / "models" / "scaler.json"
PQ_PATH     = REPO_ROOT / "data" / "processed" / "test" / "Vw02.parquet"
OUT_PATH    = REPO_ROOT / "intelligent_dead_reckoning" / "assets" / "models" / "gru_speed_trace.json"

N_SIM_SAMPLES = 640   # must match IdrSimulation.samples
WINDOW_LEN    = 60
NUM_CHANNELS  = 12
FEATURES = ["acc_x","acc_y","acc_z","gyro_x","gyro_y","gyro_z",
            "mag_x","mag_y","mag_z","roll","pitch","yaw"]

# --- load scaler ---
sc    = json.loads(SCALER_PATH.read_text())
X_MEAN = np.array(sc["x_mean"], dtype=np.float32)
X_STD  = np.array(sc["x_std"],  dtype=np.float32)
Y_MEAN = float(sc["y_mean"])
Y_STD  = float(sc["y_std"])

# --- load model ---
session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
IN  = session.get_inputs()[0].name
OUT = session.get_outputs()[0].name

# --- load sequence ---
df = pd.read_parquet(PQ_PATH)
raw = df[FEATURES].values.astype(np.float32)  # (N, 12)
ref_speed = df["reference_speed"].values.astype(np.float32)

total_windows = len(raw) - WINDOW_LEN + 1
print(f"Vw02: {len(raw)} rows → {total_windows} windows")

# pick 640 evenly-spaced window start indices
indices = np.linspace(0, total_windows - 1, N_SIM_SAMPLES, dtype=int)

speeds_mps  = []
speeds_kmh  = []
gt_kmh      = []

for idx in indices:
    window = raw[idx : idx + WINDOW_LEN]                      # (60,12)
    x_norm = ((window - X_MEAN) / X_STD).reshape(1, WINDOW_LEN, NUM_CHANNELS)
    raw_out = session.run([OUT], {IN: x_norm})
    mps = Y_MEAN + float(raw_out[0][0]) * Y_STD
    mps = max(0.0, mps)
    speeds_mps.append(round(mps, 4))
    speeds_kmh.append(round(mps * 3.6, 4))
    gt_kmh.append(round(float(ref_speed[idx + WINDOW_LEN - 1]) * 3.6, 4))

print(f"GRU speed range: {min(speeds_mps):.2f} – {max(speeds_mps):.2f} m/s")
print(f"GT  speed range: {min(gt_kmh)/3.6:.2f} – {max(gt_kmh)/3.6:.2f} m/s")

# --- write asset ---
payload = {
    "source_sequence": "Vw02",
    "model": "GRU-v2 (GRU2-E05c-T60)",
    "n_samples": N_SIM_SAMPLES,
    "window_length": WINDOW_LEN,
    "note": "640 speed values (m/s) evenly spaced along Vw02. "
            "Index i corresponds to IdrSimulation.progress = i/639.",
    "speeds_mps": speeds_mps,
    "gt_speeds_kmh": gt_kmh,    # reference only — not loaded by the app
}

OUT_PATH.write_text(json.dumps(payload))
print(f"Written → {OUT_PATH}  ({OUT_PATH.stat().st_size//1024} KB)")
