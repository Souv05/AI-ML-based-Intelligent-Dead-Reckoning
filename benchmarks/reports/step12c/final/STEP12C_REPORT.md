# STEP 12C Report — LSTM Sequence Model

## 1. Experiment objective

Determine whether an LSTM trained directly on raw IMU windows improves `forward_speed` prediction over the frozen 12B-F Tuned XGBoost model.


## 2. Dataset

IO-VNBD, same sequence-level split as 12A/12B-F: train=35, validation=7, test=4 sequences. Windows: train=625900, val=146853, test=86331.


## 3. Input specification

20 x 12 raw IMU window (no flattening): ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']


## 4. Target

forward_speed (m/s) - reference vehicle speed (Velocity (km/hr) / 3.6) at window-end


## 5. Scaling

Per-channel z-score using TRAIN-only mean/std; target z-score is used only for training stability and is de-normalized before reported metrics.


## 6. Baseline LSTM configuration

{
  "hidden_size": 64,
  "num_layers": 1,
  "dropout": 0.0,
  "learning_rate": 0.001,
  "weight_decay": 0.0,
  "batch_size": 512,
  "max_epochs": 30,
  "patience": 5
}


## 7. Hyperparameter search methodology

Staged validation-only random search: 3 trials per stage across architecture and regularization/learning-rate stages. The test set was never inspected during tuning.


## 8. Best hyperparameters

{
  "hidden_size": 64,
  "num_layers": 1,
  "dropout": 0.0,
  "learning_rate": 0.001,
  "weight_decay": 0.0,
  "batch_size": 512,
  "max_epochs": 30,
  "patience": 5
}


## 9. Validation results

LSTM baseline: {
  "MAE": 5.721833229064941,
  "RMSE": 7.36816917505207,
  "R2": 0.4043216109275818,
  "MedianAE": 4.610471248626709,
  "training_time_s": 198.83129810000003,
  "best_epoch": 2
}

LSTM tuned: {
  "MAE": 5.721833229064941,
  "RMSE": 7.36816917505207,
  "R2": 0.4043216109275818,
  "MedianAE": 4.610471248626709,
  "best_epoch": 2,
  "training_time_s": 226.8848814999999
}


## 10. Final test results

| Model                |     MAE |    RMSE |          R2 |   MedianAE |
|:---------------------|--------:|--------:|------------:|-----------:|
| Baseline 0           | 7.36411 | 8.66964 | -0.254318   |    7.40751 |
| 12A Random Forest    | 6.57176 | 8.34259 | -0.161468   |    5.57717 |
| 12B XGBoost baseline | 6.05833 | 7.77045 | -0.00762343 |    4.96115 |
| 12B-F Tuned XGBoost  | 5.17787 | 6.50137 |  0.294632   |    4.42394 |
| 12C LSTM             | 5.45281 | 6.90193 |  0.205037   |    4.53245 |


## 11. Per-sequence performance

See `per_sequence_metrics.csv`.


## 12. Error analysis

See `error_analysis.md`.


## 13. Blackout diagnostic

Velocity-only preliminary diagnostic; it is not a positional-drift result.


## 14. Computational cost

{
  "lstm": {
    "training_time_s": 226.8848814999999,
    "parameter_count": 22081,
    "model_file_size_bytes": 92015,
    "ms_per_window": 0.011478710937495862,
    "device": "cpu",
    "note": "Measured on this machine's CPU; not a smartphone/edge benchmark."
  }
}

## 15. Limitations

- GRU, TCN, Transformer and navigation fusion are not part of this experiment.
- No EKF/UKF/final INS, map matching, or GNSS fusion.
- No Android/TFLite/ONNX deployment.
- No final SIH positional-drift claim.
- CPU benchmark is not a smartphone benchmark.

## 16. Conclusion

12C LSTM does not improve over 12B-F Tuned XGBoost on test RMSE (-6.16% change).