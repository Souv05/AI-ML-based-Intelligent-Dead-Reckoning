# STEP 16A (NEW, AUTHORITATIVE) - GRU v2 Downstream Revalidation

SIH26168 - AI-ML Intelligent Dead Reckoning. Does the already-frozen GRU v2 improve downstream navigation over GRU v1 inside the actual Step-15C AI + EKF + active-NHC pipeline, over the frozen 72 outage cases?

## 1. Frozen model artifacts

- GRU v1: `D:\SIH 2026\outputs\step12d\final\gru_best.pt`  md5 `27e1dd1eeadce6bc`  T=20  params 153729
- GRU v2: `D:\SIH 2026\outputs\step16a\gru_v2_best.pt`  md5 `4761355bb0764145`  T=60  params 153729  (hidden 128, 2 layers, dropout 0.2)
- Neither retrained, tuned, or overwritten. Scaler = frozen 12D `scaler.json` for both.

## 2. Navigation engine (actual 15C)

`EKF5_15C`: constant-velocity predict (vE, vN, psi pass through - **no** hard assignment `vE=v_GRU*sin(psi)`). GRU velocity enters as a measurement (`z=v_GRU`, `h=vE*sin psi + vN*cos psi`). Active NHC (`z=0`, `h=vE*cos psi - vN*sin psi`, `NHC_STD_MPS=1.0`). Q, P0, sig_gnss, sig_AI, the GNSS/course reacquisition logic - all reused verbatim from Step 14 / 15C. No ZUPT in the primary arms.

## 3. Dataset split

- 35 train / 7 validation / 4 test.  Test = ['Vta08', 'Vta28', 'Vtb01', 'Vw02'].

## 4. 72-case accounting

- 72 frozen outage cases (4 seq x 6 durations x 3 starts) from `D:\SIH 2026\outputs\step14_ekf\final\outage_cases.csv`.  Executed: A 72/72, B 72/72.  Excluded: 0.

## 5. Test-firewall status

GRU v2 is already frozen -> the held-out test may be evaluated. No test result was used to change any model / architecture / window / scaler / Q / P0 / AI noise / NHC / outage case / model selection. `config.json['firewall']` records every flag = False.

## 6. GRU v1 vs GRU v2 - AI metrics (held-out test windows)
```
 model     RMSE      MAE       R2  MedianAE     n
GRU_v1 5.070727 3.987608 0.570912  3.328142 86331
GRU_v2 4.401557 3.431960 0.675535  2.867649 86171
```

## 7. GRU v1 vs GRU v2 - navigation metrics (72 cases each)
```
     arm  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_velocity_error_mps  failure_events_total
A_gru_v1     72.0    250.872101  411.143739         36.428768       63.195443       349.935300             3.0           4.166667               31.743426                40.028189                0.000404               0.612687                 3.579349                   0.0
B_gru_v2     72.0    186.260505  386.929337         36.760615       59.540558       291.185273             3.0           4.166667               31.888846                40.192749                0.000495               0.797512                 3.398557                   0.0
```

delta median FDE (v1 - v2) = +64.61 m  (positive = GRU v2 better).  delta mean FDE = +24.21 m.

## 8. Duration analysis
```
     arm  outage_duration_s  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_velocity_error_mps  failure_events_total
A_gru_v1               10.0     12.0     49.152872   49.792692         29.821141       45.709270       129.532346             2.0          16.666667               12.754812                14.294523                0.000878               0.328231                 3.394182                   0.0
A_gru_v1               20.0     12.0    100.561797  131.181811         30.439062       43.653514       109.048938             1.0           8.333333               22.136065                31.851705                0.001097               0.612687                 3.529968                   0.0
A_gru_v1               30.0     12.0    153.120089  199.531563         37.125775       54.627367       134.871220             0.0           0.000000               29.470864                35.663077                0.000193               0.097096                 3.242931                   0.0
A_gru_v1               60.0     12.0    494.523526  513.371167         58.443229       86.438560       349.935300             0.0           0.000000               41.282636                55.994826                0.000038               0.064891                 4.253160                   0.0
A_gru_v1               90.0     12.0    413.749181  617.317872         31.932930       79.601486       256.971270             0.0           0.000000               40.499162                49.407588                0.000098               0.144532                 3.540347                   0.0
A_gru_v1              120.0     12.0    791.915127  955.667327         61.175071       69.142459       164.783743             0.0           0.000000               44.317016                52.957416                0.000120               0.340209                 3.515508                   0.0
B_gru_v2               10.0     12.0     53.819772   53.321551         31.839682       47.335217       131.949699             0.0           0.000000               12.819182                14.353950                0.001015               0.364545                 3.677262                   0.0
B_gru_v2               20.0     12.0     85.047028  120.991172         20.813177       40.966640       106.895230             1.0           8.333333               22.707267                32.440465                0.001469               0.797512                 3.269701                   0.0
B_gru_v2               30.0     12.0    150.410205  187.467256         38.768743       52.484177       134.135039             2.0          16.666667               29.578724                35.807338                0.000176               0.075783                 3.101438                   0.0
B_gru_v2               60.0     12.0    445.110300  473.878624         53.243030       77.726315       291.185273             0.0           0.000000               41.287952                56.007117                0.000052               0.077915                 3.875534                   0.0
B_gru_v2               90.0     12.0    428.067800  574.806715         33.616478       72.557922       225.065479             0.0           0.000000               40.488038                49.388854                0.000100               0.138393                 3.085857                   0.0
B_gru_v2              120.0     12.0    700.793039  911.110707         64.117574       66.173075       166.262080             0.0           0.000000               44.451910                53.158769                0.000159               0.587467                 3.381551                   0.0
```

## 9. Sequence analysis
```
     arm sequence_id  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  sih_pass_count  sih_pass_rate_pct  mean_heading_error_deg  final_heading_error_deg  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_velocity_error_mps  failure_events_total
A_gru_v1       Vta08     18.0    244.344340  415.099724         41.507856       57.067277       112.156665             0.0           0.000000               28.768707                33.562696                0.000293               0.381058                 3.140156                   0.0
A_gru_v1       Vta28     18.0    324.711763  479.134355         92.658765      110.436200       349.935300             0.0           0.000000               49.404179                65.192992                0.000673               0.612687                 3.647822                   0.0
A_gru_v1       Vtb01     18.0    212.684077  384.221384         33.944105       48.963566       143.900616             0.0           0.000000               32.644440                42.253795                0.000145               0.037431                 3.449379                   0.0
A_gru_v1        Vw02     18.0    235.105538  366.119491         21.279589       36.314727       164.783743             3.0          16.666667               16.156376                19.103273                0.000505               0.340209                 4.080042                   0.0
B_gru_v2       Vta08     18.0    155.521803  386.444339         40.261792       51.911392       108.053254             0.0           0.000000               28.809878                33.617749                0.000423               0.522772                 3.179727                   0.0
B_gru_v2       Vta28     18.0    314.966255  441.356135         98.268453      102.459995       291.185273             0.0           0.000000               49.848546                65.637037                0.000901               0.797512                 3.472625                   0.0
B_gru_v2       Vtb01     18.0    212.221906  386.112909         34.592213       49.098094       142.640191             0.0           0.000000               32.666146                42.316565                0.000122               0.038516                 3.329700                   0.0
B_gru_v2        Vw02     18.0    184.227410  333.803967         18.285543       34.692750       166.262080             3.0          16.666667               16.230812                19.199646                0.000535               0.364545                 3.612177                   0.0
```

median FDE delta (v1 - v2) by sequence:
```
sequence_id  median_FDE_v1_minus_v2  v2_better
      Vta08               88.822537       True
      Vta28                9.745508       True
      Vtb01                0.462171       True
       Vw02               50.878128       True
```

## 10. Paired case analysis

- GRU v2 wins 50 / loses 22 / ties 0 of 72 on FDE.
- median delta FDE (v1 - v2) = +10.89 m ; mean = +24.21 m.
- paired Wilcoxon on FDE: stat=592.0, p=5.0859292757270285e-05.
- deterministic representative cases (min / median / max delta FDE): see `representative_cases.csv`.

## 11. SIH <10% pass rate

- GRU v1: 3/72 (4.17%).   GRU v2: 3/72 (4.17%).

## 12. Failure count

- numerical failure events: GRU v1 = 0, GRU v2 = 0.

## 13. Does GRU v2 improve navigation?

- AI improves: True (RMSE 5.071 -> 4.402 m/s).
- median FDE improves: True (250.9 -> 186.3 m).
- mean FDE improves: True (411.1 -> 386.9 m).
- median drift: 36.43% -> 36.76%.
- **Outcome: A  (AI improves AND navigation improves) -> strong evidence GRU v2 is useful**

## 14. Should GRU v2 remain the preferred AI-velocity candidate?

GRU v2 remains the preferred AI-velocity candidate: better AI quality, navigation improves, stable, SIH pass not reduced.

Decision rule (spec S23): AI velocity quality + downstream navigation + stability/failure + SIH drift behaviour - not AI RMSE alone.

## 15. Relation to old Phase-16 results

Old 16A/16D navigation numbers used the Step-14 EKF **without active NHC**; old 17B reconstructed 15C. Both are historical references only. This report's navigation numbers are produced with the actual 15C + active NHC and are the authoritative 16A downstream result.

## 16. Constraints honoured

No retraining, no tuning, no architecture/window/scaler/weight change, no EKF Q / P0 / AI-noise / NHC change, no ZUPT in the primary arms, no new outage cases, no model selection from test. STOP after 16A - Step 16B / Transformer / map-matching / deployment not started.
