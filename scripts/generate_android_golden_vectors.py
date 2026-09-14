"""
Generate golden test vectors for Android/Flutter GRU-v2 integration smoke-test.

Uses REAL windows from the frozen test split (same preprocessing as the
validated 19A pipeline) so the expected outputs are authoritative.

Run from the repo root or any directory:
    python scripts/generate_android_golden_vectors.py

Outputs to:
    D:/SIH 2026/android_handoff/test_vectors/
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import onnxruntime as ort

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(r"D:\SIH 2026")
MODEL_PATH = REPO_ROOT / "gru_v2_flutter_integration" / "assets" / "models" / "gru_v2.onnx"
SCALER_PATH = REPO_ROOT / "gru_v2_flutter_integration" / "assets" / "models" / "scaler.json"
TEST_DIR = REPO_ROOT / "data" / "processed" / "test"
OUT_DIR = REPO_ROOT / "android_handoff" / "test_vectors"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Load frozen scaler
# ---------------------------------------------------------------------------

scaler = json.loads(SCALER_PATH.read_text())
X_MEAN = np.array(scaler["x_mean"], dtype=np.float32)
X_STD  = np.array(scaler["x_std"],  dtype=np.float32)
Y_MEAN = float(scaler["y_mean"])
Y_STD  = float(scaler["y_std"])

print(f"Scaler loaded — y_mean={Y_MEAN:.4f}, y_std={Y_STD:.4f}")

# ---------------------------------------------------------------------------
# Load ONNX model
# ---------------------------------------------------------------------------

session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
INPUT_NAME  = session.get_inputs()[0].name
OUTPUT_NAME = session.get_outputs()[0].name
print(f"ONNX model loaded — input='{INPUT_NAME}', output='{OUTPUT_NAME}'")

# Validate names match gru_v2_speed_estimator.dart constants
assert INPUT_NAME  == "sensor_window",    f"Unexpected input name: {INPUT_NAME}"
assert OUTPUT_NAME == "speed_normalised", f"Unexpected output name: {OUTPUT_NAME}"

# ---------------------------------------------------------------------------
# Build 60-sample windows from the parquet raw data
# (the stored *_windows.npz used a 20-sample window from a different step)
# ---------------------------------------------------------------------------

WINDOWS_PER_FILE = 2
NUM_CHANNELS = 12
WINDOW_LEN   = 60

FEATURES = ["acc_x","acc_y","acc_z","gyro_x","gyro_y","gyro_z",
            "mag_x","mag_y","mag_z","roll","pitch","yaw"]

all_windows = []  # (x_raw: float32[60,12], y_true: float, seq_id: str, start_idx: int)

for pq_path in sorted(TEST_DIR.glob("*.parquet")):
    seq_id = pq_path.stem
    df = pd.read_parquet(pq_path)

    if len(df) < WINDOW_LEN:
        print(f"  {seq_id}: too short ({len(df)} rows), skipping")
        continue

    total_windows = len(df) - WINDOW_LEN + 1
    idxs = np.linspace(0, total_windows - 1, WINDOWS_PER_FILE, dtype=int)

    for start in idxs:
        window_df = df.iloc[start : start + WINDOW_LEN]
        x_raw = window_df[FEATURES].values.astype(np.float32)  # (60,12)
        # ground truth: reference_speed at the last sample of the window
        y_true = float(df["reference_speed"].iloc[start + WINDOW_LEN - 1])
        all_windows.append((x_raw, y_true, seq_id, int(start)))

    print(f"  {seq_id}: {len(df)} rows → {total_windows} possible windows, taking {WINDOWS_PER_FILE}")

print(f"\nTotal vectors to generate: {len(all_windows)}")

# ---------------------------------------------------------------------------
# Run inference and write JSON pairs
# ---------------------------------------------------------------------------

results_summary = []

for i, (x_raw, y_true, seq_id, win_idx) in enumerate(all_windows, start=1):
    assert x_raw.shape == (WINDOW_LEN, NUM_CHANNELS), x_raw.shape

    # Exact same preprocessing as the research pipeline
    x_norm = (x_raw - X_MEAN) / X_STD           # (60,12), float32
    x_in   = x_norm.reshape(1, WINDOW_LEN, NUM_CHANNELS)

    raw_out = session.run([OUTPUT_NAME], {INPUT_NAME: x_in})
    speed_norm = float(raw_out[0][0])
    speed_mps  = Y_MEAN + speed_norm * Y_STD

    label = f"input_{i:03d}"

    # --- input JSON (raw, un-normalised window so Dart side can verify it) ---
    (OUT_DIR / f"{label}.json").write_text(json.dumps({
        "vector_id":   i,
        "sequence_id": seq_id,
        "window_index_in_sequence": win_idx,
        "shape":       [WINDOW_LEN, NUM_CHANNELS],
        "dtype":       "float32",
        "feature_order": [
            "acc_x","acc_y","acc_z",
            "gyro_x","gyro_y","gyro_z",
            "mag_x","mag_y","mag_z",
            "roll","pitch","yaw"
        ],
        "note": "raw (un-normalised) sensor values; normalise with scaler.json before ONNX inference",
        "data": x_raw.tolist(),
    }, indent=2))

    # --- expected output JSON ---
    (OUT_DIR / f"expected_output_{i:03d}.json").write_text(json.dumps({
        "vector_id":        i,
        "sequence_id":      seq_id,
        "speed_normalised": round(speed_norm, 8),
        "speed_mps":        round(speed_mps,  6),
        "ground_truth_mps": round(float(y_true), 6),
        "abs_error_mps":    round(abs(speed_mps - float(y_true)), 6),
        "tolerance_mps":    0.05,
        "note": "Android output must match speed_mps within tolerance_mps",
    }, indent=2))

    results_summary.append({
        "vector": label,
        "seq": seq_id,
        "python_mps":    round(speed_mps, 4),
        "gt_mps":        round(float(y_true), 4),
        "error_mps":     round(abs(speed_mps - float(y_true)), 4),
    })

    print(f"  {label} ({seq_id}[{win_idx}]): {speed_mps:.4f} m/s  (GT {y_true:.4f})  err={abs(speed_mps-y_true):.4f}")

# ---------------------------------------------------------------------------
# Write manifest
# ---------------------------------------------------------------------------

manifest = {
    "model":        "GRU-v2 (GRU2-E05c-T60)",
    "model_file":   "gru_v2.onnx",
    "scaler_file":  "scaler.json",
    "onnx_input":   INPUT_NAME,
    "onnx_output":  OUTPUT_NAME,
    "window_length": WINDOW_LEN,
    "num_channels":  NUM_CHANNELS,
    "y_mean": Y_MEAN,
    "y_std":  Y_STD,
    "num_vectors": len(all_windows),
    "tolerance_mps": 0.05,
    "preprocessing": "z-score: x_norm = (x_raw - x_mean) / x_std  (per channel, from scaler.json)",
    "postprocessing": "speed_mps = y_mean + speed_normalised * y_std",
    "vectors": results_summary,
}

(OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

print(f"\nDone. {len(all_windows)} vector pairs written to:")
print(f"  {OUT_DIR}")
print("\nSummary table:")
print(f"  {'Vector':<12} {'Sequence':<12} {'Python m/s':>10} {'GT m/s':>10} {'Err m/s':>10}")
for r in results_summary:
    print(f"  {r['vector']:<12} {r['seq']:<12} {r['python_mps']:>10.4f} {r['gt_mps']:>10.4f} {r['error_mps']:>10.4f}")
print("\nSend the contents of android_handoff/test_vectors/ to your friend along")
print("with gru_v2.onnx, scaler.json, and gru_v2_speed_estimator.dart.")
