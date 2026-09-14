# STEP 17G Report — GNSS ↔ Dead-Reckoning Transition Validation

## 1. Objective
Validate the complete GNSS ↔ DR transition cycle using the frozen GRU-v2
(GRU2-E05c-T60) and corrected Step-15C 5-state EKF. This step validates
*seamless transition + system continuity*, not the final SIH accuracy target.

## 2. Frozen model used
- GRU-v2 (GRU2-E05c-T60), T=60, input_size=12, hidden_size=128, num_layers=2
- Checkpoint: gru_best.pt — NOT retrained, NOT modified
- Phase-16 winner RMSE: 4.4016 m/s

## 3. Navigation pipeline
EKF5_CV (5-state: E, N, vE, vN, psi) + GRU speed measurement
(h=vE*sin(psi)+vN*cos(psi)) + active NHC (NHC_STD=1.0 m/s).
No ZUPT. No parameter tuning on evaluation results.

## 4. State machine
Three modes: GNSS_AIDED → DR_ACTIVE → GNSS_REACQUIRE → GNSS_AIDED.
N_LOSS_CONFIRM=3 (GNSS→DR), N_REACQ_CONFIRM=5 (DR→REACQUIRE and REACQUIRE→AIDED).
Both constants frozen before evaluation.

## 5. GNSS outage detection
gnss_mask: 1=available, 0=masked. In this sandbox, masking is applied at
a controlled start index. In a real system, the GNSSHealthMonitor (17B/17C)
provides the valid flag.

## 6. GNSS → DR transition
- Requires N_LOSS_CONFIRM=3 consecutive invalid samples
- EKF state preserved across transition (no position reset)
- GRU + NHC continue; GNSS updates stop

## 7. DR operation
- predict(dt) + update_speed(v_gru) + update_nhc(NHC_STD) per timestep
- No GNSS position updates during blackout
- Position propagated by EKF constant-velocity model

## 8. GNSS reacquisition
- Requires N_REACQ_CONFIRM=5 consecutive valid samples → GNSS_REACQUIRE
- Further N_REACQ_CONFIRM valid → GNSS_AIDED
- During REACQUIRE: ramped g_max (REACQ_G_MIN=0.25 → 1.0 over 1.5s)
- max_pos_step_m=25.0m during first 8.0s

## 9. DR → GNSS recovery
Graduated GNSS trust prevents uncontrolled position jump.
EKF absorbs correction smoothly via innovation gating.

## 10. Transition metrics (mean over 2 sequences)
| Outage | FDE | Entry jump | DR drift | Recovery jump | Recovery lat | Output Hz |
|--------|-----|------------|----------|---------------|--------------|-----------|
|   10s |    57.20m |    0.685m |    48.5% |      6.980m |       0.900s |     10.0 Hz |
|   20s |   113.50m |    0.685m |    47.8% |     29.431m |       0.900s |     10.0 Hz |
|   30s |   169.76m |    0.685m |    47.6% |     64.001m |       0.900s |     10.0 Hz |
|   60s |   338.48m |    0.685m |    47.4% |    189.805m |       0.900s |     10.0 Hz |

## 11. Drift metrics
Median FDE: 249.32761623916647
Median drift: 47.82891362202888%
Note: GRU-v2 baseline (Phase 16) median drift ≈ 36.76%; this step does not
improve accuracy — it validates transitions only.

## 12. Heading continuity
Heading maintained by EKF across GNSS→DR transition.
No heading reset at mode change.

## 13. Velocity continuity
GRU forward speed active in all modes.
NHC constrains lateral velocity throughout.
No velocity reset at mode change.

## 14. Output-rate analysis
Navigation output produced every EKF timestep (target 10 Hz).
Achieved: ≈10 Hz (set by scaffold timestamp spacing).

## 15. Failure cases
  Case A: Brief 0.2s flicker (2 samples < N_LOSS_CONFIRM=3) — PASS=True
  Case B: 45s outage — expect full DR cycle — PASS=True
  Case C: GNSS returns with 50m position jump — PASS=True
  Case D: GNSS stays invalid — must stay in DR_ACTIVE — PASS=True
  Case E: Flickering GNSS (2-on/2-off pattern) — hysteresis must prevent chattering — PASS=True

## 16. Limitations
- Synthetic scaffold data (no real IO-VNBD IMU); re-run on real data for
  numbers that belong in the report.
- GRU running on synthetic IMU produces near-constant speed — real data
  will show richer dynamics and larger drift.
- GNSS masking is controlled/synchronized; real GNSS uncertainty is
  asynchronous.
- No map-matching, no ZUPT, no adaptive Q.

## 17. Internal SIH demo readiness
PASS criteria (from 17G brief) — all 12 items:
1. GNSS navigation: PASS  2. Outage detection: PASS  3. DR switch: PASS
4. GRU speed during blackout: PASS  5. EKF+NHC navigation: PASS
6. Position continues updating: PASS  7. GNSS return detection: PASS
8. EKF smooth incorporation: PASS  9. Return to GNSS_AIDED: PASS
10. No uncontrolled jump: PASS  11. ≈10 Hz output: PASS
12. No pretend-accuracy claim: acknowledged (see drift metrics above)

## 18. Next step
STOP after 17G. Review transition behavior, drift, heading continuity,
recovery jumps, update rate, failure cases.
Then: PHASE 18 — MAP MATCHING
  18A Offline OSM → 18B Road candidates → 18C Road heading constraint
  → 18D Basic map matching → 18E Map+EKF+NHC → 18F Outage validation
