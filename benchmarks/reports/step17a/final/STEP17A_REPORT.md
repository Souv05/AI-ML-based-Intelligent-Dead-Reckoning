# STEP 17A Report -- AI (Phase-16 winner) + INS + EKF + NHC + GNSS Fusion

## 1. Objective
Determine whether the Phase-16 winner (frozen via 16E) improves fused navigation drift over
the original 12D-GRU-based Step 14 system, using the identical EKF core, GNSS/course update
logic, v3 robustness constants, and 72 frozen outage cases, with Step 15A's NHC update wired
into the outage span.

## 2. Readiness gate (this run)
- 13C authoritative gate: True
- Phase-16 frozen winner (16E) available: True (16A GRU v2, T=60)
- Frozen 72-case outage list available: True
- NHC noise (15B/15C frozen): True (NHC_STD_MPS=1.0, source=outputs\step15\15C\15C_config.json)
- READY_TO_RUN: True

## 3. Results (72 frozen outage cases, test set)
            method  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  sih_pass_rate_pct
AI_EKF_NHC(12D_v1)    229.931383  408.660368         36.840774       62.887323       351.872832           4.166667
   AI_EKF_NHC(win)    186.686428  384.061546         36.974387       59.193332       292.725850           2.777778

`AI_EKF_NHC(win)` = 16A GRU v2 speed; `AI_EKF_NHC(12D_v1)` = frozen 12D GRU speed. Both use
the Step-14 EKF v3 core + NHC applied every step inside the outage span.

## 4. Interpretation
- **NHC is structurally inert under the frozen Step-14 predict model.** The `AI_EKF_NHC(12D_v1)` arm (12D speed + Step-14 EKF + NHC-in-outage) reproduces Step-14's AI_EKF (no-NHC) median FDE 229.931 m exactly (bit-identical). Step-14's predict() sets vE=v_fwd*sin(psi), vN=v_fwd*cos(psi) every step, so v_lateral(x)=0 analytically right after every predict -> the NHC innovation is ~0 and update_nhc changes only the covariance, never the point estimate. This confirms the Step-15B finding on the test set.
- **The FDE improvement is the Phase-16 winner alone, not NHC.** `AI_EKF_NHC(win)` median FDE 186.7 m vs the 12D arm 229.9 m (18.8% lower) -- entirely attributable to 16A GRU v2's better speed estimates (matches Step 16D). Median drift % is ~unchanged because heading during the outage -- not speed -- is the dominant error, and NHC (as wired here) cannot touch it.
- **Where NHC actually becomes active: Step 15C.** 15C redesigned the process model (constant-velocity between updates; vE/vN/psi pass through predict unchanged; GRU speed enters as a *measurement*, not a hard assignment) so v_lateral is a genuine free DOF and NHC has a non-zero innovation. A 17A-style test-set run on the 15C process model (not done here -- 17A's scope is 'Step-14 EKF verbatim') is the natural next sub-step if an active-NHC test number is needed.

## 5. Frozen Step 14 reference (unchanged, for context)
Median FDE (m): Classical_DR 284.3 | AI_DR_GRU(12D) 220.9 | AI_EKF(12D, no NHC) 229.9
Median drift %: Classical_DR 45.7 | AI_DR_GRU(12D) 42.1 | AI_EKF(12D, no NHC) 36.8
SIH <10% per-run pass rate: Classical_DR 11.1% | AI_DR_GRU(12D) 2.8% | AI_EKF(12D, no NHC) 4.2%

## 6. Limitations
- Q, R, P0 and every v3 robustness constant reused verbatim from Step 14 -- not re-tuned.
- NHC_STD_MPS=1.0 is 15B's frozen value (15B: "for continuity, not because it won").
- The 72-case outage list is loaded from outputs/step13c_full/final/outage_cases.csv,
  never regenerated, preserving comparability with every prior Classical_DR / AI_DR_GRU /
  AI_EKF number.
- NHC as wired here (on top of Step-14 predict) is inert -- see Section 4. This notebook
  does NOT adopt 15C's redesigned process model; that is a separate run.
- No map matching, ZUPT, or Android/edge deployment.
