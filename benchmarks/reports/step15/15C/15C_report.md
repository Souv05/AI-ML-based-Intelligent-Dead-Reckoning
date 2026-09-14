# STEP 15C - AI + EKF + NHC Integrated Navigation

## 1. Step 14 process-model problem
`predict()` hard-assigned `vE=v_fwd*sin(psi), vN=v_fwd*cos(psi)` every step, making `v_lateral(x)` exactly 0 by construction (confirmed in 15B: all NHC candidates gave bit-identical results to the no-NHC baseline). See `15C_process_model_audit.md` for the verbatim source and full audit.

## 2. New 15C process model
Constant-velocity-between-updates: vE,vN,psi pass through predict() unchanged; only position advances kinematically (E+=vE*dt, N+=vN*dt). Accelerometer-driven propagation considered and rejected (documented in the audit) - phone accel is weakly coupled to vehicle dynamics per the project EDA and Step 13C. Q reused unchanged from Step 14 (not retuned).

## 3. AI-velocity measurement formulation
z_AI=v_GRU, h_AI(x)=vE*sin(psi)+vN*cos(psi), H_AI=[0,0,sin(psi),cos(psi),v_lateral(x)], sig_AI=5.070742 m/s (reused = frozen 12D GRU test RMSE).

## 4. NHC formulation
Unchanged from 15A/15B: z_NHC=0, h_NHC(x)=vE*cos(psi)-vN*sin(psi), H_NHC=[0,0,cos(psi),-sin(psi),-v_forward(x)], NHC_STD_MPS=1.0 (frozen from 15B).

## 5. Jacobian validation
```
{
  "H_nhc": {
    "name": "H_nhc",
    "n_samples": 500,
    "fd_eps": 1e-06,
    "tolerance": 0.0001,
    "max_abs_diff": 6.773191785214294e-09,
    "mean_abs_diff": 1.7521295985895025e-09,
    "PASS": true
  },
  "H_ai": {
    "name": "H_ai",
    "n_samples": 500,
    "fd_eps": 1e-06,
    "tolerance": 0.0001,
    "max_abs_diff": 6.591534429389867e-09,
    "mean_abs_diff": 1.7523841234177995e-09,
    "PASS": true
  }
}
```

## 6. Synthetic sanity tests
```
{
  "TESTA_nhc_nonzero_innovation": {
    "v_lateral_before": 5.0,
    "v_lateral_after": 0.010306803568967293,
    "nhc_innovation": -5.0,
    "nhc_innovation_covariance": 44.564306567969645,
    "nhc_kalman_gain": [
      0.035903172812970265,
      0.0,
      0.36127567643051334,
      0.0,
      -0.06162848405613803
    ],
    "state_after": [
      0.3204841359351487,
      1.0,
      3.193621617847433,
      10.0,
      0.3081424202806904
    ],
    "innovation_nonzero": true,
    "moved_toward_zero": true,
    "all_finite": true,
    "PASS": true
  },
  "TESTB_ai_velocity_update": {
    "v_gru": 15.0,
    "v_forward_before": 8.0,
    "v_forward_after": 10.695371089690237,
    "ai_innovation": 7.0,
    "ai_innovation_covariance": 41.812424430564,
    "ai_kalman_gain": [
      0.0,
      0.03826613791929352,
      0.0,
      0.3850530128128911,
      0.0
    ],
    "innovation_nonzero": true,
    "moved_toward_v_gru": true,
    "state_change_realistic": true,
    "all_finite": true,
    "PASS": true
  },
  "TESTC_ai_nhc_interaction": {
    "v_forward": {
      "before": 5.488695331730859,
      "after_AI": 8.343142575729555,
      "after_AI_and_NHC": 8.100373659231181
    },
    "v_lateral": {
      "before": 4.4428107697949715,
      "after_AI": 3.089648621329446,
      "after_AI_and_NHC": 0.15048915360033988
    },
    "heading_before_deg": 20.0,
    "heading_after_deg": 40.239056448408874,
    "ai_moved_forward_toward_gru": true,
    "nhc_moved_lateral_toward_zero": true,
    "heading_change_reasonable_deg": true,
    "covariance_valid": true,
    "all_finite": true,
    "PASS": true
  },
  "TESTD_covariance_validity": {
    "n_applications": 50,
    "max_symmetry_error": 0.0,
    "min_eigenvalue_overall": 0.0016288981352748878,
    "all_finite_throughout": true,
    "final_state": [
      19.474075875470312,
      60.87337204102792,
      3.891914773590965,
      12.160566926100632,
      0.3097390631087569
    ],
    "final_v_lateral": 4.681400272676939e-05,
    "PASS": true
  }
}
```

## 7. Evidence NHC now has nonzero innovation
Test A: NHC innovation = -5.0000 m/s (nonzero); |v_lateral| 5.000 -> 0.010 m/s. Real-data mean NHC innovation on validation: 0.0020 m/s (nonzero, confirming the same effect holds outside synthetic tests).

## 8. Evidence NHC changes the EKF state
mean|v_lateral| during outage: 15C-noNHC=8.1657 m/s vs 15C-withNHC=0.0013 m/s (+100.0% change).

## 9. Controlled validation results
```
            arm  n_cases  median_FDE_m  mean_FDE_m  median_position_error_m  median_drift_pct  mean_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_ai_innovation_mps  std_ai_innovation_mps  mean_nhc_innovation_mps  numerical_failures
step14_baseline    117.0    151.088526  303.019436                73.864141         35.916070       48.988041              0.000000e+00            2.299817e-16           1.776357e-15                     NaN                    NaN                      NaN                 1.0
     15c_no_nhc    117.0    323.529607 1066.175653               128.192811         67.526863      136.847721              5.998846e-01            8.165711e+00           9.580949e+01               -0.140026               2.451690                      NaN               393.0
   15c_with_nhc    117.0    151.888383  310.552498                78.356635         37.307282       50.699136              1.226619e-10            1.339233e-03           1.633474e+00               -0.202715               2.658006                 0.001972                 1.0
```

## 10. Step 14 vs Step 15C comparison
```
                comparison  delta_FDE_m  delta_FDE_pct  delta_drift_pct_pts  delta_lateral_velocity_pct  numerical_failures_with_nhc
    Step14_vs_15C(withNHC)     0.799857      -0.529396             1.391212                         NaN                          1.0
15C(noNHC)_vs_15C(withNHC)  -171.641224      53.052710           -30.219581                   99.983599                          1.0
```

## 11. Numerical stability
Numerical failures (NaN/Inf/update-failure/position-discontinuity), summed over 117 successfully executed cases: step14_baseline=1, 15c_no_nhc=393, 15c_with_nhc=1. These are failure events, not failed cases.

## 12. Limitations
- Constant-velocity process model is a documented compromise, not a validated accelerometer-driven propagation - it relies on measurements (AI, NHC, GNSS) to correct velocity, not on physics-based prediction.
- sig_AI reuses the GRU's aggregate test RMSE as a per-step measurement noise, which is a simplification (true per-sample GRU error varies).
- 120 validation cases were generated; 117 were successfully evaluated. The 3 exclusions are documented in the case-accounting audit.
- This is a VALIDATION-only result; the held-out TEST set has not been touched.

## 13. Confirmation: test set untouched
Confirmed - TEST_DIR parquet/npz files are never opened in this notebook; every sequence id used is asserted disjoint from the 4 held-out test sequences at load time, outage-case-build time, and results time.

## Case Accounting Audit
Case unit: (sequence_id, duration_s, outage_start); selection_rank is deterministic seeded selection order. Requested/generated: 126/120; excluded: 3; executed/successful/reported: 117/117/117; duplicates: 0.

Excluded case IDs: S3b__d90__s951, S3b__d90__s1004, S3b__d120__s629. Each was generated but rejected before execution because its full pre/post-run window exceeded the timestamp-gap limit; no metric row was created.

Numerical failure events: {"step14_baseline": 1, "15c_no_nhc": 393, "15c_with_nhc": 1}. Unique cases with one or more events: {"step14_baseline": 1, "15c_no_nhc": 18, "15c_with_nhc": 1}. These are event counts, not case counts.

Test-set status: untouched (test_set_touched = false).

PASS: Case accounting is internally consistent and reproducible.

## 14. Recommendation for Step 15D
NHC is now a real, measurably active constraint (sections 6-8), and the ablation shows a directionally mixed/negative effect on validation navigation metrics. Before committing to 15D, consider whether the remaining error is dominated by heading uncertainty (untouched by NHC, which only constrains the ratio of vE/vN) - if so, 15D would likely reproduce this validation finding on TEST; still a valid, reportable result either way.
