"""Extended Kalman Filter for GNSS + IMU fusion.

State vector (5 elements):
    x = [east_m, north_m, vE_ms, vN_ms, heading_rad]

Explicit NHC (Non-Holonomic Constraint):
    Lateral velocity  z_nhc = vE·cos(ψ) - vN·sin(ψ) = 0
    Jacobian H_nhc = [0, 0, cos(ψ), -sin(ψ), v·sin(ψ)·... ≈ 0 at low speed]
    This feeds back into heading: if vE/vN drift off the heading direction,
    the NHC update pulls ψ back. This is the key accuracy improvement over
    the implicit 4-state formulation.

Derived quantities:
    forward_speed = vE·sin(ψ) + vN·cos(ψ)
    speed_mag     = sqrt(vE² + vN²)

Update steps:
    1. IMU heading       (always, ~50 Hz)
    2. GRU forward-speed (once window is warm, ~50 Hz)
    3. GNSS position     (when gnss_valid, ~1 Hz)
    4. GNSS speed        (when gnss_valid, ~1 Hz)
    5. GPS CoG heading   (when gnss_valid and speed > threshold)
    6. NHC pseudo-meas   (every predict step, ~50 Hz)
    7. ZUPT              (when stationary)
    8. Road bearing      (from map matcher)
"""

from __future__ import annotations

import math

import numpy as np

_R_EARTH = 6_378_137.0

# ── Process noise ─────────────────────────────────────────────────────────────
_Q_EAST_M2_PER_S   = 0.01   # ~0.1 m/√s position
_Q_NORTH_M2_PER_S  = 0.01
_Q_VE_M2S2_PER_S   = 0.5    # ~0.7 m/s/√s velocity (GRU drives this)
_Q_VN_M2S2_PER_S   = 0.5
_Q_HDG_RAD2_PER_S  = 0.005  # ~4 deg/√s heading (gyro bias)

# ── Measurement noise ─────────────────────────────────────────────────────────
_R_IMU_HDG_RAD2    = math.radians(5) ** 2    # magnetometer ±5 deg
_R_GPS_HDG_RAD2    = math.radians(1.5) ** 2  # GPS CoG ±1.5 deg
_R_GRU_SPD_M2S2    = 1.0 ** 2                # GRU speed ±1 m/s
_R_GNSS_SPD_M2S2   = 0.3 ** 2               # GNSS Doppler ±0.3 m/s
_R_ZUPT_M2S2       = 0.05 ** 2              # ZUPT very tight
_R_NHC_M2S2        = 0.1 ** 2               # NHC: lateral speed ≤ 0.1 m/s

# ── Innovation gating (chi-squared) ──────────────────────────────────────────
# Reject a GNSS measurement whose NIS = innovᵀ S⁻¹ innov exceeds the threshold.
# χ²(2, 0.999) ≈ 13.8; using 25.0 matches 17E notebook and gives extra headroom
# for genuine large GPS jumps that aren't multipath (e.g. tunnel exit).
# Scalar heading gate: 3-sigma → NIS > 9.0 rejects an outlier GPS CoG reading.
_GATE_CHI2_POS  = 25.0   # 2-DOF position gate
_GATE_CHI2_HDG  = 9.0    # 1-DOF heading gate (3σ)


class EKFFusion:
    """5-state EKF with explicit NHC for ground-vehicle dead reckoning."""

    def __init__(self) -> None:
        # State: [east_m, north_m, vE_ms, vN_ms, heading_rad]
        self.x = np.zeros(5, dtype=np.float64)
        self.P = np.diag([100.0**2, 100.0**2,
                          5.0**2, 5.0**2,
                          math.radians(90)**2])

        self.lat0: float | None = None
        self.lon0: float | None = None
        self.initialised: bool = False
        self.pos_std_m: float = 100.0

    # ── Initialisation ────────────────────────────────────────────────────────
    def init_from_gnss(
        self,
        lat: float, lon: float,
        heading_deg: float,
        speed_ms: float,
        accuracy_m: float,
    ) -> None:
        accuracy_m = max(accuracy_m, 8.0)
        self.lat0 = lat
        self.lon0 = lon
        h = math.radians(heading_deg)
        vE = speed_ms * math.sin(h)
        vN = speed_ms * math.cos(h)
        self.x = np.array([0.0, 0.0, vE, vN, h])
        self.P = np.diag([accuracy_m**2, accuracy_m**2,
                          1.0**2, 1.0**2,
                          math.radians(10)**2])
        self.initialised = True
        self._update_pos_std()

    # ── Prediction step ───────────────────────────────────────────────────────
    def predict(self, heading_rad: float, speed_ms: float, dt: float) -> None:
        """Propagate with NHC kinematics, then apply NHC pseudomeasurement."""
        if not self.initialised or dt <= 0:
            return

        e, n, vE, vN, h = self.x

        # Propagate position from velocity
        e_new = e + vE * dt
        n_new = n + vN * dt
        # Heading and velocity propagated by measurements; hold in process model
        self.x = np.array([e_new, n_new, vE, vN, h])

        # Jacobian F (5×5)
        F = np.eye(5)
        F[0, 2] = dt   # ∂east/∂vE
        F[1, 3] = dt   # ∂north/∂vN

        Q = np.diag([
            _Q_EAST_M2_PER_S  * dt,
            _Q_NORTH_M2_PER_S * dt,
            _Q_VE_M2S2_PER_S  * dt,
            _Q_VN_M2S2_PER_S  * dt,
            _Q_HDG_RAD2_PER_S * dt,
        ])

        self.P = F @ self.P @ F.T + Q

        # Apply NHC immediately after predict
        self._apply_nhc()
        self._update_pos_std()

    # ── NHC pseudomeasurement ─────────────────────────────────────────────────
    def _apply_nhc(self) -> None:
        """z = vE·cos(ψ) - vN·sin(ψ) = 0  (lateral velocity = 0)."""
        _, _, vE, vN, h = self.x
        sin_h, cos_h = math.sin(h), math.cos(h)

        z_nhc = vE * cos_h - vN * sin_h   # should be 0

        # H = [0, 0, cos(ψ), -sin(ψ), -vE·sin(ψ) - vN·cos(ψ)]
        #                                 ↑ ∂z/∂ψ = -forward_speed
        fwd = vE * sin_h + vN * cos_h
        H = np.array([[0.0, 0.0, cos_h, -sin_h, -fwd]])

        self._scalar_update(H, -z_nhc, _R_NHC_M2S2)
        self.x[4] = _wrap_rad(self.x[4])

    # ── Measurement updates ───────────────────────────────────────────────────
    def update_imu_heading(self, heading_rad: float) -> None:
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 0.0, 1.0]])
        innovation = _wrap_rad(heading_rad - self.x[4])
        self._scalar_update(H, innovation, _R_IMU_HDG_RAD2)
        self.x[4] = _wrap_rad(self.x[4])
        self._velocity_from_heading()

    def update_gru_speed(self, speed_ms: float) -> None:
        """Fuse GRU forward-speed: z = vE·sin(ψ) + vN·cos(ψ)."""
        if not self.initialised:
            return
        _, _, vE, vN, h = self.x
        sin_h, cos_h = math.sin(h), math.cos(h)
        z_hat = vE * sin_h + vN * cos_h
        innovation = speed_ms - z_hat
        # H = [0, 0, sin(ψ), cos(ψ), vE·cos(ψ) - vN·sin(ψ)]
        lat_v = vE * cos_h - vN * sin_h
        H = np.array([[0.0, 0.0, sin_h, cos_h, lat_v]])
        self._scalar_update(H, innovation, _R_GRU_SPD_M2S2)
        self.x[3] = self.x[3]  # vN can be negative on reverse — no clamp

    def update_gnss_position(
        self, lat: float, lon: float, accuracy_m: float
    ) -> None:
        if not self.initialised or self.lat0 is None:
            return
        lat0_rad = math.radians(self.lat0)
        meas_east  = math.radians(lon - self.lon0) * _R_EARTH * math.cos(lat0_rad)
        meas_north = math.radians(lat - self.lat0) * _R_EARTH

        H = np.array([[1.0, 0.0, 0.0, 0.0, 0.0],
                      [0.0, 1.0, 0.0, 0.0, 0.0]])
        z = np.array([meas_east, meas_north])
        innov = z - H @ self.x
        R = np.diag([accuracy_m**2, accuracy_m**2])

        # Chi-squared innovation gate: NIS = innovᵀ S⁻¹ innov
        # Rejects multipath spikes / frozen fixes that slip past the health monitor.
        S = H @ self.P @ H.T + R
        try:
            nis = float(innov @ np.linalg.inv(S) @ innov)
        except np.linalg.LinAlgError:
            nis = 0.0
        if nis > _GATE_CHI2_POS:
            return

        self._vector_update(H, innov, R)
        self._update_pos_std()

    def update_gnss_heading(self, heading_rad: float) -> None:
        """GPS CoG heading — very tight noise, use only when speed > 1.5 m/s."""
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 0.0, 1.0]])
        innovation = _wrap_rad(heading_rad - self.x[4])
        # 3-sigma scalar gate: rejects implausible CoG jumps
        S = float(H @ self.P @ H.T) + _R_GPS_HDG_RAD2
        if S > 0 and (innovation ** 2 / S) > _GATE_CHI2_HDG:
            return
        self._scalar_update(H, innovation, _R_GPS_HDG_RAD2)
        self.x[4] = _wrap_rad(self.x[4])
        self._velocity_from_heading()

    def update_gnss_speed(self, speed_ms: float, accuracy_ms: float = 0.3) -> None:
        """Fuse GNSS Doppler speed as forward speed."""
        if not self.initialised:
            return
        _, _, vE, vN, h = self.x
        sin_h, cos_h = math.sin(h), math.cos(h)
        z_hat = vE * sin_h + vN * cos_h
        innovation = speed_ms - z_hat
        lat_v = vE * cos_h - vN * sin_h
        H = np.array([[0.0, 0.0, sin_h, cos_h, lat_v]])
        R = max(accuracy_ms, 0.1) ** 2
        self._scalar_update(H, innovation, R)

    def update_road_bearing(self, bearing_rad: float, std_rad: float = 0.087) -> None:
        if not self.initialised:
            return
        H = np.array([[0.0, 0.0, 0.0, 0.0, 1.0]])
        innovation = _wrap_rad(bearing_rad - self.x[4])
        self._scalar_update(H, innovation, std_rad ** 2)
        self.x[4] = _wrap_rad(self.x[4])
        self._velocity_from_heading()

    def update_zupt(self) -> None:
        """ZUPT: inject vE=0 and vN=0 with tight noise when stationary."""
        if not self.initialised:
            return
        # Two scalar updates: vE=0, vN=0
        H_vE = np.array([[0.0, 0.0, 1.0, 0.0, 0.0]])
        H_vN = np.array([[0.0, 0.0, 0.0, 1.0, 0.0]])
        self._scalar_update(H_vE, -self.x[2], _R_ZUPT_M2S2)
        self._scalar_update(H_vN, -self.x[3], _R_ZUPT_M2S2)

    def gnss_position_error_m(self, lat: float, lon: float) -> float:
        if not self.initialised or self.lat0 is None:
            return 0.0
        lat0_rad = math.radians(self.lat0)
        meas_east  = math.radians(lon - self.lon0) * _R_EARTH * math.cos(lat0_rad)
        meas_north = math.radians(lat - self.lat0) * _R_EARTH
        return float(math.hypot(meas_east - self.x[0], meas_north - self.x[1]))

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _velocity_from_heading(self) -> None:
        """After a heading update, re-project velocity onto new heading direction.

        Preserves speed magnitude, rotates velocity vector to match new ψ.
        This keeps vE/vN consistent with heading after a heading correction.
        """
        _, _, vE, vN, h = self.x
        spd = math.hypot(vE, vN)
        self.x[2] = spd * math.sin(h)
        self.x[3] = spd * math.cos(h)

    def _scalar_update(self, H: np.ndarray, innovation: float, R: float) -> None:
        S = float(H @ self.P @ H.T) + R
        if S <= 0 or not math.isfinite(S):
            return
        K = (self.P @ H.T) / S          # shape (5,1) or (5,)
        k = K.flatten()
        self.x = self.x + k * innovation
        IKH = np.eye(5) - np.outer(k, H.flatten())
        self.P = IKH @ self.P @ IKH.T + R * np.outer(k, k)
        self.P = 0.5 * (self.P + self.P.T)
        self._repair_P()

    def _vector_update(self, H: np.ndarray, innov: np.ndarray, R: np.ndarray) -> None:
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innov
        IKH = np.eye(5) - K @ H
        self.P = IKH @ self.P @ IKH.T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)
        self._repair_P()

    def _repair_P(self) -> None:
        if not np.all(np.isfinite(self.P)):
            self.P = np.diag([50.0**2, 50.0**2, 3.0**2, 3.0**2,
                              math.radians(45)**2])
            return
        _min = np.array([0.01**2, 0.01**2, 0.01**2, 0.01**2,
                         math.radians(0.1)**2])
        for i in range(5):
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
        return float(math.degrees(self.x[4]))

    @property
    def speed_ms(self) -> float:
        """Forward speed (signed projection onto heading)."""
        _, _, vE, vN, h = self.x
        return float(vE * math.sin(h) + vN * math.cos(h))

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
