"""Coordinate frame transformation to canonical vehicle frame.

Canonical frame: FRD (Forward-Right-Down)
    ax → forward acceleration
    ay → rightward acceleration
    az → downward acceleration (gravity ≈ +9.81 when stationary)

Each sensor has its own native frame.  The transform is a signed axis
permutation (no scaling — units are already normalised by the adapter).

Supported source frames:
    "FRD"       → identity (no change)
    "FLU"       → Android default (phone lying flat, screen up)
    "NED"       → North-East-Down (many aviation/autopilot IMUs)
    "ENU"       → East-North-Up   (ROS default)
    "phone_native" → alias for FLU

To add a new frame, append an entry to _TRANSFORMS:
    "FRAME_NAME": (ax_src, ay_src, az_src, gx_src, gy_src, gz_src)
Each element is a (sign, index) pair into the source [ax,ay,az,gx,gy,gz] vector.

Usage:
    tf = FrameTransform(source_frame="FLU")
    frd_sample = tf.apply(flu_sample)
"""

from __future__ import annotations

from ..imu.standard_imu import StandardIMUSample

CANONICAL_FRAME = "FRD"

# Each entry maps source [ax,ay,az, gx,gy,gz] → canonical FRD [ax,ay,az, gx,gy,gz].
# Tuple: (a0_sign, a0_src, a1_sign, a1_src, a2_sign, a2_src,
#          g0_sign, g0_src, g1_sign, g1_src, g2_sign, g2_src)
# All indices are into the 3-element accel or gyro sub-vector (0,1,2).
_TRANSFORMS: dict[str, tuple] = {
    #            ax         ay         az         gx         gy         gz
    "FRD":     (+1,0,     +1,1,     +1,2,      +1,0,     +1,1,     +1,2),
    "FLU":     (+1,0,     -1,1,     -1,2,      +1,0,     -1,1,     -1,2),
    "NED":     (+1,0,     +1,1,     +1,2,      +1,0,     +1,1,     +1,2),  # fwd-facing = FRD
    "ENU":     (+1,1,     +1,0,     -1,2,      +1,1,     +1,0,     -1,2),
    "RFU":     (+1,1,     +1,0,     -1,2,      +1,1,     +1,0,     -1,2),
}
_TRANSFORMS["phone_native"] = _TRANSFORMS["FLU"]


class FrameTransform:
    def __init__(self, source_frame: str = "FRD") -> None:
        key = source_frame if source_frame in _TRANSFORMS else "FRD"
        t = _TRANSFORMS[key]
        self._a = [(t[i], t[i+1]) for i in range(0, 6, 2)]   # 3 (sign,idx) pairs for accel
        self._g = [(t[i], t[i+1]) for i in range(6, 12, 2)]  # 3 (sign,idx) pairs for gyro
        self._is_identity = (key == "FRD")

    def apply(self, s: StandardIMUSample) -> StandardIMUSample:
        if self._is_identity:
            return s
        sa = [s.ax, s.ay, s.az]
        sg = [s.gx, s.gy, s.gz]
        a = [sgn * sa[idx] for sgn, idx in self._a]
        g = [sgn * sg[idx] for sgn, idx in self._g]
        return StandardIMUSample(
            timestamp=s.timestamp, dt=s.dt,
            ax=a[0], ay=a[1], az=a[2],
            gx=g[0], gy=g[1], gz=g[2],
            mx=s.mx, my=s.my, mz=s.mz,
            roll=s.roll, pitch=s.pitch, yaw=s.yaw,
            frame=CANONICAL_FRAME,
            source=s.source,
        )
