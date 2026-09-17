"""Universal IMU sample contract.

Every sensor adapter must produce StandardIMUSample objects.
The GRU, EKF, and all downstream components only consume this type.

Units are always:
    acceleration : m/s²
    gyro         : rad/s
    magnetometer : µT  (optional — zero-filled if unavailable)
    orientation  : degrees (optional — computed downstream if absent)

Frame is always the canonical vehicle frame after adapter transform:
    FRD = Forward-Right-Down  (default for ground vehicles)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StandardIMUSample:
    # ── Timing ────────────────────────────────────────────────────────────────
    timestamp: float          # Unix epoch seconds (float)
    dt: float                 # actual interval since previous sample (seconds)

    # ── Inertial (canonical frame, canonical units) ───────────────────────────
    ax: float                 # forward acceleration  m/s²
    ay: float                 # rightward acceleration m/s²
    az: float                 # downward acceleration  m/s²

    gx: float                 # roll rate     rad/s
    gy: float                 # pitch rate    rad/s
    gz: float                 # yaw rate      rad/s

    # ── Optional magnetometer (zero-filled when unavailable) ─────────────────
    mx: float = 0.0           # µT
    my: float = 0.0
    mz: float = 0.0

    # ── Optional orientation (degrees, NaN when not provided by sensor) ───────
    roll:  float = float("nan")
    pitch: float = float("nan")
    yaw:   float = float("nan")

    # ── Provenance (never seen by GRU — adapter metadata only) ───────────────
    frame: str  = "FRD"       # frame BEFORE canonical transform (informational)
    source: str = "unknown"   # e.g. "phone", "csv", "vectornav"

    def has_magnetometer(self) -> bool:
        return self.mx != 0.0 or self.my != 0.0 or self.mz != 0.0

    def has_orientation(self) -> bool:
        import math
        return not (math.isnan(self.roll) or math.isnan(self.pitch) or math.isnan(self.yaw))

    def imu_vector(self) -> list[float]:
        """Return the 6-element inertial vector [ax,ay,az,gx,gy,gz]."""
        return [self.ax, self.ay, self.az, self.gx, self.gy, self.gz]
