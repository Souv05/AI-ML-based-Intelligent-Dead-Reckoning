"""Synthetic GNSS-blackout drift benchmark against the ISRO <10% target.

Outputs
    outputs/benchmark/detail.csv       one row per (trip, scenario, window, combo)
    outputs/benchmark/summary.csv      aggregated pass-rate / drift percentiles
    outputs/benchmark/summary.md       readable
    outputs/benchmark/<key>_<sc>.png   trajectory + error figures for sample trips
"""

from __future__ import annotations

import _bootstrap  # noqa: F401
import pandas as pd

from iovnbd.blackout import SCENARIOS, make_blackouts
from iovnbd.deadreckon import dead_reckon
from iovnbd.harness import DEFAULT_COMBOS, run
from iovnbd.loader import load_trip
from iovnbd.paths import OUTPUT_ROOT, find_synced_trips
from iovnbd.plots import drift_figure

BM_DIR = OUTPUT_ROOT / "benchmark"
BM_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_FIGS = [("M/M", "isro_60s"), ("Vta/Vta29", "isro_1km"), ("S/S2", "isro_60s")]


def main() -> None:
    scenarios = ("isro_60s", "isro_1km", "tunnels", "every_2min")
    print("running drift benchmark ...")
    detail, summary, skipped = run(scenarios=scenarios, combos=DEFAULT_COMBOS,
                                   only_usable=True, verbose=True)

    detail.to_csv(BM_DIR / "detail.csv", index=False)
    summary.to_csv(BM_DIR / "summary.csv", index=False)

    with open(BM_DIR / "summary.md", "w", encoding="utf-8") as fh:
        fh.write("# GNSS-blackout drift benchmark\n\n")
        fh.write(f"trips scored: {detail['key'].nunique()}   "
                 f"(skipped {len(skipped)})\n\n")
        fh.write("ISRO target: final horizontal drift <= 10% of outage distance.\n\n")
        if not summary.empty:
            cols = ["scenario", "speed_source", "heading_source", "n",
                    "pass_rate", "drift_pct_median", "drift_pct_p90",
                    "final_drift_m_median", "final_drift_m_p90"]
            fh.write(summary[cols].sort_values(["scenario", "pass_rate"],
                                              ascending=[True, False])
                     .to_markdown(index=False))
        fh.write("\n\n## skipped trips\n\n")
        for s in skipped:
            fh.write(f"- {s}\n")

    # sample figures
    trips = {t.key: t for t in find_synced_trips()}
    for key, sc in SAMPLE_FIGS:
        if key not in trips:
            continue
        trip = load_trip(trips[key])
        wins = make_blackouts(trip, SCENARIOS[sc])
        if not wins:
            continue
        res = [dead_reckon(trip, wins[0], speed_source=sp, heading_source=hd)
               for sp, hd in [("truth", "gyro"), ("hold", "gyro"),
                              ("gps_decay", "gyro"), ("imu_integrate", "gyro")]]
        png = BM_DIR / f"{key.replace('/', '_')}_{sc}.png"
        drift_figure(trip, res, png)
        print(f"  figure {png.name}")

    print(f"\nwrote {BM_DIR/'detail.csv'}")
    print(f"wrote {BM_DIR/'summary.csv'}")
    print(f"wrote {BM_DIR/'summary.md'}")
    if not summary.empty:
        print("\n" + summary.to_string(index=False))


if __name__ == "__main__":
    main()
