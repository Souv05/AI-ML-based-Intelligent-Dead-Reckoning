# Error Analysis — Step 12C LSTM

LSTM test RMSE: 6.9019 m/s | MAE: 5.4528 m/s | R2: 0.2050.

LSTM vs 12B-F tuned XGBoost test RMSE improvement: -6.16% (positive = LSTM better).

Worst test sequence: Vw02 (RMSE=8.0271, n_windows=52693).

No scenario labels are fabricated. Any braking/turning/stationary breakdown is reported only when supported by existing dataset metadata/signals.
