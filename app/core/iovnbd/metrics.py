"""Drift metrics scored against the ISRO benchmark.

ISRO target: horizontal position error < 10 % of distance travelled during the
GNSS outage (their worked examples: <5 m over 50 m, <100 m over 1 km).
"""

from __future__ import annotations

import numpy as np

from .deadreckon import DRResult

ISRO_DRIFT_PCT = 10.0


def drift_metrics(res: DRResult) -> dict:
    ex, nx = res.east_hat, res.north_hat
    et, nt = res.east_true, res.north_true
    err = np.hypot(ex - et, nx - nt)                 # instantaneous position error

    seg_len = res.path_len_m
    final = float(err[-1])
    out = {
        "speed_source": res.speed_source,
        "heading_source": res.heading_source,
        "outage_s": round(float(res.t[-1] - res.t[0]), 1),
        "outage_dist_m": round(seg_len, 1),
        "final_drift_m": round(final, 2),
        "max_drift_m": round(float(err.max()), 2),
        "rmse_m": round(float(np.sqrt(np.mean(err**2))), 2),
        "drift_pct": round(100.0 * final / max(seg_len, 1e-6), 2),
        "drift_rate_m_per_s": round(final / max(res.t[-1] - res.t[0], 1e-6), 3),
        "speed_mae_ms": _speed_mae(res),
        "pass_isro": bool(100.0 * final / max(seg_len, 1e-6) <= ISRO_DRIFT_PCT),
    }
    return out


def _speed_mae(res: DRResult) -> float:
    # only meaningful when we are not already using truth
    try:
        from .loader import Trip  # noqa
    except Exception:
        return float("nan")
    return float("nan") if res.speed_source == "truth" else round(
        float(np.nanmean(np.abs(res.speed_hat - _truth_like(res)))), 3
    )


def _truth_like(res: DRResult) -> np.ndarray:
    # reconstruct truth speed from the true ENU track (finite difference)
    dt = np.diff(res.t, prepend=res.t[0])
    dt[dt == 0] = np.nan
    ve = np.gradient(res.east_true, res.t)
    vn = np.gradient(res.north_true, res.t)
    return np.hypot(ve, vn)


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    arr = lambda k: np.array([r[k] for r in rows], dtype=float)
    return {
        "n": len(rows),
        "pass_rate": round(float(np.mean([r["pass_isro"] for r in rows])), 3),
        "drift_pct_median": round(float(np.median(arr("drift_pct"))), 2),
        "drift_pct_p90": round(float(np.percentile(arr("drift_pct"), 90)), 2),
        "final_drift_m_median": round(float(np.median(arr("final_drift_m"))), 2),
        "final_drift_m_p90": round(float(np.percentile(arr("final_drift_m"), 90)), 2),
    }
