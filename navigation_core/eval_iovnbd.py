"""Phase 12 evaluation: frozen GRU-v2 on IO-VNBD dataset.

Runs two pipelines on every synced trip and compares speed RMSE:

  Pipeline A (baseline — legacy):
    PhoneLog → GRUEngine.push() (12-feature, direct phone input)

  Pipeline B (new — sensor-agnostic):
    PhoneLog → IOVNBDAdapter → StandardIMUSample → GRUv2.push() (6-feature)

Ground truth: vehicle GNSS/INS speed (VehicleLog.speed_ms)

Outputs a summary table to stdout and saves results/phase12_eval.csv.

Usage:
    python -m navigation_core.eval_iovnbd \\
        --onnx  configs/tcn_gru_model.onnx \\
        --meta  configs/model_metadata.json \\
        [--max-trips N]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.core.iovnbd.paths import find_synced_trips
from app.core.iovnbd.loader import load_trip
from app.core.inference.gru_engine import GRUEngine        # legacy baseline
from navigation_core.imu.iovnbd_adapter import IOVNBDAdapter
from navigation_core.models.gru_v2 import GRUv2           # new sensor-agnostic


def _run_legacy(trip, gru_engine: GRUEngine) -> np.ndarray:
    """Pipeline A: legacy GRUEngine, 12-feature direct phone input."""
    gru_engine.reset()
    df = trip.phone.df
    preds = []
    for i in range(len(df)):
        row = df.iloc[i]
        speed = gru_engine.push(
            float(row.get("acc_x",  0) or 0),
            float(row.get("acc_y",  0) or 0),
            float(row.get("acc_z",  0) or 0),
            float(row.get("gyro_x", 0) or 0),
            float(row.get("gyro_y", 0) or 0),
            float(row.get("gyro_z", 0) or 0),
            float(row.get("mag_x",  0) or 0),
            float(row.get("mag_y",  0) or 0),
            float(row.get("mag_z",  0) or 0),
            float(row.get("ori_roll",  0) or 0),
            float(row.get("ori_pitch", 0) or 0),
            float(row.get("ori_yaw",   0) or 0),
        )
        preds.append(speed)
    return np.array(preds, dtype=float)


def _run_new(trip, gru_v2: GRUv2) -> np.ndarray:
    """Pipeline B: sensor-agnostic GRUv2 via IOVNBDAdapter."""
    gru_v2.reset()
    adapter = IOVNBDAdapter()
    preds = []
    for sample in adapter.stream(trip.phone):
        speed = gru_v2.push(sample)
        preds.append(speed)
    return np.array(preds, dtype=float)


def _rmse(pred: np.ndarray, truth: np.ndarray) -> float:
    """RMSE on aligned, non-NaN rows where both pipelines have output."""
    n = min(len(pred), len(truth))
    p, t = pred[:n], truth[:n]
    mask = np.isfinite(p) & np.isfinite(t)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.mean((p[mask] - t[mask]) ** 2)))


def _mae(pred: np.ndarray, truth: np.ndarray) -> float:
    n = min(len(pred), len(truth))
    p, t = pred[:n], truth[:n]
    mask = np.isfinite(p) & np.isfinite(t)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs(p[mask] - t[mask])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--onnx",      required=True, help="ONNX model path")
    parser.add_argument("--meta",      required=True, help="Model metadata JSON")
    parser.add_argument("--max-trips", type=int, default=None,
                        help="Limit number of trips (default: all)")
    parser.add_argument("--out",       default="results/phase12_eval.csv",
                        help="Output CSV path")
    args = parser.parse_args()

    onnx_path = Path(args.onnx)
    meta_path = Path(args.meta)

    print("Loading models …")
    gru_legacy = GRUEngine(onnx_path, meta_path)
    gru_new    = GRUv2(onnx_path, meta_path)
    print(f"  Legacy  : GRUEngine  window={gru_legacy._window}")
    print(f"  New     : GRUv2 v{gru_new.version}  window={gru_new.window_size}  features={gru_new.feature_order}")

    print("\nDiscovering trips …")
    all_trips = find_synced_trips()
    if args.max_trips:
        all_trips = all_trips[:args.max_trips]
    print(f"  {len(all_trips)} trips found")

    rows = []
    rmse_a_all, rmse_b_all = [], []

    for st in all_trips:
        try:
            trip = load_trip(st)
        except Exception as e:
            print(f"  SKIP {st.key}: {e}")
            continue

        truth = trip.vehicle.speed_ms   # ground-truth m/s

        pred_a = _run_legacy(trip, gru_legacy)
        pred_b = _run_new(trip, gru_new)

        rmse_a = _rmse(pred_a, truth)
        rmse_b = _rmse(pred_b, truth)
        mae_a  = _mae(pred_a,  truth)
        mae_b  = _mae(pred_b,  truth)
        delta  = rmse_b - rmse_a   # positive = new is worse

        rmse_a_all.append(rmse_a)
        rmse_b_all.append(rmse_b)

        rows.append({
            "trip":       st.key,
            "n_samples":  trip.n,
            "duration_s": f"{trip.duration_s:.1f}",
            "rmse_legacy_ms": f"{rmse_a:.4f}",
            "rmse_new_ms":    f"{rmse_b:.4f}",
            "delta_ms":       f"{delta:+.4f}",
            "mae_legacy_ms":  f"{mae_a:.4f}",
            "mae_new_ms":     f"{mae_b:.4f}",
        })

        status = "OK" if abs(delta) < 0.1 else ("worse" if delta > 0 else "better")
        print(f"  {st.key:<20}  legacy={rmse_a:.3f}  new={rmse_b:.3f}  d={delta:+.3f}  {status}")

    # Summary
    if rmse_a_all:
        mean_a = float(np.nanmean(rmse_a_all))
        mean_b = float(np.nanmean(rmse_b_all))
        print(f"\n{'-'*60}")
        print(f"  Trips evaluated  : {len(rows)}")
        print(f"  Legacy mean RMSE : {mean_a:.4f} m/s")
        print(f"  New    mean RMSE : {mean_b:.4f} m/s")
        print(f"  Mean delta       : {mean_b - mean_a:+.4f} m/s")
        if abs(mean_b - mean_a) < 0.05:
            print("  [PASS] Adapter pipeline matches legacy — architecture validated.")
        elif mean_b < mean_a:
            print("  [BETTER] New pipeline is better — model generalises well.")
        else:
            print("  [FAIL] Degradation detected — investigate frame/unit/normalization.")

    # Save CSV
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
