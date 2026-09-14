# SIH 26168 — Step 12A Initial ML Baseline

## 1. Objective
Predict smartphone-IMU-derived vehicle forward velocity (forward_speed, m/s)
during a simulated GNSS outage, as the first ML baseline for PS 26168.

## 2. Dataset
- Train sequences: 35
- Validation sequences: 7
- Test sequences: 4
- Total windows: 859084
- Sampling rate: [10.0] Hz
- Window length: 20 timesteps
- Sensor features: ['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']

## 3. Input Features
['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']

## 4. Target
forward_speed (m/s) — Nowcast (horizon=0) forward speed of the vehicle at the last IMU sample of the window.

## 5. Leakage Controls
- Sequence-wise split (verified in this notebook, section 06)
- No GPS/reference input in X (verified)
- No future information (window ends at t; target at t, horizon=0)
- Test set untouched until section 14

## 6. Baseline 0
{
  "train_mean": 12.432490348815918,
  "validation": {
    "MAE": 9.145538330078125,
    "RMSE": 10.643852831018423,
    "R2": -0.24305522441864014,
    "MedianAE": 9.856379508972168
  },
  "test": {
    "MAE": 7.364105224609375,
    "RMSE": 8.669636535417734,
    "R2": -0.2543179988861084,
    "MedianAE": 7.407509803771973
  }
}

## 7. Initial ML Model
- Backend: sklearn_cpu
- Device: cpu
- Configuration: {"n_estimators": 100, "max_depth": null, "min_samples_split": 2, "min_samples_leaf": 1, "max_features": "sqrt", "random_state": 42, "n_jobs": -1}

## 8. Results
Validation: {
  "MAE": 6.875914188980173,
  "RMSE": 8.408198798802294,
  "R2": 0.22429135933288435,
  "MedianAE": 6.723378636837005
}
Test: {
  "MAE": 6.571764601977242,
  "RMSE": 8.34258575193705,
  "R2": -0.16146801587051263,
  "MedianAE": 5.577171980142593,
  "MAE_ms": 6.571764601977242,
  "MAE_kmh": 23.658352567118072
}

## 9. Error Analysis
See `error_analysis.md`.

## 10. Blackout Diagnostic
Blackout diagnostic produced for sequence Vta08

## 11. Limitations
- no EKF
- no final INS
- no map matching
- no GNSS+INS fusion
- no Android deployment
- no final positional-drift claim ("<10% distance" is a Step-12A-onward target, not evaluated here)

## 12. Conclusion
Random Forest IMPROVES over Baseline 0 on test RMSE (8.3426 vs 8.6696 m/s).
