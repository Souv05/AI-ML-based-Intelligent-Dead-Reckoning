# Model input definition (phase: data prep - not trained)

Inputs available to the model **during a simulated GNSS outage** - phone inertial
/ orientation only:

| # | feature | source | unit |
|---|---------|--------|------|
| 1-3 | `acc_x/y/z` | phone accelerometer | m/s^2 |
| 4-6 | `gyro_x/y/z` | phone gyroscope | rad/s |
| 7-9 | `mag_x/y/z` | phone magnetometer | uT |
| 10-12 | `roll`,`pitch`,`yaw` | phone ORIENTATION | deg |

Channel order above is the order in the generated window tensors
(`*_windows.npz`, key `X`, shape `(n, window_len, 12)`).

**Explicitly excluded from inputs** (would leak the answer during an outage):
latitude, longitude, phone GNSS speed, phone GNSS heading, altitude, and every
`reference_*` field. Also excluded: all vehicle-only channels (steering, wheel
speed, OBD `Indicated Vehicle Speed`, engine rpm, ...) - per the PS, vehicle-side
data is reference/validation only, never a smartphone-model input.

`gravity_x/y/z` is retained in the interim timeline for optional
alignment/feature work but is **not** in the default input list.
