"""EDA figures for a handful of representative trips + a dataset-wide summary.

Outputs
    outputs/eda/<key>.png     per-trip overview (track, speed, dt hist, GPS acc)
    outputs/eda/_dataset.png  distributions across all trips
    outputs/eda/summary.txt   text digest
"""

from __future__ import annotations

import _bootstrap  # noqa: F401
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from iovnbd.eda import trip_summary
from iovnbd.loader import load_trip
from iovnbd.paths import OUTPUT_ROOT, find_synced_trips
from iovnbd.plots import trip_overview

EDA_DIR = OUTPUT_ROOT / "eda"
EDA_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_KEYS = ["S/S1", "M/M", "Vta/Vta29", "Vtb/Vtb01", "Vw/Vw01", "Y/Y1", "Vf/Vfa02"]


def dataset_figure(df: pd.DataFrame, out) -> None:
    fig, ax = plt.subplots(2, 3, figsize=(15, 9))
    ax[0, 0].hist(df["duration_min"], bins=30); ax[0, 0].set(title="trip duration [min]")
    ax[0, 1].hist(df["path_len_km"], bins=30); ax[0, 1].set(title="trip distance [km]")
    ax[0, 2].hist(df["max_speed_kmh"], bins=30); ax[0, 2].set(title="max speed [km/h]")
    ax[1, 0].hist(df["phone_hz_est"].dropna(), bins=30); ax[1, 0].set(title="phone rate [Hz]")
    ax[1, 1].hist(df["gps_acc_median_m"].dropna(), bins=30); ax[1, 1].set(title="median GPS acc [m]")
    reg = df["region"].value_counts()
    ax[1, 2].bar(reg.index, reg.values); ax[1, 2].set(title="region")
    fig.suptitle(f"IO-VNBD synchronised trips (n={len(df)})")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main() -> None:
    trips = {t.key: t for t in find_synced_trips()}
    rows = []
    made = []

    for key, st in [(t.key, t) for t in find_synced_trips()]:
        try:
            trip = load_trip(st)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {key}: {e!r}")
            continue
        rows.append(trip_summary(trip))
        if key in SAMPLE_KEYS:
            png = EDA_DIR / f"{key.replace('/', '_')}.png"
            trip_overview(trip, png)
            made.append(png)
            print(f"  figure {png.name}")

    df = pd.DataFrame(rows)
    dataset_png = EDA_DIR / "_dataset.png"
    dataset_figure(df, dataset_png)
    print(f"  figure {dataset_png.name}")

    digest = EDA_DIR / "summary.txt"
    with open(digest, "w", encoding="utf-8") as fh:
        fh.write("IO-VNBD EDA digest\n==================\n\n")
        fh.write(f"synchronised trips loaded : {len(df)}\n")
        fh.write(f"total distance            : {df['path_len_km'].sum():.1f} km\n")
        fh.write(f"total duration            : {df['duration_min'].sum()/60:.1f} h\n")
        fh.write(f"phone layouts             : {df['phone_layout'].value_counts().to_dict()}\n")
        fh.write(f"regions                   : {df['region'].value_counts().to_dict()}\n\n")
        for c in ["duration_min", "path_len_km", "mean_speed_kmh", "max_speed_kmh",
                  "phone_hz_est", "phone_dt_max_s", "phone_gaps_gt_0p3s",
                  "veh_dt_max_s", "gps_acc_median_m", "frac_gps_poor", "frac_stationary"]:
            s = pd.to_numeric(df[c], errors="coerce")
            fh.write(f"{c:<22} min={s.min():.3g}  median={s.median():.3g}  "
                     f"max={s.max():.3g}\n")
        fh.write("\nquality flags (count True):\n")
        for c in [c for c in df.columns if c.startswith("flag_")]:
            fh.write(f"  {c:<24} {int(df[c].sum())}/{len(df)}\n")
    print(f"\nwrote {digest}")


if __name__ == "__main__":
    main()
