# STEP 12B-F Report — Fine-Tuned XGBoost

## 1. Experiment objective
Determine whether a carefully tuned XGBoost model improves `forward_speed` prediction
from smartphone IMU window statistics over the 12A Random Forest baseline.

## 2. Dataset
IO-VNBD, same sequence-level split as 12A: train=35,
validation=7, test=4 sequences.
Windows: train=625900, val=146853, test=86331.

## 3. Input specification
20 x 12 IMU window: ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']

## 4. Feature engineering
12 channels x 9 statistics (mean, std, min, max, median, rms, first, last, delta)
= 108 features. Identical to 12A's `feature_schema.json` (verified).

## 5. Target
forward_speed (m/s) - reference vehicle speed (Velocity (km/hr) / 3.6) at window-end

## 6. Baseline XGBoost configuration
{
  "objective": "reg:squarederror",
  "tree_method": "hist",
  "random_state": 42,
  "n_jobs": -1,
  "n_estimators": 500,
  "learning_rate": 0.05,
  "max_depth": 6,
  "min_child_weight": 1,
  "subsample": 0.8,
  "colsample_bytree": 0.8,
  "gamma": 0,
  "reg_alpha": 0,
  "reg_lambda": 1
}
Validation metrics (frozen before tuning): {
  "MAE": 6.20834493637085,
  "RMSE": 7.715055376844254,
  "R2": 0.3469133973121643,
  "MedianAE": 5.602886199951172,
  "training_time_s": 16.60862445831299
}

## 7. Hyperparameter search methodology
Staged, validation-only random search: Stage A (tree complexity: max_depth,
min_child_weight, gamma) -> Stage B (boosting rate: learning_rate, n_estimators) ->
Stage C (sampling: subsample, colsample_bytree) -> Stage D (regularization: reg_alpha,
reg_lambda) -> Stage E (joint refinement around the best-so-far configuration).
8 trials per stage (A-D) + 8 joint-refinement trials
= 40 total trials. Early stopping (patience=50,
cap=2000) used for tree count within each trial. Test set never inspected
during this section. Full trial log: `tuning/tuning_results.csv`.

## 8. Best hyperparameters
{
  "max_depth": 4,
  "min_child_weight": 12.0,
  "gamma": 0.1,
  "learning_rate": 0.05,
  "n_estimators": 1200,
  "subsample": 0.7,
  "colsample_bytree": 0.9,
  "reg_alpha": 1.0,
  "reg_lambda": 0.5
}
Selected by lowest validation RMSE (ties -> validation MAE -> fewer trees).

## 9. Validation results
12B baseline: {
  "MAE": 6.20834493637085,
  "RMSE": 7.715055376844254,
  "R2": 0.3469133973121643,
  "MedianAE": 5.602886199951172,
  "training_time_s": 16.60862445831299
}
12B-F tuned : {
  "MAE": 5.992252826690674,
  "RMSE": 7.368165550964893,
  "R2": 0.40432214736938477,
  "MedianAE": 5.439663887023926
}

## 10. Final test results
{
  "baseline0": {
    "MAE": 7.364105224609375,
    "RMSE": 8.669636535417734,
    "R2": -0.2543179988861084,
    "MedianAE": 7.407509803771973,
    "MAE_mps": 7.364105224609375,
    "MAE_kmh": 26.510778808593752,
    "RMSE_mps": 8.669636535417734,
    "RMSE_kmh": 31.210691527503844
  },
  "rf_12a": {
    "MAE": 6.571764601977242,
    "RMSE": 8.34258575193705,
    "R2": -0.16146801587051263,
    "MedianAE": 5.577171980142593,
    "MAE_ms": 6.571764601977242,
    "MAE_kmh": 23.658352567118072,
    "MAE_mps": 6.571764601977242,
    "RMSE_mps": 8.34258575193705,
    "RMSE_kmh": 30.03330870697338
  },
  "xgb_12b_baseline": {
    "MAE": 6.058331489562988,
    "RMSE": 7.770450313288739,
    "R2": -0.007623434066772461,
    "MedianAE": 4.961150169372559,
    "MAE_mps": 6.058331489562988,
    "MAE_kmh": 21.80999336242676,
    "RMSE_mps": 7.770450313288739,
    "RMSE_kmh": 27.97362112783946
  },
  "xgb_12bf_tuned": {
    "MAE": 5.177872180938721,
    "RMSE": 6.501372559222291,
    "R2": 0.2946315407752991,
    "MedianAE": 4.423943042755127,
    "MAE_mps": 5.177872180938721,
    "MAE_kmh": 18.640339851379395,
    "RMSE_mps": 6.501372559222291,
    "RMSE_kmh": 23.404941213200246
  }
}

## 11. Comparison against 12A Random Forest
                 Model      MAE     RMSE        R2  MedianAE  Training Time (s)  Inference Time (ms/window)  Model Size (bytes)
            Baseline 0 7.364105 8.669637 -0.254318  7.407510           0.000000                    0.000000                   0
     12A Random Forest 6.571765 8.342586 -0.161468  5.577172         111.705708                         NaN          5620436609
12B XGBoost (baseline) 6.058331 7.770450 -0.007623  4.961150          16.608624                    0.005363             3619038
   12B-F Tuned XGBoost 5.177872 6.501373  0.294632  4.423943          17.792573                    0.006145              818141

12B-F vs 12A RF (test RMSE): 22.07% change
12B-F vs 12B baseline (test RMSE): 16.33% change

## 12. Per-sequence performance
See `final/per_sequence_metrics.csv`. Highest-RMSE test sequence noted in `error_analysis.md`.

## 13. Error analysis
See `final/error_analysis.md`.

## 14. Feature importance
Top feature (by gain): acc_z__std.
Feature importance indicates model reliance, not physical causality. Full table:
`final/feature_importance.csv`.

## 15. Computational cost
{
  "12b_baseline": {
    "training_time_s": 16.60862445831299,
    "model_file_size_bytes": 3619038,
    "inference_ms_per_window": 0.005363486707210541,
    "n_features": 108
  },
  "12bf_tuned": {
    "training_time_s": 17.792572736740112,
    "model_file_size_bytes": 818141,
    "inference_ms_per_window": 0.006144866347312927,
    "n_trees": 395,
    "n_features": 108
  },
  "12a_rf_for_reference": {
    "model_file_size_bytes": 5620436609,
    "training_time_s": 111.70570802688599,
    "inference_batch_size": 256,
    "inference_time_per_sample_ms": 0.14194007962942123,
    "device": "cpu",
    "random_forest_backend": "sklearn_cpu"
  },
  "note": "Measured on this machine's CPU; not a smartphone/edge benchmark."
}
No smartphone/edge benchmark has been run; do not claim real-time smartphone performance.

## 16. Limitations
- no LSTM/GRU/TCN/Transformer
- no EKF/UKF/final INS
- no map matching
- no GNSS fusion
- no Android/edge deployment
- no final positional-drift claim (blackout diagnostic above is preliminary velocity-only)

## 17. Conclusion
12B-F CLEARLY improves over the 12A Random Forest baseline on test RMSE.
