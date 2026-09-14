# Final AI Model Freeze — GRU v2

## Status

FROZEN

---

## Selected Model

GRU v2 (GRURegressor — same architecture as GRU v1, T=60)

## Experiment

GRU2-E05c-T60

## Checkpoint

`gru_v2_best.pt`
SHA-256: `138557eb0c993cf1c906fe7d7dca9b185db32ba4f8d61fec9dbfadf2680e3207`

---

## Reason for Selection

GRU-v2 is selected because it has:

- Strongest validation performance among current candidates
  (val RMSE 6.6959 m/s vs TCN-GRU 7.5182, Transformer 7.4851)
- Strongest available standalone test performance
  (test RMSE 4.4016 m/s vs TCN-GRU 5.7270, Transformer 5.4223)
- Authoritative downstream 15C + NHC evaluation on 72 held-out cases
- Established dead-reckoning baseline (median FDE 186.26 m, Wilcoxon p=5.1e-5)
- Already integrated with corrected Step-15C EKF and active NHC

---

## Alternatives Evaluated

**TCN-GRU (TCNGRU-E03c-deeper-T40)**
- Test RMSE: 5.7270 m/s
- Evaluated: AI metrics only
- Status: NOT selected

**Transformer (Transformer-E03a-narrow-T20)**
- Test RMSE: 5.4223 m/s
- Evaluated: AI metrics only
- Status: NOT selected

IMPORTANT: TCN-GRU and Transformer are not claimed to be worse in dead reckoning.
Their equivalent downstream 15C+NHC evaluations were not available.
They remain as evaluated alternatives for future edge-deployment consideration.

---

## Performance Summary

### AI-level (held-out test set, 4 sequences)

| Metric | Value |
|--------|-------|
| Val RMSE | 6.6959 m/s |
| Test RMSE | 4.4016 m/s |
| Test MAE | 3.4320 m/s |
| Test R² | 0.6755 |
| Test MedianAE | 2.8676 m/s |

### Downstream navigation (72 outage cases, 15C EKF + active NHC)

| Metric | Value |
|--------|-------|
| Median FDE | 186.26 m |
| Mean FDE | 386.93 m |
| Median drift | 36.76% |
| SIH <10% pass | 3 / 72 (4.2%) |
| Paired wins vs GRU v1 | 50 / 72 |
| Wilcoxon p | 5.1e-05 |

---

## Navigation Baseline

GRU-v2 is the frozen AI velocity estimator for Phase 17.

Pipeline:

```
IMU (10 Hz, 12 channels)
  ↓
Feature preprocessing (per-channel z-score, scaler.json)
  ↓
GRU-v2 (T=60 window, 12→128→128→1)
  ↓
Forward velocity (m/s)
  ↓
15C EKF (5-state: E, N, vE, vN, psi)
  ↓  + active NHC (NHC_STD = 1.0 m/s)
Dead reckoning position
```

---

## Known Limitations

### Parameter count

GRU-v2 has **153,729 parameters** (~604 KB).

This exceeds the current provisional 100k-parameter edge budget (Phase 16).

This is acceptable for the **internal SIH prototype**.

Do NOT claim final smartphone deployment compliance.

If model compression or distillation is required, create a new experiment
rather than modifying this frozen checkpoint.

### Navigation accuracy

Current authoritative result:

- SIH <10% drift pass: **3 / 72 (4.2%)**
- Median drift: **36.76%**
- Mean heading error: **~31.9°**

The navigation bottleneck is **heading accuracy**, not speed accuracy.

**Next development priority: navigation/orientation improvement (Phase 17+).**

---

## Frozen Package Contents

| File | Description |
|------|-------------|
| `gru_v2_best.pt` | Frozen GRU v2 checkpoint |
| `scaler.json` | Per-channel z-score scaler (fit on training only) |
| `model_config.json` | Architecture and training configuration |
| `feature_config.json` | Exact 12-feature order |
| `inference.py` | Self-contained inference module |
| `freeze_hash.txt` | SHA-256 integrity hash |
| `model_metadata.json` | Full provenance and results record |
| `FREEZE_REPORT.md` | This document |
| `authoritative_status_16e.json` | Machine-readable status |

---

## Integrity

- Checkpoint MD5 verified against Step-16A frozen record: 4761355bb0764145be37b13fd619533b
- Checkpoint SHA-256: 138557eb0c993cf1c906fe7d7dca9b185db32ba4f8d61fec9dbfadf2680e3207
- Scaler reused verbatim from Step 12D (train-only fit)
- GRU-v2 was NOT retrained in this step
- Test set was NOT re-evaluated in this step
- 72-case navigation evaluation was NOT re-run

---

## Freeze Date

2026-09-10 21:40:02

---

*After Step 16E: STOP MODEL DEVELOPMENT. Proceed to Phase 17 — Navigation Integration.*
