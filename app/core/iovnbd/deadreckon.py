"""Baseline dead-reckoning through a GNSS outage.

This is deliberately a *classical* baseline - it defines the drift floor that the
AI speed/heading models in the ISRO brief have to beat.  The estimator is fed the
trajectory up to ``window.i0`` (GNSS available) and must propagate position to
``window.i1 - 1`` using only phone-derived quantities.

Design
------
position update obeys the non-holonomic constraint (the car travels along its
heading, no side-slip, no vertical motion)::

    d(east)/dt  = v * sin(course)
    d(north)/dt = v * cos(course)          course = degrees clockwise from North

``speed_source`` and ``heading_source`` are pluggable so an ML speed regressor
can be dropped straight in::

    dead_reckon(trip, win, speed_source=my_model.predict)

Built-in sources
----------------
speed   : "truth" | "hold" | "gps_decay" | "imu_integrate"
heading : "truth" | "gps_hold" | "gyro"        (gyro is bias/sign-calibrated on
                                                the pre-outage window)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

import numpy as np

from .align import Alignment, estimate_alignment
from .blackout import Window
from .geo import unwrap_deg, wrap_deg
from .loader import Trip

SpeedSource = Union[str, Callable[[Trip, slice, dict], np.ndarray]]
HeadingSource = Union[str, Callable[[Trip, slice, dict], np.ndarray]]

_CAL_S = 60.0          # seconds of pre-outage data used for phone alignment
_CAL_LONG_S = 300.0    # longer look-back for heading-rate sensor calibration
_DEVICE_Z_SIGN = -1.0  # phone gyro-z (right-hand, z-up) vs compass heading rate


@dataclass
class DRResult:
    win: Window
    t: np.ndarray                 # time over [i0-1 .. i1-1]
    east_hat: np.ndarray
    north_hat: np.ndarray
    east_true: np.ndarray
    north_true: np.ndarray
    speed_hat: np.ndarray
    course_hat: np.ndarray
    speed_source: str
    heading_source: str

    # scalar scores (filled by metrics.drift_metrics but cached here too)
    final_drift_m: float = float("nan")
    path_len_m: float = float("nan")
    drift_pct: float = float("nan")


# --------------------------------------------------------------------------- #
# speed sources
# --------------------------------------------------------------------------- #
def _speed_truth(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    return trip.vehicle.speed_ms[sl].copy()


def _speed_hold(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    v0 = ctx["v_anchor"]
    return np.full(sl.stop - sl.start, v0)


def _speed_gps_decay(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    n = sl.stop - sl.start
    tau = 30.0
    tt = trip.t[sl] - trip.t[sl.start]
    return ctx["v_anchor"] * np.exp(-tt / tau)


def _speed_imu_integrate(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """Integrate horizontal specific force along the heading.

    Gravity is removed with the phone's GRAVITY channel; the residual is rotated
    into a level frame with ORIENTATION (pitch, roll) when present, then its
    horizontal magnitude is treated as |longitudinal accel| with the sign taken
    from its projection onto the previous velocity direction.  Crude on purpose.
    """
    p = trip.phone.df
    i0, i1 = sl.start, sl.stop
    acc = trip.phone.acc()[i0:i1]
    grav = trip.phone.gravity()[i0:i1]
    lin = acc - grav                                  # linear acceleration, body frame

    pitch = np.radians(p["ori_pitch"].to_numpy()[i0:i1]) if "ori_pitch" in p else np.zeros(i1 - i0)
    roll = np.radians(p["ori_roll"].to_numpy()[i0:i1]) if "ori_roll" in p else np.zeros(i1 - i0)
    # level the x-y plane (small-angle-safe full rotation about roll then pitch)
    ax, ay, az = lin[:, 0], lin[:, 1], lin[:, 2]
    # rotate out roll (about x), then pitch (about y)
    ay2 = ay * np.cos(roll) - az * np.sin(roll)
    az2 = ay * np.sin(roll) + az * np.cos(roll)
    ax2 = ax * np.cos(pitch) + az2 * np.sin(pitch)
    a_horiz = np.sqrt(ax2**2 + ay2**2)
    a_long = np.where(ax2 >= 0, a_horiz, -a_horiz)    # sign from forward axis guess

    t = trip.t[i0:i1]
    dt = np.diff(t, prepend=t[0])
    v = np.empty(i1 - i0)
    v[0] = ctx["v_anchor"]
    for k in range(1, i1 - i0):
        vk = v[k - 1] + a_long[k] * dt[k]
        v[k] = max(vk, 0.0)                           # cars don't go backwards here
    return v


def _speed_obd(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """CAN 'Indicated Vehicle Speed' - the clean odometry channel in the V file.
    Represents the ISRO 'good external IMU / wheel-odometry' path."""
    v = trip.vehicle.df.get("ind_speed_kmh")
    if v is None:
        return _speed_truth(trip, sl, ctx)
    out = v.to_numpy()[sl] / 3.6
    return np.where(np.isfinite(out), out, ctx["v_anchor"])


def _speed_wheel(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """Mean rear wheel angular rate, scale (effective radius) calibrated against
    GNSS speed on the pre-outage window."""
    df = trip.vehicle.df
    cols = [c for c in ("ws_rl", "ws_rr", "ws_fl", "ws_fr") if c in df]
    if not cols:
        return _speed_obd(trip, sl, ctx)
    w_all = df[cols].to_numpy().mean(axis=1)          # rad/s
    j0, i0 = ctx["cal_slice"]
    wc, vc = w_all[j0:i0], trip.vehicle.speed_ms[j0:i0]
    good = np.isfinite(wc) & np.isfinite(vc) & (wc > 1)
    r = float(np.median(vc[good] / wc[good])) if good.sum() > 20 else 0.30
    out = w_all[sl] * r
    return np.where(np.isfinite(out), out, ctx["v_anchor"])


_SPEED = {
    "truth": _speed_truth,
    "hold": _speed_hold,
    "gps_decay": _speed_gps_decay,
    "imu_integrate": _speed_imu_integrate,
    "obd": _speed_obd,
    "wheel_speed": _speed_wheel,
}


# --------------------------------------------------------------------------- #
# heading sources
# --------------------------------------------------------------------------- #
def _course_truth(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    return trip.vehicle.df["heading_deg"].to_numpy()[sl].copy()


def _course_gps_hold(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    return np.full(sl.stop - sl.start, ctx["course_anchor"])


def _calibrate_rate_sensor(rate: np.ndarray, hdg_deg: np.ndarray, t: np.ndarray,
                           j0: int, i0: int) -> tuple[float, float]:
    """Fit (scale, bias) so that integrating ``scale*rate + bias`` over the
    pre-outage window reproduces the observed net GNSS heading change.

    bias comes from the near-straight samples (where the true rate ~ 0); scale
    is then whatever makes the running integral match the unwrapped heading
    delta over the window (this pins down the sign even when the lstsq slope is
    ill-conditioned)."""
    sl = slice(j0, i0)
    r = rate[sl].astype(float)
    t = t[sl]
    dt = np.gradient(t)
    hdg = unwrap_deg(hdg_deg[sl])
    true_rate = np.gradient(hdg) / np.where(dt > 0, dt, np.nan)

    straight = np.isfinite(true_rate) & (np.abs(true_rate) < 1.0) & np.isfinite(r)
    bias = float(np.median(r[straight])) if straight.sum() > 20 else float(np.nanmedian(r))

    turning = np.isfinite(true_rate) & (np.abs(true_rate) > 3.0) & np.isfinite(r)
    net_true = hdg[-1] - hdg[0]
    net_int = float(np.nansum((r - bias) * dt))
    scale = 1.0
    if turning.sum() > 30 and abs(net_int) > 20.0:
        s = net_true / net_int
        if np.isfinite(s) and 0.2 < abs(s) < 5.0:
            scale = s
    elif turning.sum() > 30:
        s = float(np.dot(r[turning] - bias, true_rate[turning])
                  / np.dot(r[turning] - bias, r[turning] - bias))
        if np.isfinite(s) and 0.2 < abs(s) < 5.0:
            scale = s
    return scale, bias


def _course_veh_yawrate(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """Integrate the vehicle's own yaw-rate sensor (V file, deg/s), sign/scale/
    bias calibrated on the pre-outage GNSS history.  The 'decent gyro' reference
    the phone gyro mostly fails to provide."""
    df = trip.vehicle.df
    if "yaw_rate_dps" not in df:
        return _course_gps_hold(trip, sl, ctx)
    yr = df["yaw_rate_dps"].to_numpy()
    j0, i0 = ctx["cal_slice"]
    scale, bias = _calibrate_rate_sensor(yr, df["heading_deg"].to_numpy(), trip.t, j0, i0)
    t = trip.t[sl]
    dt = np.diff(t, prepend=t[0])
    return ctx["course_anchor"] + np.cumsum((scale * yr[sl] + bias) * dt)


def _calibrate_gyro(trip: Trip, i0: int) -> tuple[float, float]:
    """Estimate (scale, bias) mapping phone gyro-z [rad/s] -> compass yaw-rate
    [deg/s] from the pre-outage window where GNSS heading is still available.

    If the lead-in has little turning (yaw-rate barely varies) the slope is
    unobservable, so we fix the scale at the known device-vs-compass sign and
    only estimate the gyro bias.
    """
    t = trip.t
    j0 = max(int(np.searchsorted(t, t[i0] - _CAL_S, side="left")), 1)
    if i0 - j0 < 20:
        return _DEVICE_Z_SIGN, 0.0
    hdg = unwrap_deg(trip.vehicle.df["heading_deg"].to_numpy()[j0:i0])
    dt = np.diff(t[j0:i0])
    dt[dt <= 0] = np.nan
    yaw_true = np.diff(hdg) / dt                       # deg/s, compass
    gz = np.degrees(trip.phone.gyro()[j0:i0 - 1, 2])   # deg/s, device
    good = np.isfinite(gz) & np.isfinite(yaw_true) & (np.abs(yaw_true) < 60)
    if good.sum() < 20:
        return _DEVICE_Z_SIGN, 0.0

    gz, yaw_true = gz[good], yaw_true[good]
    turning = np.std(yaw_true) > 1.5                   # deg/s of manoeuvring
    if turning:
        (scale, bias), *_ = np.linalg.lstsq(
            np.c_[gz, np.ones_like(gz)], yaw_true, rcond=None
        )
        if np.isfinite(scale) and 0.2 < abs(scale) < 5 and scale * _DEVICE_Z_SIGN > 0:
            return float(scale), float(bias)
    # bias-only fallback
    bias = float(np.mean(yaw_true - _DEVICE_Z_SIGN * gz))
    return _DEVICE_Z_SIGN, bias


def _alignment_for(trip: Trip, i0: int) -> Alignment | None:
    """Estimate phone->vehicle alignment on up to `_CAL_S` s of pre-outage data."""
    t = trip.t
    j0 = max(int(np.searchsorted(t, t[i0] - _CAL_S, side="left")), 1)
    if i0 - j0 < 30:
        return None
    sl = slice(j0, i0)
    p = trip.phone
    course = (
        p.df["gps_course_deg"].to_numpy()[sl] if "gps_course_deg" in p.df
        else trip.vehicle.df["heading_deg"].to_numpy()[sl]
    )
    if not np.isfinite(course).any():
        course = trip.vehicle.df["heading_deg"].to_numpy()[sl]
    lin = p.acc()[sl] - p.gravity()[sl]
    try:
        return estimate_alignment(
            gravity=p.gravity()[sl],
            gyro=p.gyro()[sl],
            lin_acc=lin,
            gps_course_deg=course,
            t=t[sl],
            speed_ms=trip.vehicle.speed_ms[sl],
        )
    except Exception:  # noqa: BLE001
        return None


def _course_gyro(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """Naive: integrate raw device gyro-z, sign/bias from `_calibrate_gyro`
    (assumes the phone is roughly flat)."""
    i0, i1 = sl.start, sl.stop
    scale, bias = ctx["gyro_cal"]
    gz = np.degrees(trip.phone.gyro()[i0:i1, 2])
    t = trip.t[i0:i1]
    dt = np.diff(t, prepend=t[0])
    yaw_rate = scale * gz + bias
    return ctx["course_anchor"] + np.cumsum(yaw_rate * dt)


def _course_imu_aligned(trip: Trip, sl: slice, ctx: dict) -> np.ndarray:
    """Tilt-compensated: rotate gyro into a level frame with the alignment
    estimated on the pre-outage window, then integrate the calibrated yaw-rate.
    Falls back to holding the last GPS course when the phone is clearly not
    rigidly mounted (alignment quality low)."""
    i0, i1 = sl.start, sl.stop
    al = ctx["alignment"]
    if al is None or not np.isfinite(al.quality) or abs(al.quality) < 0.4:
        return np.full(i1 - i0, ctx["course_anchor"])   # fall back to frozen course
    gyro = trip.phone.gyro()[i0:i1]
    yaw_rate = al.yaw_rate_compass(gyro)
    t = trip.t[i0:i1]
    dt = np.diff(t, prepend=t[0])
    return ctx["course_anchor"] + np.cumsum(yaw_rate * dt)


_HEADING = {
    "truth": _course_truth,
    "gps_hold": _course_gps_hold,
    "gyro": _course_gyro,
    "imu_aligned": _course_imu_aligned,
    "veh_yawrate": _course_veh_yawrate,
}


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def dead_reckon(
    trip: Trip,
    win: Window,
    speed_source: SpeedSource = "hold",
    heading_source: HeadingSource = "gyro",
) -> DRResult:
    anchor = max(win.i0 - 1, 0)
    sl = slice(anchor, win.i1)                        # inclusive of the anchor sample
    n = sl.stop - sl.start

    # last known GNSS state at the anchor.  A real receiver reports Doppler speed
    # at the final fix, so anchoring on the true speed at `anchor` is fair; the
    # phone's own (mis-labelled, actually m/s) GPS-speed column agrees to ~1 %.
    v_anchor = float(trip.vehicle.speed_ms[anchor])
    if "gps_speed_ms" in trip.phone.df:
        pv = float(trip.phone.df["gps_speed_ms"].to_numpy()[anchor])
        if np.isfinite(pv) and pv > 0:
            v_anchor = pv
    if not np.isfinite(v_anchor):
        v_anchor = float(np.nanmedian(trip.vehicle.speed_ms[max(anchor - 5, 0):anchor + 1]))

    # heading/rate calibration may look back further than the alignment window -
    # it needs to have seen the vehicle turn at least once.
    cal_j0 = max(int(np.searchsorted(trip.t, trip.t[win.i0] - _CAL_LONG_S, side="left")), 1)
    ctx = {
        "v_anchor": v_anchor,
        "course_anchor": float(trip.vehicle.df["heading_deg"].to_numpy()[anchor]),
        "gyro_cal": _calibrate_gyro(trip, win.i0),
        "alignment": _alignment_for(trip, win.i0),
        "cal_slice": (cal_j0, win.i0),
    }

    sp_fn = _SPEED[speed_source] if isinstance(speed_source, str) else speed_source
    hd_fn = _HEADING[heading_source] if isinstance(heading_source, str) else heading_source
    speed_hat = np.asarray(sp_fn(trip, sl, ctx), dtype=float)
    course_hat = np.asarray(hd_fn(trip, sl, ctx), dtype=float)
    speed_hat = np.clip(np.nan_to_num(speed_hat, nan=ctx["v_anchor"]), 0.0, 90.0)

    # integrate the non-holonomic kinematics (trapezoidal)
    t = trip.t[sl]
    dt = np.diff(t, prepend=t[0])
    c = np.radians(course_hat)
    ve = speed_hat * np.sin(c)
    vn = speed_hat * np.cos(c)
    east_hat = trip.east_m[anchor] + np.cumsum(0.5 * (ve + np.roll(ve, 1)) * dt)
    north_hat = trip.north_m[anchor] + np.cumsum(0.5 * (vn + np.roll(vn, 1)) * dt)
    east_hat[0] = trip.east_m[anchor]
    north_hat[0] = trip.north_m[anchor]

    res = DRResult(
        win=win,
        t=t,
        east_hat=east_hat,
        north_hat=north_hat,
        east_true=trip.east_m[sl],
        north_true=trip.north_m[sl],
        speed_hat=speed_hat,
        course_hat=wrap_deg(course_hat),
        speed_source=speed_source if isinstance(speed_source, str) else "callable",
        heading_source=heading_source if isinstance(heading_source, str) else "callable",
    )
    dx = east_hat[-1] - res.east_true[-1]
    dy = north_hat[-1] - res.north_true[-1]
    res.final_drift_m = float(np.hypot(dx, dy))
    res.path_len_m = float(trip.dist_m[win.i1 - 1] - trip.dist_m[anchor])
    res.drift_pct = 100.0 * res.final_drift_m / max(res.path_len_m, 1e-6)
    return res
