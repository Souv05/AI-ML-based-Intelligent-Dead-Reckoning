# STEP 12D Report — GRU Forward-Speed Model

## 1. Objective
Evaluate whether a causal GRU using the raw 20x12 smartphone-IMU sequence improves
forward_speed prediction under the same sequence-level split used by earlier models.

## 2. Dataset
IO-VNBD processed windows.

## 3. Input
20 timesteps x 12 channels:
['acc_x', 'acc_y', 'acc_z', 'gyro_x', 'gyro_y', 'gyro_z', 'mag_x', 'mag_y', 'mag_z', 'roll', 'pitch', 'yaw']

## 4. Target
`forward_speed` in m/s, at the window end.

## 5. Split
Train sequences: 35
Validation sequences: 7
Test sequences: 4

Train windows: 625900
Validation windows: 146853
Test windows: 86331

## 6. Normalization
Per-channel z-score fitted on TRAIN ONLY.
Target scaling, if used internally, was also fitted on TRAIN ONLY.

## 7. GRU baseline
Hidden size 64, one layer, dropout 0, Adam lr=1e-3, weight_decay=0,
maximum 20 epochs, validation early stopping patience 5.

Baseline validation metrics:
{
  "MAE": 5.702850179621098,
  "RMSE": 7.506786406777407,
  "R2": 0.3816977823112151,
  "MedianAE": 4.629209518432617
}

## 8. Tuning
10 controlled candidates.
Selection metric: validation RMSE, then validation MAE, then parameter count.
The test set was not used during tuning.

Best parameters:
{
  "hidden_size": 128,
  "num_layers": 2,
  "learning_rate": 0.0005,
  "dropout": 0.2,
  "weight_decay": 0.0001
}

Best epoch from tuning: 2

## 9. Final test results
{
  "MAE": 3.9892628406038755,
  "RMSE": 5.070741779180324,
  "R2": 0.5709095127206887,
  "MedianAE": 3.3284502029418945,
  "MAE_kmh": 14.361346226173952,
  "RMSE_kmh": 18.254670405049165
}

## 10. Frozen XGBoost comparison
12B-F test RMSE: 6.840263 m/s
12D GRU test RMSE: 5.070742 m/s
Relative change vs 12B-F: 25.87%

## 11. Per-sequence performance
See `per_sequence_metrics.csv`.

## 12. Computational cost
{
  "device": "cpu",
  "batch_size": 2048,
  "inference_ms_per_batch": 84.6600399999943,
  "inference_ms_per_window": 0.041337910156247215,
  "model_file_size_bytes": 618965,
  "parameter_count": 153729,
  "training_time_s": 236.96638990000002,
  "note": "Development-machine CPU benchmark; not a smartphone/edge benchmark."
}

## 13. Limitations
- No TCN or Transformer.
- No INS/dead reckoning.
- No EKF/UKF.
- No GNSS fusion.
- No map matching or NHC.
- No Android/edge benchmark.
- No final positional-drift claim.
- CPU inference timing is only a development-machine measurement.

## 14. Conclusion
12D GRU improves over the frozen 12B-F XGBoost benchmark by 25.87% RMSE.

## 15. Next experiment
STEP 12E — TCN.
