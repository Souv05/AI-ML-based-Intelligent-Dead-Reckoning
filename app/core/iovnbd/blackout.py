"""Synthetic GNSS-outage windows.

IO-VNBD has only incidental GPS loss, so we engineer deterministic outages to
score dead-reckoning against the ISRO drift benchmark.  A window is a half-open
interval of sample indices ``[i0, i1)`` during which GNSS is considered absent;
the estimator may use the fix at ``i0-1`` as its last anchor and is scored at
``i1-1``.

Scenario presets mirror the problem statement:
    "isro_60s"  : a single 60 s outage starting after warm-up
    "isro_1km"  : a single outage spanning ~1 km of travel
    "tunnels"   : several 20-40 s outages (urban-canyon / short-tunnel style)
    "every_2min": recurring 60 s outages for aggregate statistics
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .loader import Trip


@dataclass(frozen=True)
class BlackoutSpec:
    kind: str = "duration"          # "duration" | "distance"
    length: float = 60.0            # seconds (duration) or metres (distance)
    warmup_s: float = 20.0          # never start an outage before this
    cooldown_s: float = 10.0        # nor within this of the trip end
    gap_s: float = 60.0             # nominal spacing between recurring outages
    max_windows: int = 50
    require_moving: bool = True     # window itself must be mostly in motion
    lead_s: float = 20.0            # motion also required for this long before i0
    min_lead_speed: float = 3.0     # m/s the vehicle must exceed at the anchor
    min_window_move_frac: float = 0.6
    seed: int | None = 0


@dataclass(frozen=True)
class Window:
    i0: int
    i1: int
    t0: float
    t1: float
    span_s: float
    span_m: float

    def mask(self, n: int) -> np.ndarray:
        m = np.zeros(n, dtype=bool)
        m[self.i0 : self.i1] = True
        return m


def _end_index_by_duration(t: np.ndarray, i0: int, length_s: float) -> int:
    target = t[i0] + length_s
    j = int(np.searchsorted(t, target, side="left"))
    return min(max(j, i0 + 2), len(t))


def _end_index_by_distance(dist: np.ndarray, i0: int, length_m: float) -> int:
    target = dist[i0] + length_m
    j = int(np.searchsorted(dist, target, side="left"))
    return min(max(j, i0 + 2), len(dist))


def _anchor_ok(trip: Trip, i0: int, spec: BlackoutSpec) -> bool:
    """The vehicle must be moving at i0 and for `lead_s` before it (so a gyro
    bias/scale calibration on the pre-outage data is actually observable)."""
    t, spd = trip.t, trip.vehicle.speed_ms
    if not np.isfinite(spd[i0]) or spd[i0] < spec.min_lead_speed:
        return False
    j0 = int(np.searchsorted(t, t[i0] - spec.lead_s, side="left"))
    if i0 - j0 < 5:
        return False
    lead = spd[j0:i0]
    return np.mean(lead > 0.5) > 0.8 and np.mean(np.isfinite(lead)) > 0.9


def make_blackouts(trip: Trip, spec: BlackoutSpec) -> list[Window]:
    t, dist = trip.t, trip.dist_m
    n = trip.n
    spd = trip.vehicle.speed_ms

    t_end = t[-1] - spec.cooldown_s
    # candidate anchor times: denser than gap_s so we can slide off bad spots
    step = min(spec.gap_s, max(5.0, spec.gap_s / 4)) if spec.max_windows > 1 else 5.0
    cand = np.arange(spec.warmup_s, max(spec.warmup_s + step, t_end), step)

    wins: list[Window] = []
    last_t1 = -1e9
    for st in cand:
        if len(wins) >= spec.max_windows:
            break
        i0 = int(np.searchsorted(t, st, side="left"))
        if i0 >= n - 2 or t[i0] < last_t1 + spec.gap_s:
            continue
        if not _anchor_ok(trip, i0, spec):
            continue
        if spec.kind == "distance":
            i1 = _end_index_by_distance(dist, i0, spec.length)
        else:
            i1 = _end_index_by_duration(t, i0, spec.length)
        if i1 <= i0 + 1 or i1 > n:
            continue
        # reject windows that straddle a logging gap (would corrupt the truth
        # and any dead-reckoning integral)
        lead_i = int(np.searchsorted(t, t[i0] - spec.lead_s, side="left"))
        if np.max(np.diff(t[lead_i:i1])) > 0.5:
            continue

        span_s = float(t[i1 - 1] - t[i0])
        span_m = float(dist[i1 - 1] - dist[i0])
        if spec.kind == "duration" and span_s < 0.5 * spec.length:
            continue            # ran off the end of the trip
        if spec.kind == "distance" and span_m < 0.5 * spec.length:
            continue
        if spec.require_moving and np.mean(spd[i0:i1] > 0.5) < spec.min_window_move_frac:
            continue
        wins.append(Window(i0, i1, float(t[i0]), float(t[i1 - 1]), span_s, span_m))
        last_t1 = t[i1 - 1]
    return wins


def single_window(trip: Trip, spec: BlackoutSpec) -> Window | None:
    """First window only - the common case for the ISRO single-outage scenarios."""
    ws = make_blackouts(trip, spec.__class__(**{**spec.__dict__, "max_windows": 1}))
    return ws[0] if ws else None


SCENARIOS: dict[str, BlackoutSpec] = {
    "isro_60s":   BlackoutSpec(kind="duration", length=60.0,  max_windows=1),
    "isro_1km":   BlackoutSpec(kind="distance", length=1000.0, max_windows=1),
    "short_30s":  BlackoutSpec(kind="duration", length=30.0,  max_windows=1),
    "tunnels":    BlackoutSpec(kind="duration", length=30.0,  gap_s=90.0, max_windows=8),
    "every_2min": BlackoutSpec(kind="duration", length=60.0,  gap_s=120.0, max_windows=50),
}
