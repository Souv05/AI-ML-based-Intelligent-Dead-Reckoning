# STEP 17B Report -- AI (Phase-16 winner) + INS + EKF (constant-velocity, speed-as-measurement) + NHC + GNSS Fusion

## 1. Objective
Get the "active NHC" test number 17A's Section 4 asked for, by reconstructing (from 17A's own
description, since the real 15C notebook was not available -- see Section 0) a constant-velocity
/ speed-as-measurement EKF in which body-frame lateral velocity is a genuine free DOF, then
running a 2x2 ablation (winner/12D_v1 speed x NHC on/off) over the same 72 frozen outage cases
17A used.

## 2. Readiness gate (this run)
- 13C authoritative gate: True
- Phase-16 frozen winner (16E) available: True (16A GRU v2, T=60)
- Frozen 72-case outage list available: True
- NHC noise (15B/15C frozen): True (NHC_STD_MPS=1.0, source=outputs\step15\15C\15C_config.json)
- sig_speed_win_mps: 4.4016 (reported (not live in this environment)) | sig_speed_v1_mps: 5.070741779180324 (outputs\step12d\final\test_metrics.json)
- READY_TO_RUN: True

## 3. Results (72 frozen outage cases x 4 arms, test set)
                 method  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  sih_pass_rate_pct  mean_abs_nhc_innovation_mps
AI_EKF_CV(12D_v1,noNHC)    348.238862  884.126775         69.888412      120.146473       771.066302           4.166667                          NaN
   AI_EKF_CV(win,noNHC)    288.639732  778.696559         69.267520      105.466672       558.219487           4.166667                          NaN
  AI_EKF_CV_NHC(12D_v1)    250.872101  411.143739         36.428768       63.195443       349.935300           4.166667                     0.001848
     AI_EKF_CV_NHC(win)    186.327826  387.090438         36.791316       59.591643       291.252235           4.166667                     0.002074

## 4. Interpretation
- **NHC's innovation is now non-zero.** Mean |NHC innovation| for the winner arm = 0.0021 m/s (17A's equivalent number was 0).
- For the Phase-16 winner (16A GRU v2), switching NHC on REDUCED median FDE by 102.31 m (NHC helps once its innovation is non-zero).
- For the frozen 12D GRU v1, switching NHC on REDUCED median FDE by 97.37 m (NHC helps once its innovation is non-zero).
- Switching from Step-14's hard-assignment process model to 17B's constant-velocity / speed-as-measurement model (NHC off, winner speed) changed median FDE by -101.95 m vs 17A's AI_EKF_NHC(win) (worsened) -- this isolates the process-model redesign's own effect, separate from NHC.

## 5. Reference (Step 14 / 17A, unchanged, for context)
Median FDE (m): Classical_DR 284.3 | AI_DR_GRU(12D) 220.9 | AI_EKF(12D,noNHC) 229.9 |
AI_EKF_NHC(12D_v1,17A) 229.9 | AI_EKF_NHC(win,17A) 186.7

## 6. Limitations
- Section 0/5: the constant-velocity / speed-as-measurement process model is 17B's OWN
  reconstruction from 17A's description of "15C" -- the real 15C notebook/config was not
  available. If a real 15C.py/notebook exists with different exact update equations, treat
  this as directionally informative, not a certified match.
- sig_speed_mps (forward-speed measurement noise) is set to each model's own test RMSE, not
  independently tuned -- a documented, reasonable choice, not a frozen/validated one.
- Q_PSD_DIAG / P0_DIAG / SIG_GNSS_M reused verbatim from a process model they were NOT tuned
  for (Step 14's hard-assignment model) -- the velocity/heading covariance terms may now be
  mismatched to the new model's actual dynamics; a real re-tune was out of scope here.
- No map matching, ZUPT, or Android/edge deployment.
- No Phase-17 "final" drift claim -- this is a controlled ablation of one design question
  (does NHC help once active), not a production readiness statement.
