"""Extended Kalman Filter for GNSS + IMU fusion.

State vector (4 elements):
    x = [east_m, north_m, heading_rad, speed_ms]

NHC is built into the state parameterisation: velocity is always
    v_east  = speed * sin(heading)
    v_north = speed * cos(heading)
so lateral velocity is identically zero by construction — no separate
pseudomeasurement needed.

Prediction step uses the IMU heading and GRU speed as process inputs.
Update steps accept four measurement types independently:
    1. IMU heading    (always, ~50 Hz)
    2. GRU speed      (once window is warm, ~50 Hz)
    3. GNSS position  (when gnss_valid, ~1 Hz from phone)
    4. GNSS speed     (when gnss_valid, ~1 Hz)

Noise tuning:
    Process noise Q reflects how fast each state can drift per second.
    Measurement noise R reflects sensor accuracy.  Both are diagonals —
    cross-correlations are small enough to ignore at this fidelity level.
"""

from __future__ import annotations

import math

import numpy as np

_R_EARTH = 6_378_137.0

# ── Process noise (std² per second, then scaled by dt in predict) ────────────
_Q_EAST_M2_PER_S    = 0.01   # position drifts ~0.1 m/√s (NHC-constrained)
_Q_NORTH_M2_PER_S   = 0.01
_Q_HDG_RAD2_PER_S   = 0.005  # heading noise ~4 deg/√s (gyro bias)
_Q_SPD_M2S2_PER_S   = 0.5    # speed noise ~0.7 m/s /√s (GRU uncertainty)

# ── Measurement noise (fixed 1-sigma²) ───────────────────────────────────────
_R_IMU_HDG_RAD2     = (math.radians(5)) ** 2   # magnetometer heading ±5 deg
_R_GRU_SPD_M2S2     = 1.0 ** 2                 # GRU speed ±1 m/s
_R_GNSS_SPD_M2S2    = 0.3 ** 2                 # GNSS Doppler speed ±0.3 m/s
_R_ZUPT_M2S2        = 0.05 ** 2                # ZUPT: near-zero speed, very tight


class EKFFusion:
    """4-state EKF fusing IMU heading, GRU speed, and GNSS position/speed."""

    def __init__(self) -> None:
        # State: [east_m, north_m, heading_rad, speed_ms]
        self.x = np.zeros(4, dtype=np.float64)
        # Covariance: start uncertain
        self.P = np.diag([100.0**2, 100.0**2,
                          math.radians(90)**2, 10.0**2])

        self.lat0: float | None = None
        self.lon0: float | None = None
        self.initialised: bool = False

        # For external access
        self.pos_std_m: float = 100.0

    # ── Initialisation ────────────────────────────────────────────────────────
    def init_from_gnss(
        self,
        lat: float, lon: float,
        heading_deg: float,
        speed_ms: float,
        accuracy_m: float,
    ) -> None:
        self.lat0 = lat
        self.lon0 = lon
        lat0_rad = math.radians(lat)
        east  = math.radians(lon - lon) * _R_EARTH * math.cos(lat0_rad)
        north = math.radians(lat - lat) * _R_EARTH
        self.x = np.array([east, north,
                            math.radians(heading_deg), speed_ms])
        self.P = np.diag([accuracy_m**2, accuracy_m**2,
                          math.radians(10)**2, 1.0**2])
        self.initialised = True
        self._update_pos_std()

    # ── Prediction step ───────────────────────────────────────────────────────
    def predict(self, heading_rad: float, speed_ms: float, dt: float) -> None:
        """Propagate state forward by dt using NHC kinematics.

        IMU heading and GRU speed are used as process inputs (not measurements
        here — they are also fused as measurements separately, which gives the
        EKF a chance to correct them).
        """
        if not self.initialised or dt <= 0:
            return

        e, n, h, v = self.x
        # Use current state heading/speed for prediction (not raw IMU directly)
        # to keep the EKF self-consistent; raw IMU feeds the update step.
        sin_h, cos_h = math.sin(h), math.cos(h)
        dist = v * dt

        # Predicted state
        e_new = e + dist * sin_h
        n_new = n + dist * cos_h
        h_new = h   # heading is updated via IMU measurement, not process model
        v_new = v   # speed is updated via GRU measurement, not process model

        self.x = np.array([e_new, n_new, h_new, v_new])

        # Jacobian of process model w.r.t. state
        F = np.eye(4)
        F[0, 2] = dist * cos_h    # ∂east/∂heading
        F[0, 3] = sin_h * dt      # ∂east/∂speed
        F[1, 2] = -dist * sin_h   # ∂north/∂heading
        F[1, 3] = cos_h * dt      # ∂north/∂speed

        # Process noise (scaled by dt)
        Q = np.diag([
            _Q_EAST_M2_PER_S  * dt,
            _Q_NORTH_M2_PER_S * dt,
            _Q_HDG_RAD2_PER_S * dt,
            _Q_SPD_M2S2_PER_S * dt,
        ])

        self.P = F @ self.P @ F.T + Q
        self._update_pos_std()

    # ── Measurement updates ───────────────────────────────────────────────────
    def update_imu_heading(self, heading_rad: float) -> None:
        """Fuse magnetometer/complementary-filter heading."""
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 1.0, 0.0]])
        innovation = _wrap_rad(heading_rad - self.x[2])
        self._scalar_update(H, innovation, _R_IMU_HDG_RAD2)
        self.x[2] = _wrap_rad(self.x[2])

    def update_gru_speed(self, speed_ms: float) -> None:
        """Fuse GRU forward-speed estimate."""
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 1.0]])
        innovation = speed_ms - self.x[3]
        self._scalar_update(H, innovation, _R_GRU_SPD_M2S2)
        self.x[3] = max(self.x[3], 0.0)  # speed cannot be negative

    def update_gnss_position(
        self, lat: float, lon: float, accuracy_m: float
    ) -> None:
        """Fuse GNSS lat/lon fix."""
        if not self.initialised or self.lat0 is None:
            return
        lat0_rad = math.radians(self.lat0)
        meas_east  = math.radians(lon - self.lon0) * _R_EARTH * math.cos(lat0_rad)
        meas_north = math.radians(lat - self.lat0) * _R_EARTH

        H = np.array([[1.0, 0.0, 0.0, 0.0],
                      [0.0, 1.0, 0.0, 0.0]])
        z = np.array([meas_east, meas_north])
        innov = z - H @ self.x
        R = np.diag([accuracy_m**2, accuracy_m**2])
        self._vector_update(H, innov, R)
        self._update_pos_std()

    def update_gnss_heading(self, heading_rad: float) -> None:
        """Fuse GPS course-over-ground when speed > threshold.

        GPS course is far more reliable than magnetometer in a vehicle.
        Use only when gnss_speed > 1.5 m/s (course is meaningless at low speed).
        Noise: ±1 deg (tight) vs ±5 deg for magnetometer.
        """
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 1.0, 0.0]])
        innovation = _wrap_rad(heading_rad - self.x[2])
        self._scalar_update(H, innovation, math.radians(1.5) ** 2)
        self.x[2] = _wrap_rad(self.x[2])

    def update_road_bearing(self, bearing_rad: float, std_rad: float = 0.087) -> None:
        """Fuse road bearing from map matcher as a tight heading pseudomeasurement.

        std_rad defaults to ~5 degrees (road direction is well-known).
        This is the strongest heading correction available during DR mode.
        """
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 1.0, 0.0]])
        innovation = _wrap_rad(bearing_rad - self.x[2])
        self._scalar_update(H, innovation, std_rad ** 2)
        self.x[2] = _wrap_rad(self.x[2])

    def update_zupt(self) -> None:
        """Zero Velocity Update — inject speed=0 with tight noise when stationary.

        Call only when the vehicle is confidently stationary (GRU speed near
        zero AND accel magnitude close to 1 g).  Prevents EKF position drift
        caused by residual heading errors multiplied by non-zero speed.
        """
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 1.0]])
        innovation = 0.0 - self.x[3]
        self._scalar_update(H, innovation, _R_ZUPT_M2S2)
        self.x[3] = max(self.x[3], 0.0)

    def update_gnss_speed(self, speed_ms: float, accuracy_ms: float = 0.3) -> None:
        """Fuse GNSS Doppler speed."""
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 1.0]])
        innovation = speed_ms - self.x[3]
        R = max(accuracy_ms, 0.1) ** 2
        self._scalar_update(H, innovation, R)
        self.x[3] = max(self.x[3], 0.0)

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _scalar_update(
        self, H: np.ndarray, innovation: float, R: float
    ) -> None:
        S = float(H @ self.P @ H.T) + R
        if S <= 0 or not math.isfinite(S):
            return  # degenerate — skip rather than produce NaN
        K = (self.P @ H.T) / S           # (4,1) gain
        self.x = self.x + K.flatten() * innovation
        self.P = (np.eye(4) - K @ H) @ self.P
        self.P = 0.5 * (self.P + self.P.T)  # symmetrise
        self._repair_P()

    def _vector_update(
        self, H: np.ndarray, innov: np.ndarray, R: np.ndarray
    ) -> None:
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innov
        self.P = (np.eye(4) - K @ H) @ self.P
        self.P = 0.5 * (self.P + self.P.T)
        self._repair_P()

    def _repair_P(self) -> None:
        """Clamp P diagonal to positive values; reset if NaN/Inf crept in."""
        if not np.all(np.isfinite(self.P)):
            # Full reset to a safe uncertain covariance
            self.P = np.diag([50.0**2, 50.0**2,
                              math.radians(45)**2, 5.0**2])
            return
        # Enforce minimum diagonal (P must be positive definite)
        _min = np.array([0.01**2, 0.01**2, math.radians(0.1)**2, 0.01**2])
        for i in range(4):
            if self.P[i, i] < _min[i]:
                self.P[i, i] = _min[i]

    def _update_pos_std(self) -> None:
        v = 0.5 * (self.P[0, 0] + self.P[1, 1])
        self.pos_std_m = float(math.sqrt(v)) if v >= 0 and math.isfinite(v) else 999.0

    # ── Output helpers ────────────────────────────────────────────────────────
    @property
    def east_m(self) -> float:
        return float(self.x[0])

    @property
    def north_m(self) -> float:
        return float(self.x[1])

    @property
    def heading_deg(self) -> float:
        return float(math.degrees(self.x[2]))

    @property
    def speed_ms(self) -> float:
        return float(self.x[3])

    @property
    def lat(self) -> float:
        if self.lat0 is None:
            return 0.0
        return self.lat0 + math.degrees(self.north_m / _R_EARTH)

    @property
    def lon(self) -> float:
        if self.lat0 is None or self.lon0 is None:
            return 0.0
        lat0_rad = math.radians(self.lat0)
        return self.lon0 + math.degrees(
            self.east_m / (_R_EARTH * math.cos(lat0_rad))
        )


def _wrap_rad(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
