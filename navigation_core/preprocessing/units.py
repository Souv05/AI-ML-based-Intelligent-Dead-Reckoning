"""Unit conversion utilities.

All navigation core components work in SI units:
    acceleration : m/s²
    gyro rate    : rad/s
    magnetometer : µT
"""

from __future__ import annotations

import math

_G = 9.80665   # standard gravity (m/s²)


def accel_to_ms2(value: float, unit: str) -> float:
    if unit in ("m/s2", "m/s²"):
        return value
    if unit == "g":
        return value * _G
    if unit == "cm/s2":
        return value * 0.01
    raise ValueError(f"Unsupported acceleration unit: {unit!r}")


def gyro_to_rad_s(value: float, unit: str) -> float:
    if unit == "rad/s":
        return value
    if unit in ("deg/s", "°/s"):
        return value * math.pi / 180.0
    if unit == "mdps":          # milli-degrees per second (some MEMS IMUs)
        return value * math.pi / 180_000.0
    raise ValueError(f"Unsupported gyro unit: {unit!r}")


def mag_to_ut(value: float, unit: str) -> float:
    if unit in ("uT", "µT"):
        return value
    if unit == "mT":
        return value * 1000.0
    if unit == "T":
        return value * 1_000_000.0
    if unit == "gauss":
        return value * 100.0
    raise ValueError(f"Unsupported magnetometer unit: {unit!r}")
