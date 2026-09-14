# STEP 15B - Validation Tuning of the Lateral-NHC Measurement Noise

## 0. KEY FINDING (read first)
All 7 NHC candidates are numerically indistinguishable from the Step 14 no-NHC baseline: median validation FDE is identical to 9 decimal places across every configuration (151.088526 m), and mean |v_lateral| is ~1e-16 m/s (machine-epsilon zero) in every configuration, **including the baseline**. This was verified directly (section 11a of the notebook): Step 14's `predict()`, reused unmodified, sets `vE=v_fwd*sin(psi)`, `vN=v_fwd*cos(psi)` on every step, which makes `v_lateral(x)=vE*cos(psi)-vN*sin(psi)` analytically **exactly zero immediately after every predict**, for any v_fwd/psi (confirmed over 500 random probe states, max residual 1.78e-15 m/s). The NHC innovation is therefore always ~0, and `update_nhc` can only shrink covariance - it has **no effect on the point-estimate trajectory whatsoever** under this process model.

This does not contradict Step 15A: 15A validated the NHC math correctly on synthetic states where vE/vN were specified independently of psi. The issue is specific to how that math *integrates* with Step 14's particular predict() formula, where velocity is always re-derived from (v_fwd, psi) rather than integrated as an independent quantity. Fixing this would require changing the EKF process model - explicitly out of scope for 15B ("do not redesign the EKF"). **This is reported as a negative result, per the project's own instruction that negative results are valid.**

## 1. Candidate values tested
`NHC_STD_MPS` in [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0], plus the Step 14 baseline (no NHC).

## 2. Validation sequences
7 sequences: ['S3a', 'S3b', 'S3c', 'V-Vfa02', 'Vw03', 'Vw16a', 'Vw16b']

## 3. Validation outage cases
120 cases, durations represented: [10, 20, 30, 60, 90, 120] s (protocol: up to 3 seeded starts per sequence/duration, speed>=5.0 km/h, GNSS available, no logging gap, full GRU window).

## 4. Validation-only protocol
Test sequences are never opened by this notebook (structural firewall, section 4 of the notebook); every loaded/evaluated sequence id is asserted disjoint from the 4 held-out test sequences at multiple points.

## 5. Baseline Step 14 metrics (VALIDATION, no NHC)
```
config_label                              baseline_no_nhc
nhc_std_mps                                           NaN
n_validation_sequences                                  7
outage_durations_represented    [10, 20, 30, 60, 90, 120]
n_cases                                             117.0
median_FDE_m                                   151.088526
mean_FDE_m                                     303.019436
median_position_error_m                         73.864141
max_position_error_m                           2304.01211
median_drift_pct                                 35.91607
mean_drift_pct                                  48.988041
max_drift_pct                                  212.503415
median_abs_v_lateral_mps                              0.0
mean_abs_v_lateral_mps                                0.0
max_abs_v_lateral_mps                                 0.0
nan_count                                             0.0
inf_count                                             0.0
invalid_covariance_count                              0.0
innovation_failures                                   0.0
numerical_failures                                    1.0
```

## 6. Metrics per NHC candidate
```
   config_label  nhc_std_mps  n_validation_sequences outage_durations_represented  n_cases  median_FDE_m  mean_FDE_m  median_position_error_m  max_position_error_m  median_drift_pct  mean_drift_pct  max_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  nan_count  inf_count  invalid_covariance_count  innovation_failures  numerical_failures
baseline_no_nhc          NaN                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.299817e-16           1.776357e-15        0.0        0.0                       0.0                  0.0                 1.0
       nhc_0.25         0.25                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.328811e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
        nhc_0.5         0.50                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413676e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
       nhc_0.75         0.75                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413704e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
          nhc_1         1.00                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413704e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
        nhc_1.5         1.50                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413704e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
          nhc_2         2.00                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413704e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
          nhc_3         3.00                       7    [10, 20, 30, 60, 90, 120]    117.0    151.088526  303.019436                73.864141            2304.01211          35.91607       48.988041     212.503415                       0.0            2.413704e-16           1.421085e-14        0.0        0.0                       0.0                  0.0                 1.0
```

## 7. Selected NHC_STD_MPS
**1.0 m/s**

## 8. Selected R_NHC
**1.0** (m/s)^2

## 9. Why it was selected
All 7 candidates are numerically indistinguishable from the Step 14 no-NHC baseline on every navigation metric (median FDE identical to 9 decimal places; mean |v_lateral| ~1e-16 m/s in every configuration, including baseline). This is a structural property of the reused, unmodified Step 14 predict() model, not a tuning failure: predict() recomputes vE=v_fwd*sin(psi), vN=v_fwd*cos(psi) every step, which makes v_lateral(x) analytically 0 immediately after every predict, so the NHC innovation is always ~0 and update_nhc has no point-estimate effect to tune. The engineering selection rule (sections 12/15) therefore cannot discriminate among candidates on this pipeline; NHC_STD_MPS=1.0 m/s (the Step 15A initial engineering value) is frozen for continuity into 15C, not because it outperformed the others - none did. Reported as a negative result, not hidden: realising any benefit from lateral NHC requires the EKF process model to give vE/vN an independent, non-heading-slaved degree of freedom during predict, which is an EKF redesign question outside 15B's scope ("do not redesign the EKF").

## 10. Per-sequence behaviour (selected candidate)
```
config_label  nhc_std_mps sequence_id  outage_cases  median_FDE_m  median_drift_pct  median_abs_v_lateral_mps  numerical_failures numerical_status
       nhc_1          1.0         S3a          18.0    171.640139         41.247525                       0.0                 0.0               OK
       nhc_1          1.0         S3b          15.0    147.462724        100.465113                       0.0                 0.0               OK
       nhc_1          1.0         S3c          18.0    189.824655         50.510443                       0.0                 1.0         FAILURES
       nhc_1          1.0     V-Vfa02          18.0    246.892188         30.909049                       0.0                 0.0               OK
       nhc_1          1.0        Vw03          18.0    140.890372         30.341319                       0.0                 0.0               OK
       nhc_1          1.0       Vw16a          18.0    157.697899         30.387888                       0.0                 0.0               OK
       nhc_1          1.0       Vw16b          12.0     50.827973          8.521046                       0.0                 0.0               OK
```

## 11. Numerical stability
```
   config_label  nhc_std_mps  nan_count  inf_count  invalid_covariance_count  innovation_failures  numerical_failures
baseline_no_nhc          NaN        0.0        0.0                       0.0                  0.0                 1.0
       nhc_0.25         0.25        0.0        0.0                       0.0                  0.0                 1.0
        nhc_0.5         0.50        0.0        0.0                       0.0                  0.0                 1.0
       nhc_0.75         0.75        0.0        0.0                       0.0                  0.0                 1.0
          nhc_1         1.00        0.0        0.0                       0.0                  0.0                 1.0
        nhc_1.5         1.50        0.0        0.0                       0.0                  0.0                 1.0
          nhc_2         2.00        0.0        0.0                       0.0                  0.0                 1.0
          nhc_3         3.00        0.0        0.0                       0.0                  0.0                 1.0
```

## 12. Did NHC improve validation performance?
No measurable change on any metric, for any candidate - see section 0. This is a structural artefact of Step 14's process model, not evidence that lateral-velocity constraints are unhelpful in general.

## 13. Limitations
- 7 validation sequences, up to 3 seeded starts per (sequence,duration) cell - not an exhaustive sweep.
- NHC is applied unconditionally throughout the outage span (no adaptive gating, no turn/slip detection) - by design for 15A/15B; gating is explicitly out of scope here.
- Selection is an engineering rule (reject-unstable -> require lateral suppression -> reject over-aggressive -> rank by drift -> robustness/parsimony tie-breaks), not a global optimisation; a different, equally defensible rule could select a neighbouring candidate.
- This is a VALIDATION-only result. It says nothing yet about the held-out TEST set - that is Step 15D.

## 14. Confirmation: test data NOT used for tuning
Confirmed. `TEST_DIR` parquet/npz files are never opened in this notebook; every sequence id used is asserted disjoint from the 4 held-out test sequences at load time, outage-case-build time, and results time (3 separate assertions).
