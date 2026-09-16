"""IMU pre-processing filter for vehicle dead-reckoning.

Two stages:
1. Low-pass Butterworth filter (8 Hz cutoff at 50 Hz input) on acc/gyro channels
   — removes engine vibration harmonics (typically 20-200 Hz) and road texture noise.
2. Pothole / shock detector — flags samples where vertical acceleration spike
   exceeds a threshold; resets the GRU window to avoid corrupting the speed estimate
   with a transient that looks nothing like training data.

Design choices:
- 8 Hz cutoff keeps vehicle dynamics (braking, turning, acceleration) intact
  while rejecting chassis resonance and road roughness.
- Pothole threshold: |az - gravity_z| > 15 m/s² for ≥1 sample. Real potholes
  produce 20-40 m/s² spikes; 15 m/s² rejects them while passing hard braking (~8 m/s²).
- We do NOT filter magnetometer or orientation channels — they are slowly varying
  and don't benefit from aggressive LP filtering.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from scipy.signal import butter, sosfilt_zi, sosfilt

_FS   = 50.0   # expected IMU sample rate (Hz)
_FC   = 8.0    # low-pass cutoff (Hz)
_ORDER = 4     # Butterworth order

# Channels filtered: acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z (indices 0-5)
_FILTER_CHANNELS = list(range(6))

# Pothole detection: vertical accel (az, index 2) spike above this relative to 1g
_GRAVITY_MS2    = 9.81
_POTHOLE_THRESH = 15.0   # m/s² above/below gravity


class ImuFilter:
    def __init__(self) -> None:
        sos = butter(_ORDER, _FC / (_FS / 2), btype='low', output='sos')
        self._sos = sos
        # One filter state per channel (zi shape: (n_sections, 2))
        n_sections = sos.shape[0]
        self._zi = [np.zeros((n_sections, 2)) for _ in _FILTER_CHANNELS]
        self._sample_count = 0
        self._pothole_flag = False

    def push(self, sample: list[float]) -> tuple[list[float], bool]:
        """Filter one IMU sample.

        Parameters
        ----------
        sample : list[float]
            12-element vector in GRU feature order:
            [acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z,
             mag_x, mag_y, mag_z, roll, pitch, yaw]

        Returns
        -------
        filtered : list[float]
            Filtered 12-element vector (mag/orientation channels unchanged).
        reset_window : bool
            True if a pothole was detected — caller should reset the GRU window.
        """
        out = list(sample)
        reset_window = False

        # Pothole detection before filtering (use raw az)
        az_raw = sample[2]
        if abs(az_raw - _GRAVITY_MS2) > _POTHOLE_THRESH or abs(az_raw + _GRAVITY_MS2) > _POTHOLE_THRESH:
            reset_window = True

        # Low-pass filter acc + gyro channels in-place
        for i, ch in enumerate(_FILTER_CHANNELS):
            val = np.array([sample[ch]], dtype=np.float64)
            filtered_val, self._zi[i] = sosfilt(self._sos, val, zi=self._zi[i])
            out[ch] = float(filtered_val[0])

        self._sample_count += 1
        return out, reset_window

    def reset(self) -> None:
        """Reset filter state (e.g. after a long gap or sensor reconnect)."""
        n_sections = self._sos.shape[0]
        self._zi = [np.zeros((n_sections, 2)) for _ in _FILTER_CHANNELS]
        self._sample_count = 0
