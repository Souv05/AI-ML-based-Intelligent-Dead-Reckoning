"""Per-trip summary statistics and data-quality checks.

`trip_summary` returns a flat dict (one row of the catalog); `quality_flags`
adds boolean columns that are useful for filtering trips before training.
"""

from __future__ import annotations

import numpy as np

from .geo import unwrap_deg
from .loader import Trip

_G = 9.80665


def _best_lag_corr(a: np.ndarray, b: np.ndarray, mask: np.ndarray, lags=range(-20, 21, 2)) -> float:
    """Max |Pearson r| between a and lag-shifted b over the masked samples."""
    best = 0.0
    for lag in lags:
        bb = np.roll(b, lag)
        m = mask & np.isfinite(a) & np.isfinite(bb)
        if m.sum() < 200 or np.std(a[m]) < 1e-6 or np.std(bb[m]) < 1e-6:
            continue
        r = float(np.corrcoef(a[m], bb[m])[0, 1])
        if np.isfinite(r) and abs(r) > abs(best):
            best = r
    return round(best, 3)


def imu_usefulness(trip: Trip) -> dict:
    """How much of the vehicle's dynamics actually shows up in the phone IMU.
    Values near 0 mean the phone was not rigidly coupled to the car."""
    p, v = trip.phone, trip.vehicle
    moving = v.speed_ms > 3
    t = trip.t
    dt = np.gradient(t)

    lin_mag = np.linalg.norm(p.acc() - p.gravity(), axis=1)
    veh_long = np.abs(v.df["acc_long_g"].to_numpy() * _G) if "acc_long_g" in v.df else np.full(trip.n, np.nan)
    r_acc = _best_lag_corr(lin_mag, veh_long, moving)

    true_yawrate = np.gradient(unwrap_deg(v.df["heading_deg"].to_numpy())) / dt
    gyro = p.gyro()
    r_gyro = max((_best_lag_corr(np.degrees(gyro[:, k]), true_yawrate, moving) for k in range(3)),
                 key=abs, default=0.0)

    return {
        "imu_r_acc_vs_vehlong": r_acc,
        "imu_r_gyro_vs_yawrate": round(r_gyro, 3),
        "flag_imu_coupled": bool(abs(r_acc) > 0.3 or abs(r_gyro) > 0.3),
    }


def truth_consistency(trip: Trip) -> dict:
    """Dead-reckon with the TRUE speed and TRUE heading over one 60 s window and
    measure the residual: it should be ~0.  Larger values mean the V file's
    dynamics channels disagree with its position channels on that trip."""
    from .blackout import SCENARIOS, make_blackouts
    from .deadreckon import dead_reckon

    wins = make_blackouts(trip, SCENARIOS["isro_60s"])
    if not wins:
        return {"truth_dr_drift_pct": None, "flag_truth_consistent": None}
    r = dead_reckon(trip, wins[0], speed_source="truth", heading_source="truth")
    return {
        "truth_dr_drift_pct": round(r.drift_pct, 2),
        "flag_truth_consistent": bool(r.drift_pct < 3.0),
    }


def trip_summary(trip: Trip) -> dict:
    p, v = trip.phone, trip.vehicle
    t = trip.t
    dt = np.diff(t)
    spd_true = v.speed_ms

    # phone sample cadence (from its own clock, before re-basing to vehicle)
    pt = p.df["t"].to_numpy()
    pdt = np.diff(pt)
    pdt = pdt[np.isfinite(pdt) & (pdt > 0)]

    # GPS availability on the phone
    if "gps_acc_m" in p.df:
        gps_acc = p.df["gps_acc_m"].to_numpy()
    else:
        gps_acc = np.full(trip.n, np.nan)
    if "gps_sats" in p.df:
        sats = p.df["gps_sats"].to_numpy()
    else:
        sats = np.full(trip.n, np.nan)

    gyro = p.gyro()
    acc = p.acc()

    row = {
        "key": trip.key,
        "driver": trip.driver.split(" ")[0],
        "trip_id": trip.meta["trip_id"],
        "phone_layout": trip.meta["phone_layout"],
        "n_rows": trip.n,
        "duration_s": round(trip.duration_s, 1),
        "duration_min": round(trip.duration_s / 60.0, 2),
        "path_len_km": round(trip.length_m / 1000.0, 3),
        "mean_speed_kmh": round(float(np.nanmean(spd_true)) * 3.6, 2),
        "max_speed_kmh": round(float(np.nanmax(spd_true)) * 3.6, 2),
        "frac_stationary": round(float(np.mean(spd_true < 0.5)), 3),

        "veh_dt_median_s": round(float(np.median(dt)), 4) if dt.size else None,
        "veh_dt_p95_s": round(float(np.percentile(dt, 95)), 4) if dt.size else None,
        "veh_dt_max_s": round(float(np.max(dt)), 3) if dt.size else None,
        "veh_time_gaps_gt_0p3s": int(np.sum(dt > 0.3)) if dt.size else None,

        "phone_hz_est": round(1.0 / float(np.median(pdt)), 2) if pdt.size else None,
        "phone_dt_max_s": round(float(np.max(pdt)), 2) if pdt.size else None,
        "phone_gaps_gt_0p3s": int(np.sum(pdt > 0.3)) if pdt.size else None,

        "gps_acc_median_m": round(float(np.nanmedian(gps_acc)), 2),
        "gps_acc_p95_m": round(float(np.nanpercentile(gps_acc, 95)), 2),
        "sats_median": round(float(np.nanmedian(sats)), 1),
        "frac_gps_poor": round(float(np.nanmean(gps_acc > 15)), 3),

        "acc_norm_mean": round(float(np.nanmean(np.linalg.norm(acc, axis=1))), 3),
        "gyro_abs_p95": round(float(np.nanpercentile(np.abs(gyro), 95)), 4),
        "lat0": round(trip.lat0, 5),
        "lon0": round(trip.lon0, 5),
        "region": _region(trip.lat0, trip.lon0),
    }

    row.update(quality_flags(trip, row))
    row.update(imu_usefulness(trip))
    row.update(truth_consistency(trip))
    return row


def _region(lat: float, lon: float) -> str:
    if 4 <= lat <= 14 and 2 <= lon <= 15:
        return "Nigeria"
    if 41 <= lat <= 52 and -5 <= lon <= 9:
        return "France"
    if 49 <= lat <= 61 and -8 <= lon <= 2:
        return "UK"
    return "other"


def quality_flags(trip: Trip, row: dict) -> dict:
    p = trip.phone
    need = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
    has_imu = all(c in p.df for c in need) and p.df[need].notna().mean().min() > 0.95
    acc_norm = np.linalg.norm(p.acc(), axis=1)
    return {
        "flag_has_full_imu": bool(has_imu),
        "flag_short": bool(trip.duration_s < 60),
        "flag_time_irregular": bool((row["veh_dt_max_s"] or 0) > 1.0),
        "flag_acc_units_ok": bool(6 < np.nanmedian(acc_norm) < 13),  # ~g, i.e. m/s^2
        "flag_mostly_moving": bool(row["frac_stationary"] < 0.7),
    }


def usable_for_benchmark(row: dict) -> bool:
    return (
        row["flag_has_full_imu"]
        and row["flag_acc_units_ok"]
        and not row["flag_short"]
        and row["flag_mostly_moving"]
        and row["path_len_km"] >= 0.3
        and bool(row.get("flag_truth_consistent", True))
    )
