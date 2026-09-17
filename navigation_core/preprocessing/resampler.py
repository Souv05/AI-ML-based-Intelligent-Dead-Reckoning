"""Resample a variable-rate IMU stream to a fixed target frequency.

Strategy: linear interpolation on a uniform time grid.
The resampler accumulates incoming samples and emits one output sample
per target period, interpolating between the two nearest input samples.

This ensures the GRU always receives exactly `window` samples at
`target_hz` regardless of whether the source is 50 Hz, 100 Hz, or 200 Hz.

Usage:
    resampler = Resampler(target_hz=10.0)
    for raw_sample in adapter.stream(packets):
        for resampled in resampler.push(raw_sample):
            window_buffer.append(resampled)
"""

from __future__ import annotations

from typing import Iterator

from ..imu.standard_imu import StandardIMUSample


class Resampler:
    def __init__(self, target_hz: float = 10.0) -> None:
        self._period = 1.0 / target_hz
        self._prev: StandardIMUSample | None = None
        self._next_t: float | None = None   # next output timestamp

    def push(self, sample: StandardIMUSample) -> Iterator[StandardIMUSample]:
        """Accept one raw sample; yield zero or more resampled samples."""
        if self._prev is None:
            self._prev = sample
            self._next_t = sample.timestamp
            return

        t0, t1 = self._prev.timestamp, sample.timestamp
        if t1 <= t0:
            # Non-monotonic timestamp — skip
            return

        # Emit all output ticks that fall in [t0, t1)
        while self._next_t is not None and self._next_t <= t1:
            alpha = (self._next_t - t0) / (t1 - t0)
            yield _interpolate(self._prev, sample, self._next_t, alpha)
            self._next_t += self._period

        self._prev = sample

    def reset(self) -> None:
        self._prev = None
        self._next_t = None


def _interpolate(
    a: StandardIMUSample,
    b: StandardIMUSample,
    t: float,
    alpha: float,
) -> StandardIMUSample:
    """Linear interpolation between two samples at fractional position alpha."""
    def lerp(x, y):
        return x + alpha * (y - x)

    import math
    def lerp_nan(x, y):
        if math.isnan(x) or math.isnan(y):
            return float("nan")
        return lerp(x, y)

    dt = b.timestamp - a.timestamp   # actual dt at the interpolated point
    return StandardIMUSample(
        timestamp = t,
        dt        = dt * alpha if alpha > 0 else a.dt,
        ax = lerp(a.ax, b.ax),  ay = lerp(a.ay, b.ay),  az = lerp(a.az, b.az),
        gx = lerp(a.gx, b.gx),  gy = lerp(a.gy, b.gy),  gz = lerp(a.gz, b.gz),
        mx = lerp(a.mx, b.mx),  my = lerp(a.my, b.my),  mz = lerp(a.mz, b.mz),
        roll  = lerp_nan(a.roll,  b.roll),
        pitch = lerp_nan(a.pitch, b.pitch),
        yaw   = lerp_nan(a.yaw,   b.yaw),
        frame  = a.frame,
        source = a.source,
    )
