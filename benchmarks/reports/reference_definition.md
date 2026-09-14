# Reference trajectory definition

**Source:** vehicle (`V-*`) GNSS/INS channels - `Latitude`, `Longitude`,
`Velocity (km/hr)`, `Heading (degrees)`.

**Why this and not the phone GNSS:** the phone GPS updates at ~1 Hz, is held
between updates, and is the noisier consumer-grade receiver. The vehicle file
carries a survey-grade GNSS/INS solution at the full 10 Hz. Using the phone GNSS
as *both* a (masked) input and the ground truth would be circular, so the phone
GNSS is kept only for bookkeeping / `native_gnss_valid`, never as the target.

**Sampling rate:** 10 Hz, row-aligned with the phone stream in the synchronised
pairs (confirmed by smoothed phone-speed vs reference-speed correlation at
lag 0 = 0.918 for the selected pair `M`).

**Coordinates:** `reference_x`, `reference_y` are local ENU metres from the first
valid vehicle fix (equirectangular projection, R = 6378137 m). See
`src/data/coordinates.py`.

**Limitations:** still a GNSS-based solution (not cm-truth); brief outages /
multipath possible; a handful of trips show internal position-vs-speed
inconsistency and are flagged in `data_quality_report.md`.
