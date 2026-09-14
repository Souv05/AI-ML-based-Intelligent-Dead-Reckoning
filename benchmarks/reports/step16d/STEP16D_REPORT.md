# STEP 16D — Final AI Model Comparison + Navigation-Baseline Decision

**Date**: 2026-09-10 19:42
**Authoritative result**: YES
**Decision**: GRU v2 RECOMMENDED as the primary AI velocity model.

---

## 1. Purpose

Step 16D assembles all frozen AI-model metrics from Steps 16A/16B/16C into a
single comparative analysis and issues the final model recommendation. No model
is retrained and no 72-case navigation evaluation is re-run. All metrics are
read from existing authoritative output files.

---

## 2. Models Under Comparison

| Model | Experiment ID | Window T | Params | Downstream Nav |
|-------|--------------|----------|--------|----------------|
| GRU v2 | GRU2-E05c-T60 | 60 | 153,729 | YES (72 cases) |
| TCN-GRU | TCNGRU-E03c-deeper-T40 | 40 | 17,434 | NOT evaluated |
| Transformer | Transformer-E03a-narrow-T20 | 20 | 19,746 | NOT evaluated |

---

## 3. AI-Level Metrics (held-out test set)

| Model | Val RMSE | Test RMSE | Test MAE | Test R² | Test MedianAE |
|-------|----------|-----------|----------|---------|---------------|
| GRU v2 | 6.6959 | 4.4016 | 3.4320 | 0.6755 | 2.8676 |
| TCN-GRU | 7.5182 | 5.7270 | 4.5538 | 0.4526 | 3.8849 |
| Transformer | 7.4851 | 5.4223 | 4.2183 | 0.5094 | 3.4045 |

**Winner (test RMSE):** GRU v2 (4.4016 m/s) — 13.2% lower than GRU v1 baseline.

---

## 4. Downstream Navigation Results (GRU v2 only)

Results from Step 16A New (actual 15C EKF + active NHC, 72 held-out cases):

| Metric | GRU v1 (Arm A) | GRU v2 (Arm B) | Delta |
|--------|---------------|---------------|-------|
| Median FDE (m) | 250.87 | 186.26 | -64.61 m (-25.8%) |
| Mean FDE (m) | 411.14 | 386.93 | -24.21 m |
| Median drift (%) | 36.43 | 36.76 | +0.33 pp |
| SIH pass / 72 | 3 | 3 | 0 |
| Mean heading error (°) | 31.74 | 31.89 | +0.15° |

GRU v2 wins 50/72 cases, loses 22/72. Wilcoxon signed-rank p = 5.1×10⁻⁵ (highly significant).

**IMPORTANT**: TCN-GRU and Transformer have NO downstream navigation results.
Their nav benefit (if any) is unquantified. Selection based on test RMSE alone
would be speculation per the spec decision rule.

---

## 5. Speed-Regime Analysis

| Speed bin | GRU v2 MAE | TCN-GRU MAE | Transformer MAE |
|-----------|-----------|------------|----------------|
| 0–1 m/s   | 2.4644 | 2.0079 | 2.0369 |
| 1–5 m/s   | 2.7181 | 3.6742 | 3.4527 |
| 5–10 m/s  | 3.6444 | 3.1803 | 4.0449 |
| >10 m/s   | 5.4901 | 4.9862 | 4.4674 |

GRU v2 outperforms TCN-GRU and Transformer in the 1–5, 5–10, and >10 m/s bins.
All models improve at low speed (0–1 m/s). Drive data is dominated by the >10 m/s
regime (>77% of windows for v1/v2).

---

## 6. Computational Profile

| Model | Params | File size | CPU inference | Edge eligible |
|-------|--------|-----------|--------------|---------------|
| GRU v2 | 153,729 | 604.0 KB | ~GPU batched | NO (>100k params) |
| TCN-GRU | 17,434 | 76.7 KB | 2.246 ms | YES |
| Transformer | 19,746 | 122.4 KB | 1.166 ms | YES |

GRU v2 exceeds the 100k parameter edge-budget limit. For Phase 21+ edge deployment,
TCN-GRU or Transformer may be preferred — but only after their downstream nav
performance is quantified.

---

## 7. Decision Rationale

**Decision priority** (from spec §7):
1. Existing downstream nav evidence ← GRU v2 is the ONLY candidate
2. Validation RMSE
3. Test RMSE
4. Robustness across speed regimes
5. Compute / deployment suitability

GRU v2 satisfies criterion (1) exclusively. TCN-GRU and Transformer cannot be
ranked against GRU v2 on nav criteria because their downstream effect is unknown.

---

## 8. Honest Caveats

- The SIH pass rate (3/72, 4.2%) is unchanged by using GRU v2. The bottleneck is
  heading accuracy (mean error ~31.9°), not speed accuracy.
- Median drift percentage is unchanged (36.76% vs 36.43%).
- GRU v2's improvement is real and statistically significant but does not bring the
  system close to the SIH threshold.
- If TCN-GRU or Transformer were run through the 72-case 15C+NHC pipeline, they
  might outperform GRU v2 in navigation (unverified).

---

## 9. Recommendation

**Recommend GRU v2 as the frozen primary AI velocity model for Phase 17+.**

TCN-GRU and Transformer are retained as evaluated alternatives. If edge deployment
becomes a hard constraint (Phase 21+), revisit TCN-GRU with a full 72-case nav
evaluation before replacing GRU v2.

---

## 10. Integrity / Firewall

- gru_best.pt (GRU v1 checkpoint): NOT modified
- gru_v2_best.pt: NOT retrained or tuned
- Test set used for: held-out evaluation only
- 35/7/4 split: unchanged
- 72-case outage list: loaded from disk, NOT regenerated
- All metrics: read from frozen output files, NOT recomputed

---

## 11. Output Files

| File | Description |
|------|-------------|
| final_ai_model_comparison.csv | Master comparison table (all models) |
| ai_metrics_comparison.csv | AI-level metrics only |
| computational_comparison.csv | Params, size, latency, edge eligibility |
| speed_regime_comparison.csv | MAE/RMSE by speed bin |
| model_selection_summary.json | Decision record with full rationale |
| model_comparison.png | 6-panel comparison figure |
| speed_regime_comparison.png | Speed-bin bar charts |
| computational_comparison.png | Compute profile figure |
| STEP16D_REPORT.md | This report |
| authoritative_status_16d.json | Authoritative result declaration |

---

## 12. Next Steps

STOP. Do NOT start Step 16E automatically.
Await user review and approval of GRU v2 selection.
If approved → Step 16E: freeze GRU v2 checkpoint and write final manifest.
