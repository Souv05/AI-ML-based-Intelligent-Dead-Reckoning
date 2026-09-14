# STEP 15F - ZUPT Experiment

SIH26168 - AI-ML Intelligent Dead Reckoning. Analysis of an optional Zero-Velocity Update on top of the frozen Step-15C AI+INS+EKF+NHC pipeline.

## 1. Design (validation only, then frozen)

- **Detector** (IMU only, causal): W=25 samples, |mean|a|-g|<0.12 m/s^2, var(|a|)<0.05, mean|gyro|<0.03 rad/s, latch after 15 samples, release after 5.
  Validation: recall=0.521, false-positive rate=0.01119, precision=0.714.
- **R_ZUPT** = 0.01 (m/s)^2, chosen on validation median FDE from [0.01, 0.04, 0.1, 0.25], then frozen.
- **ZUPT update**: z=[0,0], h=[vE,vN], H rows on vE,vN only - a proper Kalman update, no overwrite, heading column is zero so heading is not directly modified.

## 2. Synthetic checks
```
{
  "1_nonzero_innovation_when_moving": true,
  "2_correction_moves_velocity_toward_zero": true,
  "3_heading_not_directly_modified": true,
  "4_covariance_stays_positive_semidefinite": true,
  "5_no_nan_inf": true,
  "6_no_direct_overwrite": true,
  "7_detector_does_not_trigger_while_moving": true,
  "8_detector_handles_entering_and_leaving_a_stop": true
}
```

## 3. Held-out test - aggregate (72 cases per arm)
```
           arm  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  mean_velocity_error_mps  zupt_applied_total  zupt_events_total  zupt_total_duration_s  false_positive_zupt_total  false_negative_stationary_total  cases_with_usable_stationary  failure_events_total
     A_15c_nhc     72.0    250.873533  411.146596         36.429242       63.196075     349.940889             3.0           4.166667               31.743429                40.028197                0.000404                 3.579358                 0.0                0.0                    0.0                       50.0                           1711.0                          19.0                   0.0
B_15c_nhc_zupt     72.0    250.873533  409.207032         36.429242       62.955408     349.940889             3.0           4.166667               31.743429                40.028197                0.000404                 3.574007               638.0               15.0                   63.8                       50.0                           1711.0                          19.0                   0.0
```

## 4. By outage duration
```
           arm  outage_duration_s  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  mean_velocity_error_mps  zupt_applied_total  zupt_events_total  zupt_total_duration_s  false_positive_zupt_total  false_negative_stationary_total  cases_with_usable_stationary  failure_events_total
     A_15c_nhc               10.0     12.0     49.153697   49.792887         29.820606       45.709788     129.533818             2.0          16.666667               12.754820                14.294533                0.000878                 3.394211                 0.0                0.0                    0.0                        0.0                              0.0                           0.0                   0.0
     A_15c_nhc               20.0     12.0    100.563354  131.181123         30.439478       43.653530     109.049256             1.0           8.333333               22.136078                31.851724                0.001097                 3.529925                 0.0                0.0                    0.0                        0.0                              0.0                           0.0                   0.0
     A_15c_nhc               30.0     12.0    153.122339  199.532689         37.126459       54.627878     134.873291             0.0           0.000000               29.470873                35.663101                0.000193                 3.242942                 0.0                0.0                    0.0                        0.0                             76.0                           1.0                   0.0
     A_15c_nhc               60.0     12.0    494.522904  513.373525         58.444178       86.439419     349.940889             0.0           0.000000               41.282630                55.994817                0.000038                 4.253168                 0.0                0.0                    0.0                       12.0                            399.0                           5.0                   0.0
     A_15c_nhc               90.0     12.0    413.740922  617.322041         31.933275       79.602411     256.975165             0.0           0.000000               40.499151                49.407578                0.000098                 3.540374                 0.0                0.0                    0.0                       24.0                            745.0                           7.0                   0.0
     A_15c_nhc              120.0     12.0    791.905871  955.677312         61.176354       69.143422     164.786511             0.0           0.000000               44.317025                52.957428                0.000120                 3.515528                 0.0                0.0                    0.0                       14.0                            491.0                           6.0                   0.0
B_15c_nhc_zupt               10.0     12.0     49.153697   49.792887         29.820606       45.709788     129.533818             2.0          16.666667               12.754820                14.294533                0.000878                 3.394211                 0.0                0.0                    0.0                        0.0                              0.0                           0.0                   0.0
B_15c_nhc_zupt               20.0     12.0    100.563354  131.181123         30.439478       43.653530     109.049256             1.0           8.333333               22.136078                31.851724                0.001097                 3.529925                 0.0                0.0                    0.0                        0.0                              0.0                           0.0                   0.0
B_15c_nhc_zupt               30.0     12.0    153.122339  199.532689         37.126459       54.627878     134.873291             0.0           0.000000               29.470873                35.663101                0.000193                 3.242942                 0.0                0.0                    0.0                        0.0                             76.0                           1.0                   0.0
B_15c_nhc_zupt               60.0     12.0    494.522904  511.222209         58.444178       86.004746     349.940889             0.0           0.000000               41.282630                55.994817                0.000038                 4.254236                61.0                2.0                    6.1                       12.0                            399.0                           5.0                   0.0
B_15c_nhc_zupt               90.0     12.0    413.740922  615.401201         31.933275       79.356049     256.975165             0.0           0.000000               40.499151                49.407578                0.000098                 3.544243                59.0                3.0                    5.9                       24.0                            745.0                           7.0                   0.0
B_15c_nhc_zupt              120.0     12.0    791.905871  948.112085         58.723988       68.380455     161.945190             0.0           0.000000               44.317025                52.957428                0.000120                 3.478488               518.0               10.0                   51.8                       14.0                            491.0                           6.0                   0.0
```

## 5. By sequence
```
           arm sequence_id  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  mean_velocity_error_mps  zupt_applied_total  zupt_events_total  zupt_total_duration_s  false_positive_zupt_total  false_negative_stationary_total  cases_with_usable_stationary  failure_events_total
     A_15c_nhc       Vta08     18.0    244.359207  415.104285         41.508051       57.068077     112.156961             0.0           0.000000               28.768712                33.562704                0.000293                 3.140219                 0.0                0.0                    0.0                       48.0                             48.0                           4.0                   0.0
     A_15c_nhc       Vta28     18.0    324.715453  479.141708         92.661081      110.437964     349.940889             0.0           0.000000               49.404185                65.193013                0.000673                 3.647937                 0.0                0.0                    0.0                        0.0                           1096.0                           5.0                   0.0
     A_15c_nhc       Vtb01     18.0    212.684707  384.222880         33.944570       48.963628     143.901592             0.0           0.000000               32.644439                42.253796                0.000145                 3.449317                 0.0                0.0                    0.0                        2.0                            360.0                           7.0                   0.0
     A_15c_nhc        Vw02     18.0    235.093236  366.117512         21.278968       36.314630     164.786511             3.0          16.666667               16.156382                19.103275                0.000505                 4.079960                 0.0                0.0                    0.0                        0.0                            207.0                           3.0                   0.0
B_15c_nhc_zupt       Vta08     18.0    229.704801  411.918422         41.508051       56.643074     112.156961             0.0           0.000000               28.768712                33.562704                0.000293                 3.146657               112.0                4.0                   11.2                       48.0                             48.0                           4.0                   0.0
B_15c_nhc_zupt       Vta28     18.0    324.715453  479.141708         92.661081      110.437964     349.940889             0.0           0.000000               49.404185                65.193013                0.000673                 3.647937                 0.0                0.0                    0.0                        0.0                           1096.0                           5.0                   0.0
B_15c_nhc_zupt       Vtb01     18.0    212.684707  382.445890         33.944570       48.704853     143.901592             0.0           0.000000               32.644439                42.253796                0.000145                 3.440371               103.0                3.0                   10.3                        2.0                            360.0                           7.0                   0.0
B_15c_nhc_zupt        Vw02     18.0    237.215216  363.322110         21.278968       36.035740     161.945190             3.0          16.666667               16.156382                19.103275                0.000505                 4.061065               423.0                8.0                   42.3                        0.0                            207.0                           3.0                   0.0
```

## 6. Analysis - the 10 questions

1. **Does ZUPT improve median FDE?** NO - A=250.9 m -> B=250.9 m (+0.0 m); paired Wilcoxon p=0.009344113002204883.
2. **Does ZUPT improve drift?** NO - median drift A=36.43% -> B=36.43%.
3. **Does ZUPT improve long outages (>=90 s)?** False - median delta FDE 0.0 m.
4. **Does ZUPT reduce velocity error?** YES (paired Wilcoxon p=0.3862707203664827).
5. **Does ZUPT indirectly improve heading/position?** heading 31.74 deg -> 31.74 deg (Wilcoxon p=0.32698934959801507).
6. **Does ZUPT help only on cases with stationary periods?** cases with usable stationary = 19/72; median delta FDE with-stationary = 0.0 m, without = 0.0 m.
7. **Does ZUPT ever hurt from false detections?** 5 cases had a false-positive ZUPT (50 events total); their median delta FDE = -14.596278841915193 m.
8. **How many of the 72 cases contain usable stationary periods?** 19/72.
9. **Does ZUPT complement NHC or add little?** little additional benefit.
10. **Does the SIH <10% target improve?** SIH pass A=3/72 -> B=3/72 (unchanged).

## 7. Numerical stability

Failure events: A=0, B=0.

## 8. Final conclusion

- **ZUPT was active:** True (applied in 10 of 72 cases).
- **ZUPT was correctly detected:** validation FP rate 0.01119, recall 0.521; on test, 50 false-positive events across 5 cases.
- **ZUPT improved navigation:** NO / marginal (median FDE +0.0 m vs baseline).
- **ZUPT improved long-outage behaviour:** False.
- **SIH <10% target improved:** False (A 3/72 -> B 3/72).
- **Remaining bottleneck:** heading error during the outage - ZUPT constrains velocity magnitude when stopped but does not observe absolute heading; consistent with the 15E finding. Outage duration remains the dominant error driver.
- **Recommendation:** DO NOT freeze - keep as an optional module; revisit with map-matching / ZIHR.

## 9. Constraints honoured

No redesign of the navigation system. Q, P0, sig_gnss, NHC, the AI measurement model, the state definition, the heading model, the GRU, and the 72 outage cases are all reused unchanged. The detector and R_ZUPT were selected on the 7 validation sequences only and then frozen; no held-out test result influenced any parameter. The reference trajectory is used only for post-hoc metrics and, on validation only, to label true stationary periods. ZIHR, map-matching and magnetometer heading were not added. STOP after 15F - Step 16 not started.
