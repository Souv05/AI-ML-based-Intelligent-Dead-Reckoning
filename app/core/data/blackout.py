"""Stage: GNSS-availability mask + reusable blackout generator.

Two distinct things:

* ``native_gnss_valid`` - was a *real* GNSS fix present on that row (finite,
  in-range coordinates, non-stale).  Derived from the data, never edited.
* ``gnss_available``    - the simulation mask.  Starts as a copy of
  ``native_gnss_valid`` and is then set to 0 inside engineered outage windows.

The mask is meant to gate MODEL INPUTS only.  The reference trajectory is never
masked - it stays fully available for evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import PrepConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class BlackoutWindow:
    start_idx: int
    end_idx: int            # exclusive
    start_time: float
    end_time: float
    duration_s: float
    distance_m: float


def native_gnss_valid(df: pd.DataFrame, stale_seconds: float = 12.0) -> np.ndarray:
    """A real GNSS fix is 'available' on this row if the coordinates are finite,
    in range, and were refreshed within the last `stale_seconds`.

    NOTE (measured, not assumed): the phone position fix refreshes every ~1 s on
    only a few trips; on most it refreshes every ~9 s, with real dropouts of
    30-150 s.  Holding a fix for its normal refresh interval is NOT a dropout, so
    the threshold is set well above the typical 9 s cadence; only genuine
    multi-fix outages while moving are flagged invalid."""
    lat = df["latitude"].to_numpy(float)
    lon = df["longitude"].to_numpy(float)
    t = df["timestamp"].to_numpy(float)
    spd = df["reference_speed"].to_numpy(float) if "reference_speed" in df else np.zeros(len(df))

    ok = (
        np.isfinite(lat) & np.isfinite(lon)
        & (np.abs(lat) < 90) & (np.abs(lon) < 180)
        & ~((lat == 0) & (lon == 0))
    )

    changed = np.r_[True, (np.diff(lat) != 0) | (np.diff(lon) != 0)]
    last_change_t = np.where(changed, t, np.nan)
    last_change_t = pd.Series(last_change_t).ffill().to_numpy()
    stale = (t - last_change_t > stale_seconds) & (spd > 3.0)

    return ok & ~stale


def make_windows(
    df: pd.DataFrame,
    cfg: PrepConfig = DEFAULT_CONFIG,
    recurring: bool = False,
) -> list[BlackoutWindow]:
    t = df["timestamp"].to_numpy(float)
    n = len(t)
    spd = df["reference_speed"].to_numpy(float) if "reference_speed" in df else np.full(n, np.nan)
    if "reference_x" in df and "reference_y" in df:
        x = df["reference_x"].to_numpy(float)
        y = df["reference_y"].to_numpy(float)
        dist = np.r_[0.0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    else:
        dist = np.full(n, np.nan)

    starts = [cfg.blackout_warmup_s]
    if recurring:
        s = cfg.blackout_warmup_s + cfg.blackout_period_s
        while s < t[-1] - cfg.blackout_duration_s - 5:
            starts.append(s)
            s += cfg.blackout_period_s

    out: list[BlackoutWindow] = []
    for st in starts:
        i0 = int(np.searchsorted(t, st))
        i1 = int(np.searchsorted(t, st + cfg.blackout_duration_s))
        if i0 >= n - 2 or i1 <= i0 + 1 or i1 > n:
            continue
        if np.nanmax(np.diff(t[i0:i1])) > cfg.max_gap_s:
            continue
        if np.isfinite(spd[i0:i1]).any() and np.nanmean(spd[i0:i1] > cfg.blackout_min_speed_ms) < 0.5:
            continue
        out.append(BlackoutWindow(
            start_idx=i0, end_idx=i1,
            start_time=float(t[i0]), end_time=float(t[i1 - 1]),
            duration_s=float(t[i1 - 1] - t[i0]),
            distance_m=float(dist[i1 - 1] - dist[i0]) if np.isfinite(dist[i1 - 1]) else float("nan"),
        ))
    return out


def apply_mask(df: pd.DataFrame, windows: list[BlackoutWindow]) -> pd.DataFrame:
    """Return a copy with `gnss_available` zeroed inside every window."""
    out = df.copy()
    avail = out["native_gnss_valid"].to_numpy().astype(np.int8).copy()
    for w in windows:
        avail[w.start_idx:w.end_idx] = 0
    out["gnss_available"] = avail
    return out
