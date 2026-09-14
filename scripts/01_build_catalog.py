"""Discover every synchronised trip, load it, and write a one-row-per-trip catalog.

Outputs
    outputs/catalog.csv        full per-trip stats + quality flags
    outputs/catalog_brief.md   readable summary table
"""

from __future__ import annotations

import _bootstrap  # noqa: F401
import pandas as pd

from iovnbd.eda import trip_summary, usable_for_benchmark
from iovnbd.loader import load_trip
from iovnbd.paths import OUTPUT_ROOT, find_synced_trips


def main() -> None:
    trips = find_synced_trips()
    print(f"{len(trips)} synchronised categorised trips under the dataset root\n")

    rows = []
    for st in trips:
        try:
            trip = load_trip(st)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {st.key}: {e!r}")
            continue
        row = trip_summary(trip)
        row["usable_for_benchmark"] = usable_for_benchmark(row)
        rows.append(row)
        print(f"  {row['key']:<16} {row['region']:<8} "
              f"{row['path_len_km']:>6.2f} km  {row['duration_min']:>6.1f} min  "
              f"phone~{row['phone_hz_est']}Hz  "
              f"{'USABLE' if row['usable_for_benchmark'] else 'skip'}")

    df = pd.DataFrame(rows)
    csv = OUTPUT_ROOT / "catalog.csv"
    df.to_csv(csv, index=False)

    brief_cols = [
        "key", "region", "duration_min", "path_len_km",
        "mean_speed_kmh", "max_speed_kmh", "frac_stationary",
        "phone_hz_est", "gps_acc_median_m",
        "imu_r_acc_vs_vehlong", "imu_r_gyro_vs_yawrate", "flag_imu_coupled",
        "truth_dr_drift_pct", "flag_truth_consistent", "usable_for_benchmark",
    ]
    md = OUTPUT_ROOT / "catalog_brief.md"
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(f"# IO-VNBD synchronised trip catalog ({len(df)} trips)\n\n")
        fh.write(df[brief_cols].to_markdown(index=False))
        fh.write("\n\n## totals\n\n")
        fh.write(f"- trips: {len(df)}\n")
        fh.write(f"- usable for drift benchmark: {int(df['usable_for_benchmark'].sum())}\n")
        fh.write(f"- total distance: {df['path_len_km'].sum():.1f} km\n")
        fh.write(f"- total duration: {df['duration_min'].sum()/60:.1f} h\n")
        fh.write(f"- regions: {df['region'].value_counts().to_dict()}\n")
        fh.write(f"- phone layouts: {df['phone_layout'].value_counts().to_dict()}\n")

    print(f"\nwrote {csv}")
    print(f"wrote {md}")
    print(f"\nusable for benchmark: {int(df['usable_for_benchmark'].sum())}/{len(df)}")


if __name__ == "__main__":
    main()
