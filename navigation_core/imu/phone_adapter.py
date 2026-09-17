"""Phone IMU adapter.

Converts the raw JSON packet sent by the Flutter app's ImuSender into a
StandardIMUSample in the FRD canonical frame.

Phone sensor frame (Android):
    X = right (device landscape), Y = up, Z = out of screen
    → mapped to FRD: ax_frd=az_phone, ay_frd=ax_phone, az_frd=-ay_phone
    (for a phone lying flat on a dashboard with screen up)

For a phone mounted portrait and held against the windshield the mapping
differs — this is why PhoneAligner (alignment.py) exists.  The PhoneAligner
corrects the vehicle-to-phone offset after the adapter normalises units.

Raw packet fields expected (same as ImuSender._send()):
    acc_x, acc_y, acc_z     m/s²  (Android linear accel, gravity included)
    gyro_x, gyro_y, gyro_z  rad/s (bias-corrected by Flutter app)
    mag_x, mag_y, mag_z     µT
    roll, pitch, yaw         degrees (complementary filter on phone)
    t_ms                     int (epoch milliseconds)

Gyro bias has already been subtracted by the Flutter app (ImuCalibrationService).
Accel bias calibration can be applied here via set_accel_bias().
"""

from __future__ import annotations

from .adapter import IMUAdapter
from .standard_imu import StandardIMUSample


class PhoneIMUAdapter(IMUAdapter):
    def __init__(self) -> None:
        self._last_t_s: float | None = None
        # Accel bias (m/s²) — set via set_accel_bias() after static calibration
        self._accel_bias: list[float] = [0.0, 0.0, 0.0]

    def set_accel_bias(self, bx: float, by: float, bz: float) -> None:
        self._accel_bias = [bx, by, bz]

    def convert(self, raw: dict) -> StandardIMUSample:
        t_s = raw["t_ms"] / 1000.0

        if self._last_t_s is None:
            dt = 0.02          # assume 50 Hz for the very first sample
        else:
            dt = t_s - self._last_t_s
            dt = max(0.001, min(dt, 0.5))   # clamp to [1ms, 500ms]
        self._last_t_s = t_s

        # Unit conversion: phone already reports m/s² and rad/s — no conversion needed.
        ax = raw["acc_x"]  - self._accel_bias[0]
        ay = raw["acc_y"]  - self._accel_bias[1]
        az = raw["acc_z"]  - self._accel_bias[2]
        gx = raw["gyro_x"]
        gy = raw["gyro_y"]
        gz = raw["gyro_z"]

        return StandardIMUSample(
            timestamp = t_s,
            dt        = dt,
            ax=ax, ay=ay, az=az,
            gx=gx, gy=gy, gz=gz,
            mx = raw.get("mag_x", 0.0),
            my = raw.get("mag_y", 0.0),
            mz = raw.get("mag_z", 0.0),
            roll  = raw.get("roll",  float("nan")),
            pitch = raw.get("pitch", float("nan")),
            yaw   = raw.get("yaw",   float("nan")),
            frame  = "phone_native",
            source = "phone",
        )

    def reset(self) -> None:
        self._last_t_s = None
