# STEP 17B Report — GNSS Health / Outage Detection

## 1. Objective
Causal per-sample GNSS health classification (HEALTHY/DEGRADED/OUTAGE) using satellite
count, HDOP, and kinematic-consistency — the monitoring layer upstream of any GNSS-to-DR
switching logic (not built here).

## 2. Module
GNSSHealthMonitor — four cues (sat-count, HDOP, kinematic self-consistency, frozen-fix).
Thresholds: MIN_SATS_HEALTHY=6, MIN_SATS_OUTAGE=3,
HDOP_HEALTHY=2.0, HDOP_OUTAGE=10.0,
KINEMATIC_JUMP_MPS=8.0.

## 3. Synthetic sanity tests
7/7 passed.

## 4. Validation sanity check
Mean F1=0.865, mean outage recall=1.000
(thresholds_sane=True).

## 5. Held-out test results
sequence_id  precision  recall     f1  outage_recall  outage_precision     n  n_true_degraded  n_true_outage  n_pred_healthy  n_pred_degraded  n_pred_outage
      Vta08     0.8036     1.0 0.8911            1.0            0.7826  3700              360            180            3028              442            230
      Vta28     0.6916     1.0 0.8177            1.0            0.7207  4300              225             80            3859              330            111
      Vtb01     0.8384     1.0 0.9121            1.0            0.8955 10000              910            600            8199             1131            670
       Vw02     0.8276     1.0 0.9057            1.0            0.9238 15000             1010            800           12813             1321            866

Mean F1: 0.882 | Outage recall: 1.000
| Outage precision: 0.831

## 6. Interpretation
The detector reliably catches true outages via satellite-count and frozen-fix cues.
Main failure mode: brief mild degradations not crossing any single threshold (known
limitation of independent-cue-max fusion vs a learned combiner).

## 7. Limitations
- Synthetic scaffold data (real n_satellites/hdop not in IO-VNBD dataset).
- No GNSS-to-DR switching or hysteresis logic — classifier only.
- GRU-v2 not touched; module is upstream/independent of both GRU and EKF.

## STOP
Step 17B complete. GNSS-to-DR switching logic is a distinct follow-up step.
