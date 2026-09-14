# STEP 13C - FULL SIH TEST-SET: Classical DR vs AI-DR (frozen 12D GRU)

## 1. Objective
Compare classical dead reckoning against AI dead reckoning (frozen 12D GRU forward-speed) during simulated GNSS outages, on the complete prepared test split. Evaluation only - no EKF, GNSS fusion, map matching, NHC, or model retraining.

## 2. Dataset
Prepared IO-VNBD processed windows. Test split: ['Vta08', 'Vta28', 'Vtb01', 'Vw02']. Per-sample parquet + (N,20,12) windows, 10 Hz, 12 phone IMU/orientation channels, local ENU reference in reference_x/reference_y (m).

## 3. Dataset coverage
```
sequence_id split  rows  duration_s  number_of_valid_outages  number_of_skipped_outages                                                                                                         skip_reasons
      Vta08  test  3676       367.5                       18                       8272                                                                {"start_speed<5_kmh": 5196, "no_gnss_at_start": 3076}
      Vta28  test  4210       420.9                       18                       7686                                                                {"no_gnss_at_start": 5484, "start_speed<5_kmh": 2202}
      Vtb01  test 32459      3245.8                       18                      83415 {"start_speed<5_kmh": 19247, "logging_gap_in_span": 210, "no_gnss_at_start": 37936, "missing_window_in_span": 26022}
       Vw02  test 52712      5271.1                       18                      93473                                                              {"start_speed<5_kmh": 20286, "no_gnss_at_start": 73187}
```

## 4. Frozen train/validation/test split
35 train / 7 validation / 4 test sequences (unchanged from 12A-12E). 13C uses TEST ONLY.

## 5. Test sequences
```
sequence_id  rows  duration_s  number_of_valid_outages  number_of_skipped_outages
      Vta08  3676       367.5                       18                       8272
      Vta28  4210       420.9                       18                       7686
      Vtb01 32459      3245.8                       18                      83415
       Vw02 52712      5271.1                       18                      93473
```

## 6. Classical DR
Step 13A `propagate_outage` reused unmodified (trapezoidal yaw integration for heading; trapezoidal double-integration of acceleration for velocity and position). Inputs adapted from the smartphone parquet: gravity removed from phone acc via roll/pitch, body x/y taken as longitudinal/lateral, yaw rate = rad2deg(gyro_z). Initial east/north/speed/heading from reference_* at the outage-start sample (pre-outage).

## 7. Frozen 12D GRU AI-DR
GRU(hidden=128, layers=2), weights outputs/step12d/final/gru_best.pt, train-only scaler. eval()/no_grad, speed clipped at 0. Frozen benchmark: test RMSE 5.070742 m/s, MAE 3.989263, R2 0.57091.

## 8. Outage methodology
Durations [10, 20, 30, 60, 90, 120] s; up to 3 starts per (sequence,duration) drawn with np.random.default_rng(SEED+duration) from rows with speed >= 5.0 km/h, GNSS available at start, a full window for every outage sample, and no logging gap (max dt <= 0.5s). Rejected cases are logged, never silently skipped.

## 9. Fair comparison
Identical for both methods: test sequence, outage start, duration, dt, initial position, initial heading, **heading array** (produced once by 13A and shared), coordinate frame, trapezoidal position integration, reference trajectory. Only the forward-velocity source differs.

## 10. Metrics
ATE RMSE, RTE RMSE, FDE, max position error (Step 13A `trajectory_metrics`, unmodified), plus distance travelled (reference path length) and drift_percent = FDE / distance * 100.

## 11. Full test-set results (aggregated by duration)
### Classical DR
```
      method  outage_duration_s  n_runs   mean_ATE  median_ATE    std_ATE    mean_FDE  median_FDE    std_FDE  mean_max_error  median_max_error  mean_drift_percent  median_drift_percent  std_drift_percent  worst_drift_percent
Classical_DR               10.0    12.0  12.664061    9.827794   9.854370   27.041588   20.554067  21.136514       27.041588         20.554067           23.958616             14.370568          21.420884            70.401530
Classical_DR               20.0    12.0  59.893335   42.357145  45.828609  119.375595   90.972378  90.023649      119.382459         90.972378           45.749667             33.427726          40.776696           142.250935
Classical_DR               30.0    12.0 107.756985  102.246119  62.608270  215.581688  206.593197 124.904590      215.599824        206.593197           63.185835             58.226253          46.624618           187.076988
Classical_DR               60.0    12.0 267.974783  283.198700 132.282420  527.699512  567.440545 266.303299      528.529180        567.440545           99.467922             86.245841         111.311330           444.251820
Classical_DR               90.0    12.0 312.381345  278.863608 165.736457  589.708137  456.641462 320.425955      592.519592        456.641462           77.714598             40.554497          85.005281           270.796643
Classical_DR              120.0    12.0 604.614999  457.224111 362.517814 1151.693631  868.704050 680.741315     1153.400644        868.704050           88.140079             68.999080          63.302902           229.868190
```

### AI-DR (12D GRU)
```
   method  outage_duration_s  n_runs   mean_ATE  median_ATE    std_ATE    mean_FDE  median_FDE     std_FDE  mean_max_error  median_max_error  mean_drift_percent  median_drift_percent  std_drift_percent  worst_drift_percent
AI_DR_GRU               10.0    12.0  23.716821   25.098569  10.095626   40.723558   46.196093   18.967241       41.237375         47.419308           36.337889             28.721771          29.460160           112.469810
AI_DR_GRU               20.0    12.0  60.800229   58.223724  35.377812  106.314752   86.284753   74.409653      108.913555         89.619937           34.281792             25.790256          25.521782           111.915556
AI_DR_GRU               30.0    12.0 106.711262   93.288997  64.056820  200.557610  173.629004  129.880949      201.470241        174.048514           53.803911             52.442719          34.856897           118.101350
AI_DR_GRU               60.0    12.0 276.247629  269.536431 165.876851  537.390801  539.156246  307.971828      537.844451        539.156246           88.006447             55.146917          85.478981           339.991978
AI_DR_GRU               90.0    12.0 372.113240  280.663745 233.584349  715.510191  498.681801  469.994025      720.241361        498.681801           86.891114             51.208674          82.189639           269.113433
AI_DR_GRU              120.0    12.0 617.738602  450.783666 515.197272 1160.889256  868.263021 1019.143034     1176.626399        868.263021           71.136195             55.285456          46.007576           170.846487
```

## 12. Classical vs AI-DR
```
{
  "AI wins": 36,
  "Classical wins": 36,
  "Ties": 0,
  "Total paired cases": 72,
  "AI win rate %": 50.0
}
```
Median FDE: Classical 284.32 m  vs  AI-DR 220.90 m  (+22.3% for AI-DR).
Median drift: Classical 45.67%  vs  AI-DR 42.06%  (+7.9% for AI-DR).
Overall verdict (median FDE): **AI-DR**.

## 13. SIH drift analysis
```
{
  "Classical_DR": {
    "method": "Classical_DR",
    "total_runs": 72,
    "passing_runs": 8,
    "failing_runs": 64,
    "pass_rate_percent": 11.11111111111111
  },
  "AI_DR_GRU": {
    "method": "AI_DR_GRU",
    "total_runs": 72,
    "passing_runs": 2,
    "failing_runs": 70,
    "pass_rate_percent": 2.7777777777777777
  }
}
```
SIH target < 10.0% drift, evaluated per run. Worst drift: Classical 444.3%, AI-DR 340.0%. A mean below 10% is NOT treated as compliance - see per-run pass rate above.

## 14. Per-sequence analysis
```
sequence_id       method  runs  median_FDE_m  median_drift_pct  worst_drift_pct
      Vta08    AI_DR_GRU    18    246.355302         32.721251       118.101350
      Vta08 Classical_DR    18    227.294753         46.593277       110.592139
      Vta28    AI_DR_GRU    18    309.694623         59.421066       339.991978
      Vta28 Classical_DR    18    365.575705         71.132637       444.251820
      Vtb01    AI_DR_GRU    18    226.273129         47.800367       162.053892
      Vtb01 Classical_DR    18    375.387490         65.675291       127.965893
       Vw02    AI_DR_GRU    18    217.187678         23.075662       170.846487
       Vw02 Classical_DR    18    190.239187         17.010742       229.868190
```

## 15. Failure cases
Eight highest-drift runs (either method):
```
sequence_id  outage_duration_s  outage_start       method       FDE_m  drift_percent
      Vta28               60.0           694 Classical_DR  810.184785     444.251820
      Vta28               60.0           694    AI_DR_GRU  620.045468     339.991978
      Vta28               90.0           611 Classical_DR 1186.221768     270.796643
      Vta28               90.0           647    AI_DR_GRU 1203.776357     269.113433
      Vta28               90.0           647 Classical_DR 1149.480976     256.975284
      Vta28               90.0           611    AI_DR_GRU 1053.663233     240.535517
       Vw02              120.0         45621 Classical_DR 2748.955739     229.868190
      Vta28              120.0           145 Classical_DR 1869.078742     207.963255
```

## 16. Limitations
- Phone IMU is weakly coupled to vehicle motion (project EDA): phone body axes are assumed to align with vehicle longitudinal/lateral, which is not guaranteed per trip.
- Heading for BOTH methods integrates phone gyro_z; heading error is the dominant term and is not addressed here (that is Step 14 / EKF territory).
- Outage starts are a seeded sample (<=3 per case), not an exhaustive sweep of every row.
- Reference-derived initial conditions assume a clean pre-outage GNSS fix.

## 17. Conclusion
On the full prepared test set, AI-DR (frozen 12D GRU forward-speed) with a shared classical heading changes median FDE by +22.3% and median drift by +7.9% versus classical acceleration-integration DR. Neither method is a finished GNSS-denied solution; heading remains the limiting error.

## 18. Next step
STEP 13D - SIH drift + robustness analysis (per the roadmap). EKF / fusion begins at Step 14.

---
### Declarations
FULL PREPARED TEST SET USED = YES  
ALL 4 TEST SEQUENCES EVALUATED = YES  
TRUNCATION = NO  
RANDOM TEST SAMPLING = NO  
EKF USED = NO  
GRU RETRAINED = NO  
GNSS USED DURING OUTAGE = NO  
RESULTS AUTHORITATIVE = YES  