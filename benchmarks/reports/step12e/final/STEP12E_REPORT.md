# STEP 12E Report — TCN

## Final result
- 12D GRU RMSE: 5.070742 m/s
- 12E TCN RMSE: 5.606758 m/s
- 12E TCN MAE: 4.385910 m/s
- 12E TCN R2: 0.475399
- RMSE change vs 12D: -10.57%
- Current best: 12D GRU

## Integrity
```json
{
  "same target": true,
  "raw 20x12 input": true,
  "train-only normalization": true,
  "TCN baseline trained": true,
  "validation-only tuning": true,
  "best selected by validation RMSE": true,
  "final TCN trained": true,
  "TCN frozen": true,
  "test after freeze": true,
  "per-sequence metrics": true,
  "compute benchmark": true
}
```

STEP 12E does not establish positional drift, GNSS-denied navigation accuracy, INS/EKF/UKF performance, or smartphone real-time performance.
