"""Replay an external IMU CSV through the Navigation Engine.

Proves the Navigation Core runs completely without Flutter or a phone.

CSV format (columns):
    timestamp,ax,ay,az,gx,gy,gz
    [optional: mx,my,mz,roll,pitch,yaw]
    [optional: lat,lon,gnss_speed,gnss_heading,gnss_accuracy,gnss_valid]

Usage:
    python -m navigation_core.csv_replay \\
        --csv data/external_imu.csv \\
        --onnx configs/tcn_gru_model.onnx \\
        --meta configs/model_metadata.json \\
        --accel-unit g \\
        --gyro-unit deg/s \\
        --out results/output.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from navigation_core.imu.csv_adapter import CSVIMUAdapter
from navigation_core.navigation_engine import NavigationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv",  required=True,  help="Input IMU CSV file")
    parser.add_argument("--onnx", required=True,  help="ONNX model path")
    parser.add_argument("--meta", required=True,  help="Model metadata JSON")
    parser.add_argument("--accel-unit", default="m/s2", help="m/s2 or g")
    parser.add_argument("--gyro-unit",  default="rad/s", help="rad/s or deg/s")
    parser.add_argument("--frame",      default="FRD",   help="Source sensor frame")
    parser.add_argument("--out",        default=None,    help="Output CSV path (default: stdout)")
    args = parser.parse_args()

    adapter = CSVIMUAdapter(
        accel_unit   = args.accel_unit,
        gyro_unit    = args.gyro_unit,
        source_frame = args.frame,
    )

    engine = NavigationEngine(
        onnx_path     = Path(args.onnx),
        metadata_path = Path(args.meta),
    )

    out_rows = []
    has_gnss = False

    for sample in adapter.from_file(args.csv):
        out = engine.push(sample)
        if out:
            out_rows.append({
                "timestamp":      f"{out.timestamp:.3f}",
                "latitude":       f"{out.latitude:.8f}",
                "longitude":      f"{out.longitude:.8f}",
                "east_m":         f"{out.east_m:.2f}",
                "north_m":        f"{out.north_m:.2f}",
                "speed_fwd_ms":   f"{out.speed_fwd_ms:.3f}",
                "heading_deg":    f"{out.heading_deg:.1f}",
                "gru_speed_ms":   f"{out.gru_speed_ms:.3f}" if out.gru_speed_ms else "",
                "position_std_m": f"{out.position_std_m:.2f}",
                "mode":           out.mode,
                "gnss_valid":     str(out.gnss_valid),
            })

    if not out_rows:
        print("No output generated — check GNSS feed or window warmup.", file=sys.stderr)
        sys.exit(1)

    fields = list(out_rows[0].keys())
    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(out_rows)
        print(f"Written {len(out_rows)} rows → {args.out}")
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)


if __name__ == "__main__":
    main()
