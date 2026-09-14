# Step 12B - XGBoost Forward-Speed Estimation

## 1. Objective
Estimate vehicle **forward_speed** (m/s) from 12 smartphone inertial/orientation channels, as a tree-boosting baseline that must be directly comparable to Step 12A (RandomForest). No EKF / RNN / map-matching / DR here.

## 2. Dataset
- IO-VNBD processed windows via `data/processed/manifest.csv`
- windows: train 625,900 / validation 146,853 / test 86,331
- sampling rate (measured): [10.0] Hz; window = 20 timesteps (2.0 s); stride 1

## 3. Input Sensors
`['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']` - accelerometer (m/s^2), gyroscope (rad/s), magnetometer (uT), orientation roll/pitch/yaw (deg). Phone-only; no GNSS, no vehicle/OBD channel.

## 4. Target Definition
`forward_speed` = reference vehicle speed (Velocity km/hr / 3.6) at window end, nowcast horizon=0. Unit m/s. Nowcast (horizon 0): speed at the last sample of the window.

## 5. Step 12A Compatibility
Identical dataset, features, target, split, window, tabular representation (9 summary stats/channel -> 108 features) and metrics. **Only** change: `RandomForestRegressor` -> `XGBRegressor`. Step 12A saved outputs present at run time: True (RandomForest re-fitted here with the 12A recipe for a same-environment comparison).

## 6. Data Split
Sequence-wise, whole drives, from `manifest['split']` (built by `scripts/prepare_dataset.py`, split_seed 26168). Drive sub-segments kept together.
```
{
  "train": [
    "M",
    "S1",
    "S2",
    "V-Vfa01",
    "Vta01a",
    "Vta01b",
    "Vta02",
    "Vta04",
    "Vta06",
    "Vta07",
    "Vta10",
    "Vta12",
    "Vta14",
    "Vta15",
    "Vta16",
    "Vta17",
    "Vta21",
    "Vta22",
    "Vta23",
    "Vta24",
    "Vta26",
    "Vta29",
    "Vta30",
    "Vtb02",
    "Vtb03",
    "Vtb05",
    "Vtb08",
    "Vw04",
    "Vw05",
    "Vw10",
    "Vw11",
    "Vw12",
    "Vw14a",
    "Vw14b",
    "Vw14c"
  ],
  "validation": [
    "S3a",
    "S3b",
    "S3c",
    "V-Vfa02",
    "Vw03",
    "Vw16a",
    "Vw16b"
  ],
  "test": [
    "Vta08",
    "Vta28",
    "Vtb01",
    "Vw02"
  ]
}
```

## 7. Leakage Prevention
`outputs/step12b/leakage_report.md` - STATUS **PASS**. No GPS/reference/vehicle field in inputs; train/val/test sequence-disjoint; drive groups not split; no scaler fitted on any split (XGBoost uses raw features); window ends at t, target at t.

## 8. Temporal Representation
Each `(20, 12)` window -> `108` features: for every channel the 9 stats `['mean', 'std', 'min', 'max', 'median', 'rms', 'first', 'last', 'delta']`, computed only from samples inside the window. No future samples, no target-derived feature.

## 9. Feature Engineering
See `engineered_feature_list.csv` / `feature_schema.json`. Deterministic, applied identically to train/val/test, never fitted.

## 10. XGBoost Configuration
```json
{
  "objective": "reg:squarederror",
  "n_estimators": 500,
  "max_depth": 6,
  "learning_rate": 0.05,
  "subsample": 0.8,
  "colsample_bytree": 0.8,
  "min_child_weight": 1,
  "reg_alpha": 0.0,
  "reg_lambda": 1.0,
  "random_state": 42,
  "n_jobs": -1,
  "tree_method": "hist"
}
```
Early stopping: 50 rounds on the validation RMSE -> best_iteration = 185 (186 trees kept; best val RMSE 7.7327). Test never used for any model decision.

## 11. Training Procedure
Load -> validate schema/target/splits -> leakage checks -> NaN/Inf checks -> 108-feature extraction -> Baseline 0 -> reproduce RF(12A) -> train XGBoost on train only with early stopping on validation -> freeze -> single test pass -> per-sequence + error + importance + compute + blackout + distance diagnostics.

## 12. Validation Results
| MAE (m/s) | RMSE (m/s) | R2 | MedianAE (m/s) | MAE (km/h) |
|---|---|---|---|---|
| 6.2793 | 7.7327 | 0.3439 | 5.8239 | 22.6055 |

## 13. Final Test Results
| MAE (m/s) | RMSE (m/s) | R2 | MedianAE (m/s) | MAE (km/h) |
|---|---|---|---|---|
| 5.8081 | 7.4221 | 0.0807 | 4.8066 | 20.9091 |

## 14. Comparison with Step 12A

| model              | split      |    MAE |    RMSE |      R2 |   MedianAE |   MAE_kmh |
|:-------------------|:-----------|-------:|--------:|--------:|-----------:|----------:|
| Baseline 0 (mean)  | validation | 9.1455 | 10.6439 | -0.2431 |     9.8564 |   32.9239 |
| RandomForest (12A) | validation | 6.8759 |  8.4082 |  0.2243 |     6.7234 |   24.7533 |
| XGBoost (12B)      | validation | 6.2793 |  7.7327 |  0.3439 |     5.8239 |   22.6055 |
| Baseline 0 (mean)  | test       | 7.3641 |  8.6696 | -0.2543 |     7.4075 |   26.5108 |
| RandomForest (12A) | test       | 6.5718 |  8.3426 | -0.1615 |     5.5772 |   23.6584 |
| XGBoost (12B)      | test       | 5.8081 |  7.4221 |  0.0807 |     4.8066 |   20.9091 |

- Test RMSE vs Baseline 0: **+14.39%**
- Test RMSE vs RandomForest (12A): **+11.03%**

## 15. Per-Sequence Results

| sequence_id   |   n_samples |     MAE |    RMSE |        R2 |   MedianAE |   mean_true_speed |   mean_pred_speed |   max_abs_error |
|:--------------|------------:|--------:|--------:|----------:|-----------:|------------------:|------------------:|----------------:|
| Vw02          |       52693 | 7.2023  | 8.75149 | -0.297721 |    6.95787 |          18.7076  |           12.5779 |         21.5426 |
| Vtb01         |       25790 | 3.8157  | 4.8197  |  0.336571 |    3.24897 |          13.6332  |           12.2232 |         15.5345 |
| Vta28         |        4191 | 2.97642 | 4.03248 |  0.40392  |    2.09041 |           9.32992 |           11.1252 |         17.6484 |
| Vta08         |        3657 | 3.01467 | 3.802   |  0.693425 |    2.1984  |           9.25956 |           10.5285 |         12.4312 |

## 16. Feature Importance
Top 15 by gain (gain = total loss reduction from splits on the feature; **association, not causation**):

| feature       |     gain |   weight |    cover |   gain_pct |
|:--------------|---------:|---------:|---------:|-----------:|
| acc_z__std    | 332523   |      363 | 166360   |   28.7137  |
| acc_z__min    |  84507.7 |      204 |  46597.7 |    7.29732 |
| pitch__std    |  77194.3 |      280 |  92093.6 |    6.6658  |
| gyro_x__std   |  50598.2 |      160 | 100502   |    4.36921 |
| gyro_x__rms   |  42478.7 |      122 |  62525.9 |    3.66807 |
| roll__std     |  40362.6 |      126 |  40623.7 |    3.48535 |
| mag_z__std    |  36150.2 |      245 |  55819.8 |    3.1216  |
| gyro_y__std   |  28169.8 |      177 |  66078.4 |    2.43249 |
| pitch__min    |  21177.3 |      314 |  30278.9 |    1.82868 |
| pitch__median |  20802.9 |      115 |  15572.2 |    1.79635 |
| mag_y__std    |  18549.6 |      348 |  88177.2 |    1.60178 |
| mag_x__max    |  18352.3 |      360 |  38025.4 |    1.58473 |
| pitch__rms    |  14317.1 |       43 |  33310.6 |    1.2363  |
| gyro_z__std   |  13799   |      220 |  51659.9 |    1.19155 |
| mag_z__median |  12675.8 |      207 |  67562.2 |    1.09457 |

## 17. Error Analysis
- Global test bias (mean true - pred): **+4.0217 m/s** (under-prediction on average).
- Best test sequence `Vta08`, worst `Vw02`.
- MAE by true-speed bucket and by window dynamics: see `error_analysis.md`.

## 18. Computational Benchmark
```json
{
  "environment": "desktop CPU benchmark (NOT Android/edge)",
  "train_time_s_xgboost": 15.51,
  "n_test_samples": 86331,
  "inference_ms_per_sample": 0.00046,
  "throughput_samples_per_s": 2159487.0,
  "model_json_bytes": 1719700,
  "n_trees_used": 186
}
```
Desktop CPU only - **not** an Android/edge real-time measurement.

## 19. GNSS Blackout Diagnostic
```json
{
  "n_blackout_windows_test": 20141,
  "n_gnss_visible_windows_test": 66190,
  "metrics_during_blackout": {
    "MAE": 5.909017086029053,
    "RMSE": 7.553225039418179,
    "R2": -0.1429530382156372,
    "MedianAE": 4.720067977905273
  },
  "metrics_when_gnss_visible": {
    "MAE": 5.777355194091797,
    "RMSE": 7.381757065348749,
    "R2": 0.13179439306259155,
    "MedianAE": 4.8390069007873535
  }
}
```
Sensor inputs stay available during the flagged blackout windows; GNSS/reference is hidden from the model and used only to score. This is a behavioural sanity check, **not** the final dead-reckoning evaluation.

## 20. Limitations
- Static per-window summary features discard intra-window temporal order beyond first/last/delta; an RNN/TCN (Step 12C+) may capture more.
- No hyperparameter search (by design) - these are initial baseline params.
- Speed-only model; no heading, no 2D position, no drift claim.
- Test set is 4 drives / ~86k windows - per-sequence numbers are indicative.
- IO-VNBD phone IMU is loosely coupled to vehicle motion on many drives (see `outputs/FINDINGS.md`); this bounds achievable accuracy for any model here.

## 21. Conclusion
XGBoost beats Baseline 0 and beats the Step 12A RandomForest on test RMSE, using the identical feature representation. Leakage-free, reproducible (seed 42).

## 22. Recommendation for Step 12C
Proceed to STEP 12C (LSTM / GRU) on the same windows/target/split to test whether an explicit temporal model improves over the static-feature tree baselines. Keep XGBoost as a candidate for a later residual-learning stage. Do not down-select the final model yet.