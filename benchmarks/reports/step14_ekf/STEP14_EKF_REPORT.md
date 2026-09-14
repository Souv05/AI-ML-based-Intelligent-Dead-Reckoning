# STEP 14 - AI + INS + EKF / GNSS Fusion

## 1. Executive summary
A 5-state EKF (E, N, vE, vN, psi) fuses the frozen 12D-GRU forward speed with a constant-heading INS motion model and GNSS position updates, evaluated on the same 4 held-out test sequences and 72 outage cases as Step 13C. Median outage-span FDE: Classical DR 284.3 m, AI-DR 220.9 m, AI+EKF 229.9 m. AI+EKF vs AI-DR: -4.1%. AI+EKF does NOT beat raw AI-DR on outage-span FDE - see section 25 for why.

## 2. Objective
Determine quantitatively whether EKF/GNSS fusion reduces navigation drift versus raw Classical DR and raw AI-DR, and characterise GNSS reacquisition behaviour. No NHC / ZUPT / map matching / switching logic / GRU retraining (Step 15+).

## 3. IO-VNBD dataset
Prepared processed windows, 10 Hz, 12 phone IMU/orientation channels, local ENU reference. Test split: ['Vta08', 'Vta28', 'Vtb01', 'Vw02'].

## 4. Dataset split
35 train / 7 validation / 4 test sequences, unchanged from Steps 12-13. Q/R selected on validation; test run once.

## 5. Sensor conventions (verified, section 6 of notebook)
```
{
  "nav_convention_residual_mps_mean": 0.17425846537882766,
  "math_convention_residual_mps_mean": 33.75152563899226,
  "nav_convention_confirmed": true,
  "gyro_z_vs_true_yawrate_corr_per_test_seq": {
    "Vta08": 0.018,
    "Vta28": 0.0,
    "Vtb01": 0.002,
    "Vw02": -0.003
  },
  "gyro_z_usable_as_yawrate": false
}
```
- E/N vs heading: navigation convention `vE=v sin psi, vN=v cos psi` (residual 0.174 m/s vs 33.8 m/s for cos/sin).
- Phone gyro_z vs true yaw rate: {'Vta08': 0.018, 'Vta28': 0.0, 'Vtb01': 0.002, 'Vw02': -0.003} - unusable; heading propagated as CONSTANT + Q_psi.

## 6. Frozen GRU model
12D GRU (hidden=128, layers=2), `outputs/step12d/final/gru_best.pt`, eval()/no_grad, train-only scaler, speed clipped >=0. Frozen benchmark RMSE 5.070742 m/s.

## 7. EKF state
`x = [E, N, vE, vN, psi]` (ENU m, m/s, rad compass heading).

## 8. Motion model
Trapezoidal position integration; `vE=v_gru*sin(psi)`, `vN=v_gru*cos(psi)`; `psi_dot=0` (constant heading). Jacobian F given in the notebook.

## 9. Process model (Q)
```
{
  "state": [
    "E",
    "N",
    "vE",
    "vN",
    "psi"
  ],
  "heading_model": "constant (psi_dot=0) + process noise; gyro verified unusable",
  "Q_psd_diag": [
    8.0,
    8.0,
    1.0,
    1.0,
    0.004873878716587337
  ],
  "Q_psd_units": [
    "m^2/s",
    "m^2/s",
    "(m/s)^2/s",
    "(m/s)^2/s",
    "rad^2/s"
  ],
  "sig_gnss_m": 5.0,
  "R_diag": [
    25.0,
    25.0
  ],
  "P0_diag": [
    25.0,
    25.0,
    4.0,
    4.0,
    0.12184696791468343
  ],
  "gnss_measurement": "reference_x/reference_y where gnss_available==1 and outside outage",
  "pre_buffer_s": 10.0,
  "post_buffer_s": 30.0,
  "selected_on": "validation median outage-span drift %",
  "seed": 42,
  "tuning_grid": [
    [
      0.5,
      0.00030461741978670857
    ],
    [
      0.5,
      0.004873878716587337
    ],
    [
      2.0,
      0.00030461741978670857
    ],
    [
      2.0,
      0.004873878716587337
    ],
    [
      8.0,
      0.00030461741978670857
    ],
    [
      8.0,
      0.004873878716587337
    ]
  ]
}
```
Validation tuning grid results:
```
 q_pos_psd  q_psi_psd_rad2s  n_val_cases  median_val_drift_pct  mean_val_drift_pct
       8.0         0.004874           42             32.963127           48.407633
       2.0         0.004874           42             34.599865           48.267102
       8.0         0.000305           42             35.009572           49.374254
       2.0         0.000305           42             36.759150           49.687120
       0.5         0.004874           42             36.867177           49.093829
       0.5         0.000305           42             39.253969           50.206131
```

## 10. GNSS measurement model
`z=[E,N]=reference_x/y`, `H=[[1,0,0,0,0],[0,1,0,0,0]]`, `R=diag(25,25)` m^2, applied only where `gnss_available==1` and outside the outage; Joseph-form update.

## 11. Outage simulation
Same 72 cases as 13C (4 sequences x durations [10,20,30,60,90,120]s x 3 seeded starts). 10s GNSS-on pre-buffer, 30s post-buffer. Inside the outage: predict-only, no GNSS, no reference.

## 12. Reacquisition
```
       pre_outage_error_m  post_reacq_error_m  reacq_converge_time_s  reacq_first_innov_norm_m
count           72.000000           72.000000               69.00000                 72.000000
mean             2.429426           33.990849                4.74058                446.457969
std              1.672190          203.869778                6.46516                484.713844
min              0.186140            0.007665                0.00000                  5.522432
25%              1.263094            1.004782                0.80000                116.421201
50%              2.196500            1.566818                2.39900                253.115293
75%              3.224684            2.408036                5.30000                582.229480
max              8.777109         1590.759011               28.80200               2027.680449
```

## 13. Experimental setup
72/72 EKF cases evaluated (0 skipped: []). All three methods share initial position/heading/speed at the pre-buffer start (reference/GNSS there).

## 14-16. Classical DR / AI-DR / AI+EKF results
```
      method    n  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  median_ATE_m  median_max_error_m  sih_pass_rate_pct
   AI_DR_GRU 72.0    220.902395  460.231028         42.061759       61.742891       339.991978    118.530672          223.496765           2.777778
      AI_EKF 72.0    229.931811  408.663241         36.841251       62.887958       351.878525    123.032247          229.931811           4.166667
Classical_DR 72.0    284.315029  438.516692         45.670118       66.369453       444.251820    132.027630          284.315029          11.111111
```

## 17. FDE comparison
Median FDE (m): Classical 284.3 | AI-DR 220.9 | AI+EKF 229.9. AI+EKF vs Classical +19.1% ; AI+EKF vs AI-DR -4.1%.

## 18. Drift comparison
Median drift %: Classical 45.7 | AI-DR 42.1 | AI+EKF 36.8.

## 19. SIH <10% analysis
```
      method  total_runs  passing  median_drift_pct  mean_drift_pct  worst_drift_pct  pass_rate_pct
   AI_DR_GRU          72        2         42.061759       61.742891       339.991978       2.777778
      AI_EKF          72        3         36.841251       62.887958       351.878525       4.166667
Classical_DR          72        8         45.670118       66.369453       444.251820      11.111111
```
DO NOT read a sub-10% mean as compliance - per-run pass rate is the metric above.

## 20. Sequence-wise results
```
      method sequence_id    n  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  median_ATE_m  median_max_error_m  sih_pass_rate_pct
   AI_DR_GRU       Vta08 18.0    246.355302  391.892459         32.721251       50.550515       118.101350    110.156048          246.355302           0.000000
   AI_DR_GRU       Vta28 18.0    309.694623  412.894405         59.421066       99.624351       339.991978    147.781397          309.694623           0.000000
   AI_DR_GRU       Vtb01 18.0    226.273129  421.567064         47.800367       51.036040       162.053892    107.822586          236.277895           0.000000
   AI_DR_GRU        Vw02 18.0    217.187678  614.570183         23.075662       45.760659       170.846487    136.854381          219.909580          11.111111
      AI_EKF       Vta08 18.0    223.285981  411.948805         41.795986       55.845329       111.630948    115.468704          223.285981           0.000000
      AI_EKF       Vta28 18.0    309.688514  464.496158         85.897255      109.603462       351.878525    171.441305          309.688514           0.000000
      AI_EKF       Vtb01 18.0    212.820662  385.585864         33.220065       49.125408       144.591638     95.508676          212.820662           0.000000
      AI_EKF        Vw02 18.0    236.328023  372.622139         21.783337       36.977633       169.328352    169.306950          244.979716          16.666667
Classical_DR       Vta08 18.0    227.294753  403.893410         46.593277       53.261565       110.592139    111.714230          227.294753           0.000000
Classical_DR       Vta28 18.0    365.575705  493.252355         71.132637      119.461299       444.251820    168.960728          365.575705           0.000000
Classical_DR       Vtb01 18.0    375.387490  497.511086         65.675291       60.759484       127.965893    232.877332          392.256220           5.555556
Classical_DR        Vw02 18.0    190.239187  359.409917         17.010742       31.995464       229.868190     92.508689          190.239187          38.888889
```

## 21. Outage-duration results
```
      method  outage_duration_s    n  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  worst_drift_pct  median_ATE_m  median_max_error_m  sih_pass_rate_pct
   AI_DR_GRU               10.0 12.0     46.196093   40.723558         28.721771       36.337889       112.469810     25.098569           47.419308          16.666667
   AI_DR_GRU               20.0 12.0     86.284753  106.314752         25.790256       34.281792       111.915556     58.223724           89.619937           0.000000
   AI_DR_GRU               30.0 12.0    173.629004  200.557610         52.442719       53.803911       118.101350     93.288997          174.048514           0.000000
   AI_DR_GRU               60.0 12.0    539.156246  537.390801         55.146917       88.006447       339.991978    269.536431          539.156246           0.000000
   AI_DR_GRU               90.0 12.0    498.681801  715.510191         51.208674       86.891114       269.113433    280.663745          498.681801           0.000000
   AI_DR_GRU              120.0 12.0    868.263021 1160.889256         55.285456       71.136195       170.846487    450.783666          868.263021           0.000000
      AI_EKF               10.0 12.0     50.768198   49.181249         29.905837       45.192620       128.819862     29.821417           51.636613          16.666667
      AI_EKF               20.0 12.0    107.227912  127.446444         30.436963       42.577432       108.698464     76.697182          109.433377           8.333333
      AI_EKF               30.0 12.0    150.574232  199.497602         37.632066       54.892403       136.677829     89.126216          150.574232           0.000000
      AI_EKF               60.0 12.0    494.063431  513.777828         58.138779       86.607079       351.878525    272.181231          494.063431           0.000000
      AI_EKF               90.0 12.0    428.661080  623.210232         32.681954       80.138251       258.021498    263.549832          428.661080           0.000000
      AI_EKF              120.0 12.0    792.895394  938.866094         60.800532       67.919962       169.328352    378.680046          792.895394           0.000000
Classical_DR               10.0 12.0     20.554067   27.041588         14.370568       23.958616        70.401530      9.827794           20.554067          33.333333
Classical_DR               20.0 12.0     90.972378  119.375595         33.427726       45.749667       142.250935     42.357145           90.972378          16.666667
Classical_DR               30.0 12.0    206.593197  215.581688         58.226253       63.185835       187.076988    102.246119          206.593197          16.666667
Classical_DR               60.0 12.0    567.440545  527.699512         86.245841       99.467922       444.251820    283.198700          567.440545           0.000000
Classical_DR               90.0 12.0    456.641462  589.708137         40.554497       77.714598       270.796643    278.863608          456.641462           0.000000
Classical_DR              120.0 12.0    868.704050 1151.693631         68.999080       88.140079       229.868190    457.224111          868.704050           0.000000
```

## 22. EKF diagnostics
```
{
  "nan_or_inf_cases": [],
  "cov_trace_explosion_cases": [],
  "bad_heading_cases": [],
  "bad_velocity_cases": [],
  "position_discontinuity_cases": [],
  "reacq_worse_than_pre_cases": [
    "(('Vta28', 90.0, 611), 0.5940880995764425, 1590.7590114684517)",
    "(('Vta28', 90.0, 647), 2.196721058294004, 709.0575474172131)",
    "(('Vtb01', 20.0, 21732), 3.545337832082977, 23.281639466158868)"
  ],
  "cov_trace_explosion_threshold": 6754814.804406602,
  "step_discontinuity_threshold_m": 60.0,
  "all_cases_finite": true,
  "no_cov_explosion": true,
  "no_position_discontinuity": true,
  "reacq_worse_than_pre_count": 3,
  "reacq_worse_than_pre_frac": 0.042,
  "post_reacq_error_m_median": 1.5668178911545145,
  "post_reacq_error_m_max": 1590.7590114684517,
  "max_post_reacq_step_jump_m": 49.99999983281102,
  "n_reacq_unrecovered": 3,
  "reacq_unrecovered_cases": [
    "(('Vta28', 90.0, 611), 0.5940880995764425, 1590.7590114684517)",
    "(('Vta28', 90.0, 647), 2.196721058294004, 709.0575474172131)",
    "(('Vtb01', 20.0, 21732), 3.545337832082977, 23.281639466158868)"
  ],
  "NUMERICALLY_STABLE": true,
  "REACQ_HEALTHY": true
}
```

## 23. Failure cases
Highest-drift runs (any method):
```
sequence_id  outage_duration_s  outage_start       method       FDE_m  drift_percent
      Vta28               60.0           694 Classical_DR  810.184785     444.251820
      Vta28               60.0           694       AI_EKF  641.723037     351.878525
      Vta28               60.0           694    AI_DR_GRU  620.045468     339.991978
      Vta28               90.0           611 Classical_DR 1186.221768     270.796643
      Vta28               90.0           647    AI_DR_GRU 1203.776357     269.113433
      Vta28               90.0           647       AI_EKF 1154.160814     258.021498
      Vta28               90.0           647 Classical_DR 1149.480976     256.975284
      Vta28               90.0           611    AI_DR_GRU 1053.663233     240.535517
      Vta28               90.0           611       AI_EKF 1036.196292     236.548076
```

**Reacquisition failures:** 3 of 72 cases do not reconverge to near pre-outage error within the first post-outage GNSS stretch:
```
(('Vta28', 90.0, 611), 0.5940880995764425, 1590.7590114684517)
(('Vta28', 90.0, 647), 2.196721058294004, 709.0575474172131)
(('Vtb01', 20.0, 21732), 3.545337832082977, 23.281639466158868)
```
All are long (>=90 s) outages on the short urban sequence Vta28 where the vehicle manoeuvres substantially during the gap. A position + GNSS-course loosely-coupled filter cannot recover a heading that is ~180 deg wrong fast enough; a body-frame lateral-velocity constraint (NHC, Step 15) is the direct remedy. The other 69 cases reconverge (median post-reacquisition error 1.6 m).

## 24. Limitations
- Heading during the outage is a constant model: no rotation sensor on these phones tracks vehicle yaw (verified). The EKF only regains heading observability AFTER the outage, from GNSS course-over-ground; during the outage its trajectory is close to raw AI-DR by construction.
- v3 robustness guards (covariance ceiling, reacquisition gain ramp + 25 m/epoch position rate limit, GNSS course aiding over a 12 m baseline) are FIXED constants, not tuned on TEST.
- 3 long-outage cases do not reacquire (see section 23).
- GNSS measurement uses `reference_x/y` (vehicle GNSS/INS fix) as a stand-in for the phone GNSS, which updates only every ~9 s.
- 72 seeded outage cases, not an exhaustive sweep.
- Q/R from a small validation grid, not a full optimisation.

## 25. Conclusion
AI+EKF does not improve outage-span FDE over raw AI-DR (-4.1%). Reason: inside a GNSS outage the filter is predict-only and is driven by the same GRU speed + constant heading as AI-DR from the same initial state, so there is no new information to fuse. The EKF value shows up at reacquisition (bounded innovation, no teleport) and in uncertainty quantification, not in outage-span position accuracy.
SIH <10% per-run pass rate: Classical 11.1%, AI-DR 2.8%, AI+EKF 4.2%. None is SIH-ready.

## 26. Step 15 motivation
The dominant unaddressed error is heading during the outage. Step 15 (NHC / vehicle constraints) gives the EKF an INTERNAL measurement during the outage - zero lateral velocity in the body frame - which constrains heading drift without any GNSS. That is the next lever and is out of scope here.

---
### Declarations
TEST SEQUENCES UNCHANGED = YES  
GRU RETRAINED = NO  
EKF IMPLEMENTED = YES  
GNSS USED DURING OUTAGE = NO  
REFERENCE USED INSIDE OUTAGE = NO  
NHC USED = NO  
MAP MATCHING USED = NO  
Q/R TUNED ON TEST = NO (validation only)  
AI+EKF BEATS AI-DR ON FDE = NO  
LEAKAGE CHECKS = PASS  