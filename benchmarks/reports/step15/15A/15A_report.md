# STEP 15A Report - Lateral Non-Holonomic Constraint

## 1. What was implemented
A lateral body-frame-velocity pseudo-measurement (`v_lateral ~ 0`) for the frozen Step 14 5-state EKF: body-frame transform, measurement function h(x), analytical Jacobian H(x), and `EKF5.update_nhc()`. No new state, no ZUPT, no gating, no tuning.

## 2. Mathematical formulation
```
f_hat = (sin(psi), cos(psi))    l_hat = (cos(psi), -sin(psi))
v_forward = vE*sin(psi) + vN*cos(psi)
v_lateral = vE*cos(psi) - vN*sin(psi)
h(x) = v_lateral(x)     z_NHC = 0     innovation = -v_lateral(x)
```

## 3. Jacobian derivation
```
H = dh/dx = [0, 0, cos(psi), -sin(psi), -v_forward(x)]
```
Finite-difference validation: max_abs_diff=6.773e-09 (tolerance 1e-04), n=500 random states -> PASS.

## 4. Unit-test results
```
{
  "TEST1_pure_forward": {
    "n": 200,
    "max_forward_error_mps": 7.105427357601002e-15,
    "max_lateral_error_mps": 3.552713678800501e-15,
    "PASS": true
  },
  "TEST2_straight_line_real_data": {
    "sequence": "Vw02",
    "n_straight_samples": 27334,
    "mean_abs_lateral_mps": 0.09566271795789631,
    "median_abs_lateral_mps": 0.09429020163598206,
    "yaw_rate_threshold_deg_s": 1.0,
    "PASS": true
  },
  "TEST3_artificial_lateral": {
    "input": {
      "vE": 5.0,
      "vN": 10.0,
      "psi_rad": 0.0
    },
    "v_forward": 10.0,
    "v_lateral": 5.0,
    "expected_v_forward": 10.0,
    "expected_v_lateral": 5.0,
    "PASS": true
  },
  "TEST5_ekf_nhc_update": {
    "sig_nhc_mps": 1.0,
    "v_lateral_before": 5.0,
    "v_lateral_after": 0.01019600719978575,
    "innovation": -5.0,
    "innovation_covariance": 44.41556778080377,
    "kalman_gain": [
      0.0,
      0.0,
      0.3602340530455886,
      0.0,
      -0.061725131863906206
    ],
    "moved_toward_zero": true,
    "state_after": [
      0.0,
      0.0,
      3.1988297347720573,
      10.0,
      0.3086256593195311
    ],
    "all_finite": true,
    "PASS": true
  },
  "TEST6_covariance_validity": {
    "n_applications": 50,
    "max_symmetry_error": 0.0,
    "min_eigenvalue_overall": 0.0017452875959053887,
    "all_finite_throughout": true,
    "final_state": [
      0.25,
      40.09999999999999,
      0.0,
      8.0,
      0.0
    ],
    "final_v_lateral": 0.0,
    "PASS": true
  },
  "numerical_stability_stress": {
    "n_stress_cases": 300,
    "max_position_step_from_single_nhc_update_m": 0.0,
    "nan_inf": 0,
    "singular_S": 0,
    "bad_gain": 0,
    "exploding_velocity": 0,
    "exploding_heading": 0,
    "position_discontinuity": 0,
    "PASS": true
  }
}
```

## 5. Numerical-stability results
```
{
  "n_stress_cases": 300,
  "max_position_step_from_single_nhc_update_m": 0.0,
  "nan_inf": 0,
  "singular_S": 0,
  "bad_gain": 0,
  "exploding_velocity": 0,
  "exploding_heading": 0,
  "position_discontinuity": 0,
  "PASS": true
}
```

## 6. Files created
- notebooks/15A_lateral_nhc.ipynb
- outputs/step15/15A/15A_report.md
- outputs/step15/15A/15A_config.json
- outputs/step15/15A/15A_jacobian_test.json
- outputs/step15/15A/15A_sanity_tests.json

## 7. Problems discovered
None - all gates passed on the first implementation.

## Completion checklist
```json
{
  "Dataset verified": true,
  "Step 14 baseline verified": true,
  "Frozen GRU verified": true,
  "NHC implemented": true,
  "Lateral velocity measurement implemented": true,
  "Analytical Jacobian implemented": true,
  "Finite-difference Jacobian test: PASS": true,
  "Body-frame sanity tests: PASS": true,
  "EKF NHC update test: PASS": true,
  "Covariance validity test: PASS": true,
  "Numerical stability: PASS": true,
  "GRU retrained: NO": true,
  "Test-set tuning: NO": true,
  "GNSS used as NHC measurement: NO": true,
  "Reference trajectory used by NHC: NO": true
}
```

STEP 15A: COMPLETE

Per the Step 15 roadmap, this notebook STOPS here. 15B (validation tuning of R_NHC), 15C (integrated AI+EKF+NHC run), 15D (full 72-case test), 15E (heading/drift analysis) and 15F (optional ZUPT) are separate, later steps - not implemented in this notebook.