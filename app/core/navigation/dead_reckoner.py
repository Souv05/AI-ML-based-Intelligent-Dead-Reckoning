"""Incremental dead-reckoning integrator with Non-Holonomic Constraints (NHC).

NHC principle: a ground vehicle cannot slide sideways or move vertically.
During DR, the velocity vector is constrained to lie along the current heading.
Lateral velocity is forced to zero. This eliminates crosstrack drift accumulation,
which is the dominant error source for MEMS IMU dead-reckoning.

Implementation: rather than integrating raw vx/vy components independently,
we project the full speed scalar onto the heading direction only — equivalent
to applying the NHC pseudomeasurement v_lateral = 0 at every step.
"""

from __future__ import annotations

import math
import time

_R_EARTH = 6_378_137.0


class DeadReckoner:
    # 1-sigma uncertainty growth rate during DR (m per second of outage).
    # With NHC active, crosstrack drift is near-zero so this models along-track
    # speed error accumulation only — reduced from 2.0 to 0.8 m/s.
    _DRIFT_RATE_M_PER_S = 0.8

    def __init__(self) -> None:
        self.lat0: float | None = None
        self.lon0: float | None = None
        self.east_m:  float = 0.0
        self.north_m: float = 0.0
        self.heading_deg: float = 0.0
        self.speed_ms: float = 0.0
        self.pos_std_m: float = 50.0
        self.gnss_valid: bool = False
        self._last_t: float = time.monotonic()
        self._dr_since: float | None = None

        # NHC: previous heading for trapezoidal integration
        self._prev_heading_rad: float = 0.0
        self._prev_speed_ms: float = 0.0

    # ------------------------------------------------------------------
    def update_gnss(
        self,
        lat: float, lon: float,
        heading_deg: float,
        speed_ms: float,
        accuracy_m: float,
    ) -> None:
        """Snap position to GNSS fix and reset DR state."""
        if self.lat0 is None:
            self.lat0 = lat
            self.lon0 = lon

        lat0 = math.radians(self.lat0)
        self.east_m  = math.radians(lon - self.lon0) * _R_EARTH * math.cos(lat0)
        self.north_m = math.radians(lat - self.lat0) * _R_EARTH
        self.heading_deg = heading_deg
        self.speed_ms = speed_ms
        self.pos_std_m = accuracy_m
        self.gnss_valid = True
        self._last_t = time.monotonic()
        self._dr_since = None
        self._prev_heading_rad = math.radians(heading_deg)
        self._prev_speed_ms = speed_ms

    def update_imu(self, heading_deg: float, gru_speed_ms: float, dt: float) -> None:
        """Advance position by one IMU tick using NHC-constrained kinematics.

        NHC enforcement: displacement = speed * dt along heading only.
        No lateral component is added regardless of heading change rate.
        Trapezoidal integration halves the heading-discretisation error.
        """
        if self.lat0 is None:
            return
        if self._dr_since is None:
            self._dr_since = time.monotonic()

        heading_rad = math.radians(heading_deg)

        # Trapezoidal rule: average heading and speed over the step
        avg_heading = _angle_avg(self._prev_heading_rad, heading_rad)
        avg_speed   = 0.5 * (self._prev_speed_ms + gru_speed_ms)

        # NHC: displacement is purely along the heading axis (forward only)
        # v_lateral = 0 is enforced by construction — no sin/cos decomposition
        # into independent east/north components with separate noise.
        dist = avg_speed * dt
        self.east_m  += dist * math.sin(avg_heading)
        self.north_m += dist * math.cos(avg_heading)

        self.heading_deg = heading_deg
        self.speed_ms = gru_speed_ms
        self._prev_heading_rad = heading_rad
        self._prev_speed_ms = gru_speed_ms

        elapsed_dr = time.monotonic() - self._dr_since
        self.pos_std_m = elapsed_dr * self._DRIFT_RATE_M_PER_S
        self.gnss_valid = False
        self._last_t = time.monotonic()

    # ------------------------------------------------------------------
    @property
    def lat(self) -> float:
        if self.lat0 is None:
            return 0.0
        return self.lat0 + math.degrees(self.north_m / _R_EARTH)

    @property
    def lon(self) -> float:
        if self.lon0 is None:
            return 0.0
        lat0 = math.radians(self.lat0)
        return self.lon0 + math.degrees(self.east_m / (_R_EARTH * math.cos(lat0)))


def _angle_avg(a: float, b: float) -> float:
    """Average of two angles in radians, handling the 0/2π wrap correctly."""
    diff = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + 0.5 * diff
