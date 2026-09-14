"""Phone -> vehicle frame alignment (the ISRO 'automatic orientation detection').

We never assume the phone is lying flat and forward.  Using a GNSS-available
window we recover:

* ``R_tilt`` - the rotation that removes the phone's pitch/roll, from the mean
  GRAVITY vector, taking the level frame as x/y horizontal, z along gravity.
* ``(gz_scale, gz_bias)`` - the affine map from level-frame gyro-z [deg/s] to
  the vehicle's compass yaw-rate [deg/s], fitted against the GPS course rate.
* ``yaw_offset_deg`` - heading of the phone's level-frame +x axis relative to
  the direction of travel, from longitudinal acc/brake events (optional; only
  needed if you integrate acceleration for speed).
* ``quality`` - correlation of the calibrated yaw-rate with truth; low values
  mean the phone is not rigidly mounted and heading DR from its gyro will fail.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geo import unwrap_deg


@dataclass
class Alignment:
    R_tilt: np.ndarray             # 3x3, body -> level
    gz_scale: float
    gz_bias: float                 # deg/s
    yaw_offset_deg: float
    quality: float                 # corr(calibrated yaw-rate, truth) in [-1, 1]
    n: int

    def gyro_level_z_dps(self, gyro_rad_s: np.ndarray) -> np.ndarray:
        """Level-frame yaw-rate in deg/s for a (N,3) body-frame gyro array."""
        gl = gyro_rad_s @ self.R_tilt.T
        return np.degrees(gl[:, 2])

    def yaw_rate_compass(self, gyro_rad_s: np.ndarray) -> np.ndarray:
        return self.gz_scale * self.gyro_level_z_dps(gyro_rad_s) + self.gz_bias


def _rot_align(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Minimal rotation matrix taking unit vector a onto unit vector b."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -1 + 1e-8:                       # antiparallel: 180 deg about any axis _|_ a
        ax = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        v = np.cross(a, ax)
        v /= np.linalg.norm(v) + 1e-12
        return -np.eye(3) + 2 * np.outer(v, v)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def estimate_alignment(
    gravity: np.ndarray,       # (N,3) body-frame gravity  [m/s^2]
    gyro: np.ndarray,          # (N,3) body-frame angular rate [rad/s]
    lin_acc: np.ndarray,       # (N,3) body-frame linear acceleration [m/s^2]
    gps_course_deg: np.ndarray,  # (N,) compass course over ground [deg]
    t: np.ndarray,             # (N,) seconds
    speed_ms: np.ndarray | None = None,
) -> Alignment:
    n = len(t)
    g_mean = np.nanmean(gravity, axis=0)
    R_tilt = _rot_align(g_mean, np.array([0.0, 0.0, np.linalg.norm(g_mean)]))

    # level-frame yaw-rate vs GPS course rate
    gl_z = np.degrees((gyro @ R_tilt.T)[:, 2])
    dt = np.diff(t)
    dt[dt <= 0] = np.nan
    course_rate = np.diff(unwrap_deg(gps_course_deg)) / dt        # deg/s, compass
    x = gl_z[:-1]
    y = course_rate
    good = np.isfinite(x) & np.isfinite(y) & (np.abs(y) < 60)
    if speed_ms is not None:
        good &= np.r_[speed_ms[:-1] > 2.0]                        # course noisy at rest

    def _corr(a, b):
        if len(a) < 3 or np.std(a) < 1e-6 or np.std(b) < 1e-6:
            return 0.0
        c = float(np.corrcoef(a, b)[0, 1])
        return c if np.isfinite(c) else 0.0

    scale, bias, quality = -1.0, 0.0, 0.0
    if good.sum() >= 30:
        xg, yg = x[good], y[good]
        if np.std(yg) > 1.0 and np.std(xg) > 1.0:
            A = np.c_[xg, np.ones_like(xg)]
            s, b = np.linalg.lstsq(A, yg, rcond=None)[0]
            if np.isfinite(s) and 0.3 < abs(s) < 3.0:
                scale, bias, quality = float(s), float(b), _corr(s * xg + b, yg)
        if quality == 0.0:                                        # bias-only fallback
            scale = -1.0
            bias = float(np.nanmean(yg + xg))
            quality = _corr(-xg + bias, yg)

    # yaw offset from longitudinal accel/brake events (optional, for speed models)
    yaw_off = _estimate_yaw_offset(lin_acc, R_tilt, gps_course_deg, t)

    return Alignment(R_tilt=R_tilt, gz_scale=scale, gz_bias=bias,
                     yaw_offset_deg=yaw_off, quality=quality, n=int(good.sum()))


def _estimate_yaw_offset(lin_acc, R_tilt, course_deg, t) -> float:
    al = lin_acc @ R_tilt.T
    horiz = np.hypot(al[:, 0], al[:, 1])
    strong = horiz > np.nanpercentile(horiz, 80)
    if strong.sum() < 10:
        return 0.0
    # phase of level-frame accel vector, compass convention (0=+y "north-ish")
    phi = np.degrees(np.arctan2(al[strong, 0], al[strong, 1]))
    diff = np.radians(course_deg[strong] - phi)
    return float(np.degrees(np.arctan2(np.nanmean(np.sin(diff)),
                                       np.nanmean(np.cos(diff)))))
