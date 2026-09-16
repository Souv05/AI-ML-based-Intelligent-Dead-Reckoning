"""Edge Navigation Engine — standalone runner for external IMU sources.

Accepts IMU data from UDP, Serial, or CSV and runs the full navigation
pipeline (GRU-v2 + EKF + NHC) completely independently of Flutter.

                 EDGE NAVIGATION ENGINE
                         |
         +---------------+---------------+
         |               |               |
      CSV input       UDP input     Serial input
         |               |               |
         +---------------+---------------+
                         |
                  Sensor Adapter
                         |
                  Preprocessing
                         |
                      GRU-v2
                         |
                     EKF + NHC
                         |
                 NavigationOutput
                 (stdout JSON / log file)

Usage examples:

  # From CSV file:
  python -m navigation_core.edge_runner --source csv --csv data/imu.csv \\
      --onnx configs/tcn_gru_model.onnx --meta configs/model_metadata.json

  # From UDP (external IMU sending JSON datagrams):
  python -m navigation_core.edge_runner --source udp --udp-port 5005 \\
      --onnx configs/tcn_gru_model.onnx --meta configs/model_metadata.json \\
      --accel-unit g --gyro-unit deg/s

  # From serial port:
  python -m navigation_core.edge_runner --source serial --serial-port COM3 \\
      --serial-baud 115200 --accel-unit g --gyro-unit deg/s \\
      --onnx configs/tcn_gru_model.onnx --meta configs/model_metadata.json

Output (one JSON line per navigation update, ~10 Hz):
  {"timestamp":1.23,"lat":22.5,"lon":88.35,"speed_fwd_ms":8.3,
   "heading_deg":45.1,"mode":"DR_ACTIVE","position_std_m":12.4}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from navigation_core.navigation_engine import NavigationEngine
from navigation_core.imu.csv_adapter import CSVIMUAdapter
from navigation_core.imu.udp_adapter import UDPIMUAdapter
from navigation_core.imu.serial_adapter import SerialIMUAdapter


def _print_output(out, file=None) -> None:
    line = json.dumps({
        "timestamp":      round(out.timestamp,      3),
        "latitude":       round(out.latitude,        8),
        "longitude":      round(out.longitude,       8),
        "east_m":         round(out.east_m,          2),
        "north_m":        round(out.north_m,         2),
        "speed_fwd_ms":   round(out.speed_fwd_ms,    3),
        "heading_deg":    round(out.heading_deg,      1),
        "gru_speed_ms":   round(out.gru_speed_ms, 3) if out.gru_speed_ms else None,
        "position_std_m": round(out.position_std_m,  2),
        "mode":           out.mode,
        "gnss_valid":     out.gnss_valid,
    })
    print(line, file=file, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", required=True,
                        choices=["csv", "udp", "serial"],
                        help="IMU input source")

    # Model
    parser.add_argument("--onnx", required=True, help="ONNX model path")
    parser.add_argument("--meta", required=True, help="Model metadata JSON")

    # Units / frame (all sources)
    parser.add_argument("--accel-unit",  default="m/s2",  help="m/s2 or g")
    parser.add_argument("--gyro-unit",   default="rad/s", help="rad/s or deg/s")
    parser.add_argument("--frame",       default="FRD",   help="Source sensor frame")

    # CSV source
    parser.add_argument("--csv", default=None, help="CSV file path (--source csv)")

    # UDP source
    parser.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host")
    parser.add_argument("--udp-port", type=int, default=5005, help="UDP bind port")

    # Serial source
    parser.add_argument("--serial-port", default=None, help="Serial port e.g. COM3")
    parser.add_argument("--serial-baud", type=int, default=115200)
    parser.add_argument("--serial-add-timestamp", action="store_true",
                        help="Use host time.time() if packet has no timestamp field")

    # Output
    parser.add_argument("--out", default=None,
                        help="Write output JSON lines to file (default: stdout)")

    args = parser.parse_args()

    engine = NavigationEngine(
        onnx_path     = Path(args.onnx),
        metadata_path = Path(args.meta),
    )
    print(f"[edge_runner] Navigation engine ready  (GRU window={engine._gru.window_size})",
          file=sys.stderr)

    out_file = open(args.out, "w") if args.out else None

    try:
        if args.source == "csv":
            if not args.csv:
                parser.error("--csv required with --source csv")
            adapter = CSVIMUAdapter(
                accel_unit=args.accel_unit,
                gyro_unit=args.gyro_unit,
                source_frame=args.frame,
            )
            print(f"[edge_runner] Replaying {args.csv}", file=sys.stderr)
            for sample in adapter.from_file(args.csv):
                out = engine.push(sample)
                if out:
                    _print_output(out, file=out_file)

        elif args.source == "udp":
            adapter = UDPIMUAdapter(
                host=args.udp_host,
                port=args.udp_port,
                accel_unit=args.accel_unit,
                gyro_unit=args.gyro_unit,
                source_frame=args.frame,
            )
            for sample in adapter.stream():
                out = engine.push(sample)
                if out:
                    _print_output(out, file=out_file)

        elif args.source == "serial":
            if not args.serial_port:
                parser.error("--serial-port required with --source serial")
            adapter = SerialIMUAdapter(
                port=args.serial_port,
                baud=args.serial_baud,
                accel_unit=args.accel_unit,
                gyro_unit=args.gyro_unit,
                source_frame=args.frame,
                add_host_timestamp=args.serial_add_timestamp,
            )
            for sample in adapter.stream():
                out = engine.push(sample)
                if out:
                    _print_output(out, file=out_file)

    except KeyboardInterrupt:
        print("\n[edge_runner] Stopped.", file=sys.stderr)
    finally:
        if out_file:
            out_file.close()


if __name__ == "__main__":
    main()
