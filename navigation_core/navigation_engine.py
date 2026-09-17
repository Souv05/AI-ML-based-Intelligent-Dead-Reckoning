"""Navigation Engine — orchestrates the full pipeline.

Pipeline per sample:
    StandardIMUSample
        → ImuFilter (low-pass + pothole detection)
        → GRUv2.push()  → speed_ms
        → EKFFusion.predict() + update_*()
        → NavigationOutput

The engine is sensor-agnostic: it never receives raw phone JSON.
Feed it StandardIMUSample from any adapter.

GNSS is injected separately via update_gnss() — it is not part of the
IMU stream but a parallel input from the phone/receiver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .imu.standard_imu import StandardIMUSample
from .models.gru_v2 import GRUv2
from .fusion.ekf import EKFFusion, _wrap_rad
from .preprocessing.resampler import Resampler

# Re-use the existing IMU low-pass + pothole filter
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.preprocessing.imu_filter import ImuFilter


@dataclass
class NavigationOutput:
    timestamp:      float
    latitude:       float
    longitude:      float
    east_m:         float
    north_m:        float
    speed_fwd_ms:   float
    heading_deg:    float
    gru_speed_ms:   Optional[float]
    position_std_m: float
    mode:           str           # "GNSS_AIDED" | "DR_ACTIVE" | "GNSS_REACQUIRE"
    gnss_valid:     bool
    map_matched:    bool = False
    confidence:     float = 1.0


class NavigationEngine:
    """Sensor-agnostic navigation engine.

    Instantiate once per session.  Feed it StandardIMUSamples at whatever
    rate the source provides (the internal Resampler normalises to 10 Hz
    before the GRU).  Inject GNSS fixes via update_gnss() independently.
    """

    def __init__(
        self,
        onnx_path: Path,
        metadata_path: Path,
        target_hz: float = 10.0,
    ) -> None:
        self._gru      = GRUv2(onnx_path, metadata_path)
        self._ekf      = EKFFusion()
        self._filter   = ImuFilter()
        self._resampler = Resampler(target_hz=target_hz)

        self._gnss_valid   = False
        self._gnss_lat     = 0.0
        self._gnss_lon     = 0.0
        self._gnss_speed   = 0.0
        self._gnss_hdg_deg = 0.0
        self._gnss_acc     = 50.0

        self._mode           = "DR_ACTIVE"
        self._reacq_left     = 0
        self._last_output_t  = 0.0
        self._sample_index   = 0

    # ── GNSS injection ────────────────────────────────────────────────────────
    def update_gnss(
        self,
        lat: float, lon: float,
        speed_ms: float,
        heading_deg: float,
        accuracy_m: float,
        valid: bool,
    ) -> None:
        """Call whenever a new GNSS fix arrives (independent of IMU rate)."""
        self._gnss_valid   = valid
        self._gnss_lat     = lat
        self._gnss_lon     = lon
        self._gnss_speed   = speed_ms
        self._gnss_hdg_deg = heading_deg
        self._gnss_acc     = accuracy_m

        if valid and not self._ekf.initialised:
            self._ekf.init_from_gnss(lat, lon, heading_deg, speed_ms, accuracy_m)
            self._mode = "GNSS_AIDED"

    # ── IMU push ──────────────────────────────────────────────────────────────
    def push(self, sample: StandardIMUSample) -> Optional[NavigationOutput]:
        """Feed one raw StandardIMUSample; returns output when EKF updates (10 Hz)."""
        output = None
        for resampled in self._resampler.push(sample):
            output = self._process(resampled)
        return output

    def _process(self, s: StandardIMUSample) -> Optional[NavigationOutput]:
        if not self._ekf.initialised:
            return None

        # Build 12-element vector for ImuFilter (legacy interface)
        vec12 = [s.ax, s.ay, s.az, s.gx, s.gy, s.gz,
                 s.mx, s.my, s.mz,
                 s.roll  if not math.isnan(s.roll)  else 0.0,
                 s.pitch if not math.isnan(s.pitch) else 0.0,
                 s.yaw   if not math.isnan(s.yaw)   else 0.0]
        filtered, pothole = self._filter.push(vec12)
        if pothole:
            self._gru.reset()

        # GRU speed
        gru_sample = StandardIMUSample(
            timestamp=s.timestamp, dt=s.dt,
            ax=filtered[0], ay=filtered[1], az=filtered[2],
            gx=filtered[3], gy=filtered[4], gz=filtered[5],
        )
        gru_speed = self._gru.push(gru_sample)

        # Heading from orientation (yaw if available, else EKF heading)
        if not math.isnan(s.yaw):
            heading_rad = math.radians(s.yaw)
        else:
            heading_rad = math.radians(self._ekf.heading_deg)

        dt = s.dt

        # EKF predict + updates
        self._ekf.predict(heading_rad, gru_speed or self._ekf.speed_ms, dt)
        self._ekf.update_imu_heading(heading_rad)

        if gru_speed is not None:
            self._ekf.update_gru_speed(gru_speed)

        if self._gnss_valid:
            # Large-drift re-init
            if self._ekf.gnss_position_error_m(self._gnss_lat, self._gnss_lon) > 80.0:
                self._ekf.init_from_gnss(
                    self._gnss_lat, self._gnss_lon,
                    self._ekf.heading_deg, self._ekf.speed_ms, self._gnss_acc
                )
                self._reacq_left = 5

            blend_acc = self._gnss_acc + 20.0 * (self._reacq_left / 5) if self._reacq_left > 0 else self._gnss_acc
            if self._reacq_left > 0:
                self._reacq_left -= 1

            self._ekf.update_gnss_position(self._gnss_lat, self._gnss_lon, blend_acc)
            self._ekf.update_gnss_speed(self._gnss_speed)

            if self._gnss_hdg_deg > 0 and self._gnss_speed > 1.5:
                self._ekf.update_gnss_heading(math.radians(self._gnss_hdg_deg))

            self._mode = "GNSS_REACQUIRE" if self._reacq_left > 0 else "GNSS_AIDED"
        else:
            self._mode = "DR_ACTIVE"

        # Stationary ZUPT
        accel_mag = math.sqrt(filtered[0]**2 + filtered[1]**2 + filtered[2]**2)
        gyro_mag  = math.sqrt(filtered[3]**2 + filtered[4]**2 + filtered[5]**2)
        if abs(accel_mag - 9.81) < 0.5 and gyro_mag < 0.08 and (gru_speed or 0) < 0.3:
            self._ekf.update_zupt()

        self._sample_index += 1

        return NavigationOutput(
            timestamp      = s.timestamp,
            latitude       = self._ekf.lat,
            longitude      = self._ekf.lon,
            east_m         = self._ekf.east_m,
            north_m        = self._ekf.north_m,
            speed_fwd_ms   = self._ekf.speed_ms,
            heading_deg    = self._ekf.heading_deg,
            gru_speed_ms   = gru_speed,
            position_std_m = self._ekf.pos_std_m,
            mode           = self._mode,
            gnss_valid     = self._gnss_valid,
        )

    def reset(self) -> None:
        self._gru.reset()
        self._filter.reset()
        self._resampler.reset()
        self._ekf = EKFFusion()
        self._gnss_valid = False
        self._mode = "DR_ACTIVE"
        self._reacq_left = 0
        self._sample_index = 0
