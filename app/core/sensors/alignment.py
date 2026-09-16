"""Phone-to-vehicle alignment engine.

Automatically estimates the rotation from the phone's sensor frame to the
vehicle's forward/right/up frame, regardless of how the phone is mounted on
the dashboard.

Two-phase calibration
---------------------
Phase 1 — Static (runs while vehicle is stationary):
    Collect gravity vector samples → compute roll and pitch offsets that
    level the phone's accelerometer axes to the vehicle horizontal plane.
    Completes after STATIC_N_SAMPLES (~1 s at 50 Hz) of confirmed stillness.

Phase 2 — Dynamic (runs while driving):
    Compare phone compass heading against GPS course-over-ground to estimate
    yaw (heading) offset — corrects for the phone being rotated around the
    vertical axis relative to the vehicle's forward direction.
    Completes after DYNAMIC_N_SAMPLES (~3 s of straight driving at speed).

Outputs
-------
- correct_heading(heading_rad) → float   apply yaw offset to compass heading
- transform_acc(ax, ay, az)    → tuple   rotate acc into vehicle frame
- transform_gyro(gx, gy, gz)  → tuple   rotate gyro into vehicle frame
- status                       → str     UNCALIBRATED | STATIC_DONE | CALIBRATED
- yaw_offset_deg / pitch_offset_deg / roll_offset_deg  (readable diagnostics)
"""

from __future__ import annotations

import math
from enum import Enum

import numpy as np

_G = 9.80665
_STATIC_N_SAMPLES  = 50   # ~1 s at 50 Hz
_DYNAMIC_N_SAMPLES = 60   # ~1.2 s of usable GPS+IMU pairs
_MIN_SPEED_MS      = 3.0  # only collect dynamic samples above this speed


class AlignState(str, Enum):
    UNCALIBRATED   = "UNCALIBRATED"
    STATIC_DONE    = "STATIC_DONE"    # roll/pitch known; yaw still unknown
    CALIBRATED     = "CALIBRATED"     # full 3-axis alignment complete


class PhoneAligner:
    """Auto-estimates phone→vehicle rotation from gravity and GPS course."""

    def __init__(self) -> None:
        self._R = np.eye(3, dtype=np.float64)   # phone→vehicle rotation matrix
        self._yaw_offset_rad:   float = 0.0
        self._pitch_offset_rad: float = 0.0
        self._roll_offset_rad:  float = 0.0

        self._static_buf:  list[list[float]] = []
        self._dynamic_buf: list[tuple[float, float]] = []  # (imu_hdg, gps_hdg)

        self.state = AlignState.UNCALIBRATED

    # ── Phase 1: static ──────────────────────────────────────────────────────

    def push_static(
        self,
        acc_x: float, acc_y: float, acc_z: float,
        gyro_mag: float,
    ) -> None:
        """Call on every IMU tick while the vehicle is confirmed stationary.

        gyro_mag is the magnitude of the gyro vector (rad/s); samples are
        rejected if the phone is being moved (gyro_mag >= 0.05 rad/s).
        """
        if self.state != AlignState.UNCALIBRATED:
            return
        if gyro_mag >= 0.05:
            return
        self._static_buf.append([acc_x, acc_y, acc_z])
        if len(self._static_buf) >= _STATIC_N_SAMPLES:
            self._compute_static()

    def _compute_static(self) -> None:
        g_phone = np.mean(self._static_buf, axis=0)
        g_phone_n = g_phone / (np.linalg.norm(g_phone) + 1e-9)

        # Vehicle "down" axis in vehicle frame is (0, 0, -1).
        # We map measured gravity (in phone frame) → vehicle down to find
        # the tilt offsets.
        #   pitch: rotation around phone Y to align X with vehicle forward
        #   roll:  rotation around phone X to level phone Y
        self._pitch_offset_rad = math.asin(float(np.clip(g_phone_n[0], -1.0, 1.0)))
        self._roll_offset_rad  = math.asin(float(np.clip(-g_phone_n[1], -1.0, 1.0)))

        self._rebuild_R()
        self._static_buf.clear()
        self.state = AlignState.STATIC_DONE

    # ── Phase 2: dynamic ─────────────────────────────────────────────────────

    def push_dynamic(
        self,
        imu_heading_rad: float,
        gps_heading_rad: float,
        speed_ms: float,
    ) -> None:
        """Call on every IMU tick while driving.

        gps_heading_rad is the GPS course-over-ground (only meaningful at speed).
        Samples are only collected when speed_ms >= _MIN_SPEED_MS.
        """
        if self.state != AlignState.STATIC_DONE:
            return
        if speed_ms < _MIN_SPEED_MS:
            return
        self._dynamic_buf.append((
            _wrap_rad(imu_heading_rad),
            _wrap_rad(gps_heading_rad),
        ))
        if len(self._dynamic_buf) >= _DYNAMIC_N_SAMPLES:
            self._compute_dynamic()

    def _compute_dynamic(self) -> None:
        diffs = [_wrap_rad(gps - imu) for imu, gps in self._dynamic_buf]
        # Median is robust against turns mid-collection
        self._yaw_offset_rad = float(np.median(diffs))
        self._rebuild_R()
        self._dynamic_buf.clear()
        self.state = AlignState.CALIBRATED

    # ── Rotation matrix ──────────────────────────────────────────────────────

    def _rebuild_R(self) -> None:
        """Reconstruct R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
        cy, sy = math.cos(self._yaw_offset_rad),   math.sin(self._yaw_offset_rad)
        cp, sp = math.cos(self._pitch_offset_rad), math.sin(self._pitch_offset_rad)
        cr, sr = math.cos(self._roll_offset_rad),  math.sin(self._roll_offset_rad)

        Rz = np.array([[cy, -sy, 0.0],
                       [sy,  cy, 0.0],
                       [0.0, 0.0, 1.0]])
        Ry = np.array([[ cp, 0.0, sp],
                       [0.0, 1.0, 0.0],
                       [-sp, 0.0, cp]])
        Rx = np.array([[1.0, 0.0,  0.0],
                       [0.0,  cr, -sr],
                       [0.0,  sr,  cr]])
        self._R = Rz @ Ry @ Rx

    # ── Public transforms ────────────────────────────────────────────────────

    def transform_acc(
        self, ax: float, ay: float, az: float
    ) -> tuple[float, float, float]:
        """Rotate accelerometer vector from phone frame to vehicle frame."""
        v = self._R @ np.array([ax, ay, az])
        return float(v[0]), float(v[1]), float(v[2])

    def transform_gyro(
        self, gx: float, gy: float, gz: float
    ) -> tuple[float, float, float]:
        """Rotate gyroscope vector from phone frame to vehicle frame."""
        v = self._R @ np.array([gx, gy, gz])
        return float(v[0]), float(v[1]), float(v[2])

    def correct_heading(self, heading_rad: float) -> float:
        """Apply yaw offset to compass/fusion heading."""
        return _wrap_rad(heading_rad + self._yaw_offset_rad)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def yaw_offset_deg(self) -> float:
        return math.degrees(self._yaw_offset_rad)

    @property
    def pitch_offset_deg(self) -> float:
        return math.degrees(self._pitch_offset_rad)

    @property
    def roll_offset_deg(self) -> float:
        return math.degrees(self._roll_offset_rad)

    @property
    def calibrated(self) -> bool:
        return self.state == AlignState.CALIBRATED

    def as_dict(self) -> dict:
        return {
            "state":           self.state.value,
            "yaw_offset_deg":  round(self.yaw_offset_deg,   1),
            "pitch_offset_deg": round(self.pitch_offset_deg, 1),
            "roll_offset_deg": round(self.roll_offset_deg,  1),
        }


def _wrap_rad(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
