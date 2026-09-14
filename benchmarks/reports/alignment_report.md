# Time-alignment report

**Master clock:** the smartphone IMU timeline, rebuilt from the phone `DATE`
column (the `TIME SINCE START (ms)` column is unreliable on several trips) and
rebased so each sequence starts at t = 0.

**Measured phone rate:** median 10.00 Hz across sequences
(range 10.00-10.00); this is *measured per file*, not
assumed.

**Phone <-> vehicle:** the "Synchronised / Categorised" pairs are already
sample-locked at 10 Hz by the dataset authors. Each pair is truncated to the
shorter length (mismatch is 0-230 rows, mostly the `Vf` driver) and then treated
as row-for-row aligned. This is verified per pair by cross-correlating phone
GNSS speed against vehicle reference speed (`synchronized_pairs.csv`).

**Target alignment:** because the streams are row-aligned, `reference_speed` is
taken directly at each IMU sample - **no interpolation, no forward-fill**. Rows
inside a logging gap (`dt > 0.6` s) are left in the
timeline but no temporal window is allowed to span them.

**Phone GNSS is NOT upsampled** to 10 Hz and passed off as dense truth; it is
only used to derive `native_gnss_valid`.

**Measured phone GNSS refresh (not assumed):** the problem statement says ~1 Hz,
but the actual `GPS LATITUDE/LONGITUDE` columns refresh every **~9 s** on most
trips (only a few, e.g. `Vta02`, are true 1 Hz), with real dropouts of 30-150 s.
`gnss_update_interval_s` is recorded per sequence; `native_gnss_valid` uses a
12 s staleness threshold so a normal 9 s hold is still "valid" and only genuine
multi-fix outages are flagged.
