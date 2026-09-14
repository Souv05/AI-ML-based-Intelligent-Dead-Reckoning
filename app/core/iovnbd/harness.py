"""End-to-end evaluation loop: trips x scenarios x (speed, heading) sources."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .blackout import SCENARIOS, BlackoutSpec, make_blackouts
from .deadreckon import dead_reckon
from .eda import trip_summary, usable_for_benchmark
from .loader import Trip, load_trip
from .metrics import aggregate, drift_metrics
from .paths import find_synced_trips

DEFAULT_COMBOS = [
    ("truth", "truth"),           # pipeline sanity + V-file self-consistency check
    ("truth", "veh_yawrate"),     # heading-only budget with a *clean* rate gyro
    ("hold", "truth"),            # speed-only budget (freeze speed, perfect heading)
    ("obd", "veh_yawrate"),       # best classical: CAN speed + vehicle yaw-rate sensor
    ("wheel_speed", "veh_yawrate"),
    ("obd", "gps_hold"),          # clean speed, frozen heading (no gyro at all)
    ("hold", "imu_aligned"),      # phone-only classical (falls back to frozen course)
    ("imu_integrate", "imu_aligned"),  # pure phone-IMU (expected: poor -> motivates ML)
]


def evaluate_trip(
    trip: Trip,
    scenario: str = "isro_60s",
    combos=DEFAULT_COMBOS,
    spec: BlackoutSpec | None = None,
) -> list[dict]:
    spec = spec or SCENARIOS[scenario]
    wins = make_blackouts(trip, spec)
    rows: list[dict] = []
    for wi, win in enumerate(wins):
        for sp, hd in combos:
            res = dead_reckon(trip, win, speed_source=sp, heading_source=hd)
            m = drift_metrics(res)
            m.update(
                key=trip.key,
                driver=trip.driver.split(" ")[0],
                scenario=scenario,
                window=wi,
                anchor_t=round(win.t0, 1),
            )
            rows.append(m)
    return rows


def run(
    scenarios=("isro_60s", "isro_1km", "tunnels"),
    combos=DEFAULT_COMBOS,
    limit: int | None = None,
    only_usable: bool = True,
    verbose: bool = True,
):
    trips = find_synced_trips()
    if limit:
        trips = trips[:limit]

    detail: list[dict] = []
    skipped: list[str] = []
    for st in trips:
        try:
            trip = load_trip(st)
        except Exception as e:  # noqa: BLE001
            skipped.append(f"{st.key}: load error {e!r}")
            continue
        summ = trip_summary(trip)
        if only_usable and not usable_for_benchmark(summ):
            skipped.append(f"{st.key}: not benchmark-usable")
            continue
        for sc in scenarios:
            detail.extend(evaluate_trip(trip, sc, combos))
        if verbose:
            print(f"  scored {st.key:<16} ({summ['path_len_km']} km, "
                  f"{summ['duration_min']} min)")

    detail_df = pd.DataFrame(detail)
    summary_rows = []
    if not detail_df.empty:
        for (sc, sp, hd), g in detail_df.groupby(["scenario", "speed_source", "heading_source"]):
            agg = aggregate(g.to_dict("records"))
            agg.update(scenario=sc, speed_source=sp, heading_source=hd)
            summary_rows.append(agg)
    summary_df = pd.DataFrame(summary_rows)
    return detail_df, summary_df, skipped
