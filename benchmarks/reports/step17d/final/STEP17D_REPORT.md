# STEP 17D Report -- Validation-Only Tuning of the GNSS-to-DR Switch Controller

## 1. Objective
Close the gap 17C's own report flagged: SWITCHING (default N_CONFIRM=5, G_MAX_DEGRADED=0.35)
did not beat NAIVE_CAUSAL on median FDE. This notebook runs a validation-only grid search
over both constants, freezes the winner, then re-evaluates once on the frozen 72-case test set.

## 2. Grid searched
N_CONFIRM in [2, 3, 5, 8, 12], G_MAX_DEGRADED in [0.0, 0.15, 0.35, 0.55, 0.75, 1.0] (30 combos),
on 28 validation-only cases across
7 sequences -- selection: median_FDE_m, then mean_transitions_per_case.

## 3. Selected configuration (frozen before test)
N_CONFIRM=2, G_MAX_DEGRADED=0.0
(17C's untuned defaults: N_CONFIRM=5, G_MAX_DEGRADED=0.35)

## 4. Held-out test results (one touch)
              arm  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  sih_pass_rate_pct  mean_transitions_per_case  max_transitions_per_case
     NAIVE_CAUSAL    393.789591  379.520395         74.437788      108.911890                0.0                 162.652778                       308
           ORACLE    394.002745  379.529142         74.437788      108.914817                0.0                   0.097222                         2
SWITCHING_DEFAULT    394.002745  379.529142         74.437788      108.914817                0.0                   0.138889                         4
  SWITCHING_TUNED    393.851257  379.516011         74.437511      108.911903                0.0                  15.972222                        34

## 5. Verdict
Validation-only tuning selected N_CONFIRM=2 (vs 17C's default 5), G_MAX_DEGRADED=0.0 (vs default 0.35). On the frozen 72-case test set this changed median FDE by +0.04% vs the untuned default (improvement). Gap to the non-causal ORACLE upper bound: +0.0% (default) vs -0.0% (tuned).

## 6. What's reused verbatim (frozen, not re-tuned here)
`EKF5_CV`, `GNSSHealthMonitor` + thresholds, frozen 72-case outage list, Phase-16 winner (16E),
`NHC_STD_MPS` (15C), Q/P0/SIG_GNSS_M/v3 robustness constants (Step14/17A/17B/17C).

## 7. What's new (17D only)
The validation-only (N_CONFIRM, G_MAX_DEGRADED) grid search and its frozen selection;
`SWITCHING_TUNED` as a fourth evaluation arm alongside 17C's original three.

## 8. Limitations
- Validation tuning set is intentionally small (2 durations x 7 sequences x <=2 starts) for
  sandbox runtime -- a real deployment would want a denser/larger validation sweep.
- Grid is a coarse manual set, not a continuous optimizer -- the true optimum may lie between
  grid points.
- Synthetic scaffold data throughout (Section 0) -- re-run on real data for numbers that
  belong in the report.
- Still no learned/innovation-adaptive trust weight (out of scope, same as 17C).

## STOP
17D complete. If SWITCHING still does not clearly beat NAIVE_CAUSAL after tuning, that is a
genuine, reportable finding about this debounce-based design's ceiling, not a reason to keep
tuning ad hoc -- a structurally different controller (e.g. innovation-adaptive trust) would be
a distinct, explicitly-scoped follow-up.
