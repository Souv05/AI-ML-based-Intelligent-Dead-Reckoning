# STEP 16C Report — Lightweight Transformer Forward-Speed Model
## Phase 16 — "Better AI" (Option C)

## 1. Objective
Evaluate whether a lightweight, explicitly-causal self-attention encoder feeding the same
attention-pooled readout used by 16A's winning GRU v2 and 16B's Hybrid TCN-GRU improves
forward_speed prediction over both, and over the frozen 12D GRU v1, under the same
sequence-level split used by every prior model in this project.

## 2. Dataset
IO-VNBD processed windows, default window length T=20.

## 3. Input / Target
20 (or, if Section 12 ran, up to 60) timesteps x 12 channels: ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']
Target: `forward_speed` (m/s), at the window end.

## 4. Split
Train sequences: 35, Validation: 7, Test: 4
Train windows: 625900, Validation windows: 146853, Test windows: 86331

## 5. Architecture
Linear input projection (12 -> d_model) + fixed sinusoidal positional encoding
-> 2-layer causal
TransformerEncoder (d_model=32,
nhead=2,
dim_feedforward=64)
-> LayerNorm -> additive attention pooling over the window -> MLP head.
Causality is enforced by an explicit boolean attention mask (verified in Section 8's
causality smoke test), a stronger structural guarantee than the unidirectional-recurrence /
causal-convolution conventions used by 12D/16A/16B.

## 6. Staged ablation (validation only, test untouched)
                           name  val_RMSE  val_MAE  best_epoch  parameter_count
     Transformer-E05a-refine-lr  7.176614 5.296888          13            19746
        Transformer-E03a-narrow  7.257277 5.646723           2            19746
        Transformer-E03c-deeper  7.307071 5.692297           3           105602
      Transformer-E01a-huber1.0  7.311432 5.542153           1            72130
      Transformer-E01b-huber2.0  7.426755 5.682825           4            72130
          Transformer-E03b-wide  7.496856 5.650052           1           157282
           Transformer-E00-base  7.873260 5.948182           2            72130
     Transformer-E03d-moreheads  8.039441 6.350273           4            72130
        Transformer-E02-plateau  8.111385 6.346999           1            72130
     Transformer-E04a-lasttoken  8.118192 6.234196           4            18657
     Transformer-E05c-refine-wd  8.202896 6.572243           1            19746
Transformer-E05b-refine-dropout  8.446288 6.775435           2            19746

Selected configuration: Transformer-E03a-narrow-T20 (window_length=20, edge_budget_eligible=True)
{
  "input_size": 12,
  "d_model": 32,
  "nhead": 2,
  "num_layers": 2,
  "dim_feedforward": 64,
  "dropout": 0.1,
  "pooling": "attention",
  "attn_dim": 32,
  "head_hidden": 32,
  "head_dropout": 0.1
}
{
  "lr": 0.001,
  "weight_decay": 0.0,
  "max_epochs": 20,
  "patience": 5,
  "loss_name": "huber",
  "huber_delta": 1.0,
  "use_plateau_scheduler": false
}
Selected epoch count (from tuning): 2

## 7. Mandatory window-length comparison (Section 12)
Edge budget: <= 100000 params, <= 8.0 ms/window (CPU, provisional).
 window_length  val_RMSE  val_MAE  best_epoch  n_train_windows  n_val_windows  parameter_count  inference_ms_per_window_cpu  edge_budget_eligible
            20  7.485149 5.718981           2           625900         146853            19746                     1.386100                  True
            40  7.924638 6.278992           5           312938          73426            19746                     1.595982                  True
            60  7.572083 5.912520           8           208623          48949            19746                     1.191026                  True

## 8. Final test results (first and only test evaluation)
{
  "MAE": 4.218324088284387,
  "RMSE": 5.422254302029522,
  "R2": 0.5093569402169205,
  "MedianAE": 3.4045486450195312,
  "MAE_kmh": 15.185966717823794,
  "RMSE_kmh": 19.52011548730628,
  "test_evaluated_after_freeze": true,
  "window_length": 20,
  "edge_budget_eligible": true
}

## 9. Comparison to frozen benchmarks
- 12D GRU v1 test RMSE: 5.070742 m/s
- 16C Lightweight Transformer test RMSE: 5.422254 m/s
- Relative change vs 12D GRU v1 (test): -6.93%
- 12D GRU v1 validation RMSE (reported): 7.064
- 16A GRU v2 best validation RMSE (reported, GRU2-E05c-T60): 6.696
- 16C Lightweight Transformer best validation RMSE (this run): 7.4851
- 16B Hybrid TCN-GRU test metrics: {"MAE": 4.553824635858259, "RMSE": 5.727047786975912, "R2": 0.4526289832030611, "MedianAE": 3.884871482849121, "MAE_kmh": 16.393768689089733, "RMSE_kmh": 20.617372033113284, "test_evaluated_after_freeze": true, "window_length": 40, "edge_budget_eligible": true}

## 10. Error breakdown by speed regime (test)
speed_bin  n_windows      MAE     RMSE          R2  MedianAE
      0-1       6100 2.036949 3.288759 -170.060862  1.201073
      1-5       3084 3.452712 4.666465  -14.194411  2.711861
     5-10       8393 4.044871 5.208071  -13.364196  3.354404
      >10      68754 4.467376 5.627583   -0.222616  3.725897

## 11. Per-sequence performance
See `per_sequence_metrics.csv`.

## 12. Computational cost
{
  "device_train_eval": "cuda",
  "batch_size": 2048,
  "inference_ms_per_window_batched": 0.015496279296867144,
  "inference_ms_per_window_single_cpu": 1.1658189999707247,
  "model_file_size_bytes": 125336,
  "parameter_count": 19746,
  "training_time_s": 28.108462400000008,
  "note": "Development-machine benchmark; not a smartphone/edge (Phase 21/22) benchmark. Self-attention is O(T^2) in window length, unlike GRU/TCN's O(T) -- watch this term if the window-length sweep (Section 12) favors a longer T.",
  "window_length": 20,
  "edge_budget_max_params": 100000,
  "edge_budget_max_latency_ms_per_window": 8.0,
  "edge_budget_eligible": true
}

## 13. Verdict
- 16C best validation RMSE = 7.4851 m/s (Transformer-E03a-narrow-T20, edge_budget_eligible=True), vs 16A's reported best (GRU2-E05c-T60) = 6.6960 m/s and frozen GRU v1 = 7.0640 m/s.
- 16C's lightweight causal Transformer does NOT beat 16A's tuned pure-GRU-v2 on validation in this run.
- 16C also beats 16B's Hybrid TCN-GRU on test RMSE (5.4223 vs 5.7270).
- Mandatory T=20/40/60 comparison favored T=20 on validation (selected: T=20, edge_budget_eligible=True); compare against 16A's finding that longer context (T=60) was the dominant lever for the GRU.

## 14. Limitations
- No Phase-16 model-selection decision made here — 16D compares 16A/16B/16C together and
  16E freezes the winner.
- No INS/dead reckoning, EKF/UKF, GNSS fusion, map matching, or NHC.
- No Android/edge benchmark; CPU inference timing is a development-machine measurement only.
- No final positional-drift claim.
- Self-attention is O(T^2) in window length (vs GRU/TCN's O(T)); if the window-length sweep
  favors a long T, the latency column in Section 12/18 must be checked against the Phase-22
  10 Hz on-device budget before treating a longer window as a free win.
- The window-length sweep's reconstruction rule (Section 12) assumes non-overlapping
  concatenation of base windows; if 16A's actual T=40/T=60 windows were built differently
  (e.g. overlapping/sliding), the numbers here are directionally but not exactly comparable.
- The 16A reference numbers used for comparison are validation-split numbers reported from
  plots (or recovered from `gru_v2_config.json` when available), not always recomputed from
  a frozen test artifact in this run.
- 16B's test metrics are included only if its `outputs/step16b/final/test_metrics.json`
  exists in this environment; no 16B number is fabricated when it's missing.
