# Step 12B error analysis

- global test bias (mean y_true - y_pred): **+4.0217 m/s** (under-prediction on average)
- best test sequence: `Vta08` | worst: `Vw02`
- test RMSE vs Baseline 0: **+14.39%**
- test RMSE vs RandomForest (12A): **+11.03%**

## MAE by true-speed bucket

| bucket | MAE (m/s) | n |
|---|---|---|
| stationary (<0.5 m/s) | 1.9593 | 5327 |
| low (0.5-5 m/s) | 4.2286 | 3857 |
| cruise (5-15 m/s) | 2.4801 | 23719 |
| high (>=15 m/s) | 7.7833 | 53428 |

## Window dynamics

- high-IMU-variability windows MAE: 5.2899 m/s
- steadier windows MAE: 5.9808 m/s

Turning/braking labels are NOT invented - only quantities computable from the existing window metadata are reported.
