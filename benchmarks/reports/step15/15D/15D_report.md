# STEP 15D Report — Authoritative Full 72-Case Held-Out Evaluation

## 1. Objective
Run the actual completed Step 15C AI+INS+EKF+active-NHC pipeline (frozen 12D GRU, frozen NHC_STD_MPS=1.0, frozen Q/R/P0 from Step 14) against the same authoritative 72-case GNSS-outage protocol used by 13C, on the four held-out TEST sequences. This is the first time the corrected active-NHC process model has been scored on data it was never validated or tuned against.

## 2. Frozen configuration
sig_AI=5.070742 m/s (12D GRU test RMSE) | NHC_STD_MPS=1.0 | R_NHC=1.0
Q_psd=[8.0, 8.0, 1.0, 1.0, 0.004873878716587337] | sig_gnss=5.0 | P0=[25.0, 25.0, 4.0, 4.0, 0.12184696791468343]

## 3. Test-set firewall
test_set_touched_for_training=False, retraining=False, tuning=False, parameter_search=False. Reference trajectory used only for post-hoc metric computation, never as an EKF measurement or parameter source.

## 4. 72-case protocol
Loaded from D:\SIH 2026\outputs\step14_ekf\final\outage_cases.csv, never regenerated. 72 cases across ['Vta08', 'Vta28', 'Vtb01', 'Vw02'], durations [10, 20, 30, 60, 90, 120].

## 5. Case accounting
Requested 216 (72 cases x 3 arms). Executed: 216. 72/72 per arm: True.

## 6. Step 14 baseline (comparison arm only, unmodified)
{'arm': 'step14_baseline', 'n_cases': 72.0, 'median_FDE_m': 229.93181093127095, 'mean_FDE_m': 408.66324134477964, 'median_drift_pct': 36.84125097011285, 'mean_drift_pct': 62.88795799489112, 'max_drift_pct': 351.8785245732148, 'median_abs_v_lateral_mps': 0.0, 'mean_abs_v_lateral_mps': 2.319213161062795e-16, 'max_abs_v_lateral_mps': 3.552713678800501e-15, 'mean_heading_error_deg': 31.370909311233632, 'final_heading_error_deg': 20.50153833080529, 'mean_ai_innovation_mps': nan, 'mean_nhc_innovation_mps': nan, 'failure_events_total': 0.0, 'unique_cases_with_failure': 0.0, 'sih_pass_count': 3.0, 'sih_pass_rate_pct': 4.166666666666666}

## 7. Step 15C methodology
See 15C_process_model_audit.md (unchanged) for the full derivation.

## 8. NHC-on/off ablation (aggregate)
            arm  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_heading_error_deg  final_heading_error_deg  mean_ai_innovation_mps  mean_nhc_innovation_mps  failure_events_total  unique_cases_with_failure  sih_pass_count  sih_pass_rate_pct
     15c_no_nhc     72.0    348.242754  884.144395         69.889222      120.149146     771.103516              2.476123e-01            5.791409e+00           5.294030e+01               34.598810                29.955068               -0.023490                      NaN                  97.0                       10.0             3.0           4.166667
   15c_with_nhc     72.0    250.873533  411.146596         36.429242       63.196075     349.940889              3.428413e-11            4.038956e-04           6.126844e-01               31.743429                21.293828               -0.088838                -0.000099                   0.0                        0.0             3.0           4.166667
step14_baseline     72.0    229.931811  408.663241         36.841251       62.887958     351.878525              0.000000e+00            2.319213e-16           3.552714e-15               31.370909                20.501538                     NaN                      NaN                   0.0                        0.0             3.0           4.166667

## 9. Aggregate results
            arm  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_heading_error_deg  final_heading_error_deg  mean_ai_innovation_mps  mean_nhc_innovation_mps  failure_events_total  unique_cases_with_failure  sih_pass_count  sih_pass_rate_pct
     15c_no_nhc     72.0    348.242754  884.144395         69.889222      120.149146     771.103516              2.476123e-01            5.791409e+00           5.294030e+01               34.598810                29.955068               -0.023490                      NaN                  97.0                       10.0             3.0           4.166667
   15c_with_nhc     72.0    250.873533  411.146596         36.429242       63.196075     349.940889              3.428413e-11            4.038956e-04           6.126844e-01               31.743429                21.293828               -0.088838                -0.000099                   0.0                        0.0             3.0           4.166667
step14_baseline     72.0    229.931811  408.663241         36.841251       62.887958     351.878525              0.000000e+00            2.319213e-16           3.552714e-15               31.370909                20.501538                     NaN                      NaN                   0.0                        0.0             3.0           4.166667

## 10. Duration-wise results
            arm  outage_duration_s  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_heading_error_deg  final_heading_error_deg  mean_ai_innovation_mps  mean_nhc_innovation_mps  failure_events_total  unique_cases_with_failure  sih_pass_count  sih_pass_rate_pct
     15c_no_nhc               10.0     12.0     51.720439   51.222489         30.523777       46.661512     131.633417              4.899505e-02            4.438692e-01           4.845682e+00               11.930012                 6.784822               -0.051887                      NaN                   0.0                        0.0             2.0          16.666667
     15c_no_nhc               20.0     12.0    100.213624  124.656308         30.747750       41.321970     108.854992              7.951435e-02            5.909528e-01           5.274631e+00               22.723620                11.348254               -0.083998                      NaN                   0.0                        0.0             1.0           8.333333
     15c_no_nhc               30.0     12.0    165.804015  218.592226         43.290771       63.528019     178.798731              7.478005e-02            1.119423e+00           1.284249e+01               29.497581                30.301949                0.001235                      NaN                   0.0                        0.0             0.0           0.000000
     15c_no_nhc               60.0     12.0    643.424541  674.782618         87.902068      136.855987     771.103516              1.463350e+00            4.421231e+00           2.640246e+01               44.320823                50.203509               -0.066400                      NaN                   0.0                        0.0             0.0           0.000000
     15c_no_nhc               90.0     12.0   1159.003349 1451.157347        112.295592      200.571954     724.195713              6.267613e+00            1.071327e+01           4.714261e+01               50.830820                50.035012                0.018547                      NaN                   7.0                        2.0             0.0           0.000000
     15c_no_nhc              120.0     12.0   2497.115077 2784.455384        209.814627      231.955436     450.693064              1.959431e+01            1.745971e+01           5.294030e+01               48.290004                48.078001                0.041566                      NaN                  90.0                        8.0             0.0           0.000000
   15c_with_nhc               10.0     12.0     49.153697   49.792887         29.820606       45.709788     129.533818              1.331370e-07            8.775408e-04           3.282133e-01               12.754820                10.810215               -0.064202                -0.004177                   0.0                        0.0             2.0          16.666667
   15c_with_nhc               20.0     12.0    100.563354  131.181123         30.439478       43.653530     109.049256              2.736964e-08            1.096648e-03           6.126844e-01               22.136078                11.195128               -0.106559                 0.003639                   0.0                        0.0             1.0           8.333333
   15c_with_nhc               30.0     12.0    153.122339  199.532689         37.126459       54.627878     134.873291              1.089612e-09            1.932862e-04           9.709681e-02               29.470873                29.073885               -0.065229                -0.000617                   0.0                        0.0             0.0           0.000000
   15c_with_nhc               60.0     12.0    494.522904  513.373525         58.444178       86.439419     349.940889              2.331468e-14            3.847475e-05           6.489341e-02               41.282630                52.243054               -0.179456                 0.000103                   0.0                        0.0             0.0           0.000000
   15c_with_nhc               90.0     12.0    413.740922  617.322041         31.933275       79.602411     256.975165              2.442491e-15            9.786050e-05           1.445371e-01               40.499151                22.571696               -0.062402                 0.000456                   0.0                        0.0             0.0           0.000000
   15c_with_nhc              120.0     12.0    791.905871  955.677312         61.176354       69.143422     164.786511              8.881784e-16            1.195638e-04           3.402011e-01               44.317025                47.070939               -0.055181                 0.000001                   0.0                        0.0             0.0           0.000000
step14_baseline               10.0     12.0     50.768198   49.181249         29.905837       45.192620     128.819862              0.000000e+00            2.469605e-16           1.776357e-15               12.158572                11.065721                     NaN                      NaN                   0.0                        0.0             2.0          16.666667
step14_baseline               20.0     12.0    107.227912  127.446444         30.436963       42.577432     108.698464              0.000000e+00            2.574525e-16           1.776357e-15               21.051165                12.854229                     NaN                      NaN                   0.0                        0.0             1.0           8.333333
step14_baseline               30.0     12.0    150.574232  199.497602         37.632066       54.892403     136.677829              0.000000e+00            2.454931e-16           1.776357e-15               29.268584                27.919306                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline               60.0     12.0    494.063431  513.777828         58.138779       86.607079     351.878525              0.000000e+00            2.186752e-16           1.776357e-15               41.353595                52.170917                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline               90.0     12.0    428.661080  623.210232         32.681954       80.138251     258.021498              0.000000e+00            2.118314e-16           1.776357e-15               40.829375                23.501082                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline              120.0     12.0    792.895394  938.866094         60.800532       67.919962     169.328352              0.000000e+00            2.111151e-16           3.552714e-15               43.564165                40.789328                     NaN                      NaN                   0.0                        0.0             0.0           0.000000

## 11. Sequence-wise results
            arm sequence_id  n_cases  median_FDE_m  mean_FDE_m  median_drift_pct  mean_drift_pct  max_drift_pct  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps  mean_heading_error_deg  final_heading_error_deg  mean_ai_innovation_mps  mean_nhc_innovation_mps  failure_events_total  unique_cases_with_failure  sih_pass_count  sih_pass_rate_pct
     15c_no_nhc       Vta08     18.0    415.774730  745.578903         79.782599       88.797301     269.935361              1.604206e-01            5.187966e+00           4.617484e+01               32.216388                33.519892                0.100009                      NaN                  12.0                        3.0             0.0           0.000000
     15c_no_nhc       Vta28     18.0    397.136421 1173.557749        125.613678      228.870995     771.103516              1.271833e+00            8.558527e+00           4.749323e+01               56.093799                50.101243                0.204427                      NaN                  12.0                        3.0             0.0           0.000000
     15c_no_nhc       Vtb01     18.0    409.756944  778.636476         60.409775       87.962416     445.924054              2.012611e-01            3.429924e+00           5.294030e+01               33.790327                27.601300               -0.161714                      NaN                  21.0                        2.0             0.0           0.000000
     15c_no_nhc        Vw02     18.0    310.519243  838.804453         33.162461       74.965874     450.693064              2.111772e-01            5.989219e+00           4.823599e+01               16.294726                 3.619324               -0.236681                      NaN                  52.0                        2.0             3.0          16.666667
   15c_with_nhc       Vta08     18.0    244.359207  415.104285         41.508051       57.068077     112.156961              5.286738e-10            2.927463e-04           3.810534e-01               28.768712                13.027507                0.002730                 0.000866                   0.0                        0.0             0.0           0.000000
   15c_with_nhc       Vta28     18.0    324.715453  479.141708         92.661081      110.437964     349.940889              1.113370e-09            6.725182e-04           6.126844e-01               49.404185                45.876453                0.144606                 0.001419                   0.0                        0.0             0.0           0.000000
   15c_with_nhc       Vtb01     18.0    212.684707  384.222880         33.944570       48.963628     143.901592              1.258500e-10            1.449035e-04           3.742954e-02               32.644439                30.229496               -0.194846                 0.000113                   0.0                        0.0             0.0           0.000000
   15c_with_nhc        Vw02     18.0    235.093236  366.117512         21.278968       36.314630     164.786511              3.421441e-11            5.054146e-04           3.402011e-01               16.156382                 8.194802               -0.307843                -0.002795                   0.0                        0.0             3.0          16.666667
step14_baseline       Vta08     18.0    223.285981  411.948805         41.795986       55.845329     111.630948              0.000000e+00            1.513818e-16           1.776357e-15               27.909704                13.052257                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline       Vta28     18.0    309.688514  464.496158         85.897255      109.603462     351.878525              0.000000e+00            1.858256e-16           1.776357e-15               48.495186                42.312172                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline       Vtb01     18.0    212.820662  385.585864         33.220065       49.125408     144.591638              0.000000e+00            2.074133e-16           1.776357e-15               32.663931                29.555453                     NaN                      NaN                   0.0                        0.0             0.0           0.000000
step14_baseline        Vw02     18.0    236.328023  372.622139         21.783337       36.977633     169.328352              0.000000e+00            3.830645e-16           3.552714e-15               16.414815                 7.891838                     NaN                      NaN                   0.0                        0.0             3.0          16.666667

## 12. SIH <10% drift analysis
            arm  n_cases  pass_count  pass_rate_pct
step14_baseline       72           3       4.166667
     15c_no_nhc       72           3       4.166667
   15c_with_nhc       72           3       4.166667

## 13. Heading analysis
mean_heading_error_deg -- Step14=31.37 | 15C-noNHC=34.60 | 15C-withNHC=31.74

## 14. Lateral-velocity analysis
mean_abs_v_lateral_mps -- Step14=0.0000 | 15C-noNHC=5.7914 | 15C-withNHC=0.0004

## 15. Numerical stability
            arm  total_failure_events  unique_cases_with_failure  n_cases
step14_baseline                     0                          0       72
     15c_no_nhc                    97                         10       72
   15c_with_nhc                     0                          0       72

## 16. Paired comparison
Step14 vs 15C(withNHC): 15C wins 42/72 (58.3%), median delta_FDE=0.856 m (positive = 15C better)
15C(noNHC) vs 15C(withNHC): withNHC wins 49/72 (68.1%), median delta_FDE=5.111 m

## 17. Representative trajectories
           role  outage_duration_s sequence_id  outage_start  delta_FDE_m
   short_outage               10.0         NaN           NaN          NaN
  medium_outage               60.0         NaN           NaN          NaN
    long_outage              120.0         NaN           NaN          NaN
 nhc_helps_most              120.0        Vw02       45621.0  3419.109278
nhc_helps_least               90.0       Vtb01       11081.0  -237.833061

## 18. Limitations
- sig_AI reuses the GRU's aggregate test RMSE as a per-step measurement noise (documented simplification, inherited unchanged from 15C).
- Constant-velocity process model relies on measurement updates (AI, NHC, GNSS) to correct velocity rather than physics-based propagation (documented in 15C_process_model_audit.md).
- This is a held-out TEST evaluation, not the final SIH system benchmark: no map matching, ZUPT, GNSS health/state-machine, or Android deployment.
- No parameter in this notebook was selected using this test-set run's results.

## 19. Honest conclusion
NHC is mathematically/physically active on the held-out test set: YES (mean NHC innovation = -0.0001 m/s, mean|v_lateral| collapses from 5.7914 to 0.0004 m/s when NHC is turned on).
NHC improves held-out navigation accuracy (median FDE): NO (250.87 m with NHC vs 229.93 m Step-14 baseline). These are DIFFERENT CLAIMS and must not be conflated.
SIH <10% drift pass rate (15C withNHC, held-out test): 4.17% (3/72). This is NOT a claim that the SIH benchmark is met.