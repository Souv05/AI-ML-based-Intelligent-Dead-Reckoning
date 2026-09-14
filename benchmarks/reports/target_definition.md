# Target definition (phase: data prep - not trained)

**Selected first target:** `forward_speed` - the vehicle's forward speed in m/s
at the window-end timestamp, taken from the reference channel
`Velocity (km/hr) / 3.6`.

Rationale: directly matches the SIH requirement (AI speed / motion estimation for
dead reckoning), is a single scalar that is easy to validate, and needs no
assumption about heading.

**Prepared but not selected** (generator supports switching via
`PrepConfig.target`):

| key | value | shape |
|-----|-------|-------|
| `forward_speed` | reference speed at t (+horizon) | scalar |
| `velocity_vector` | d(reference_x, reference_y)/dt | (vx, vy) |
| `displacement` | (reference_x, reference_y)[t+h] - [t] | (dx, dy) |

`target_horizon_steps = 0` -> nowcast (speed at the last input sample).
Set > 0 for short-horizon prediction; windowing then drops windows whose target
sample lies beyond a gap or the sequence end.

The target is derived **only** from the reference trajectory and is never placed
in the input tensor (checked in `leakage_report.md`).
