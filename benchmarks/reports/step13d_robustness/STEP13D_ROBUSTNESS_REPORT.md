# STEP 13D - SIH DRIFT + ROBUSTNESS ANALYSIS

## 1. Objective
Statistical and robustness analysis of the Step 13C full test-set comparison (Classical DR vs frozen 12D-GRU AI-DR). No re-simulation, no retraining, no EKF / sensor fusion - those begin at Step 14.

## 2. Source
Frozen outputs of `outputs/step13c_full/` (72 paired outage cases, 4 test sequences: Vta08, Vta28, Vtb01, Vw02, durations [10, 20, 30, 60, 90, 120]s).

## 3. Statistical significance (Wilcoxon signed-rank on paired FDE)
```
outage_duration_s  n  n_nonzero  statistic  p_value  median_diff_m        direction  significant_at_0.05
              ALL 72         72     1223.0 0.609586      -0.377961 Classical better                False
             10.0 12         12       18.0 0.109863     -18.646918 Classical better                False
             20.0 12         12       35.0 0.791016       6.730457        AI better                False
             30.0 12         12       33.0 0.677246      21.728308        AI better                False
             60.0 12         12       37.0 0.909668     -17.989801 Classical better                False
             90.0 12         12       31.0 0.569336     -33.097484 Classical better                False
            120.0 12         12       22.0 0.203613     376.469507        AI better                False
```
Overall: p=0.6096

## 4. Bootstrap confidence intervals (case resampling, n=10000)
```
{
  "n_bootstrap": 10000,
  "n_paired_cases": 72,
  "ai_win_rate_point_pct": 50.0,
  "ai_win_rate_95ci_pct": [
    38.88888888888889,
    61.111111111111114
  ],
  "median_fde_gap_point_m": -0.3779612046740217,
  "median_fde_gap_95ci_m": [
    -31.638608935989545,
    39.09297740899977
  ],
  "ci_excludes_50pct_win_rate": false,
  "ci_excludes_zero_median_gap": false
}
```

## 5. Robustness across sequences
```
sequence_id  n_paired_cases  median_classical_FDE_m  median_ai_FDE_m  median_classical_drift_pct  median_ai_drift_pct  classical_sih_pass_rate_pct  ai_sih_pass_rate_pct  ai_win_rate_pct
      Vta08              18              227.294753       246.355302                   46.593277            32.721251                     0.000000              0.000000        55.555556
      Vta28              18              365.575705       309.694623                   71.132637            59.421066                     0.000000              0.000000        55.555556
      Vtb01              18              375.387490       226.273129                   65.675291            47.800367                     5.555556              0.000000        55.555556
       Vw02              18              190.239187       217.187678                   17.010742            23.075662                    38.888889             11.111111        33.333333
```
AI-DR win-rate range across sequences: 22.2 percentage points.

## 6. Drift growth rate vs outage duration
```
      method  drift_pct_per_second  drift_intercept_pct  drift_fit_r2  fde_loglog_slope  fde_loglog_r2              growth_regime
Classical_DR              0.501330            38.796313      0.073780          1.459955       0.739983 super-linear (compounding)
   AI_DR_GRU              0.419776            38.655195      0.075627          1.277692       0.703732 super-linear (compounding)
```

## 7. Drift vs distance travelled (speed proxy)
```
      method  spearman_rho_drift_vs_distance  p_value                        interpretation
Classical_DR                        0.091678 0.443728 no significant monotonic relationship
   AI_DR_GRU                        0.152132 0.202051 no significant monotonic relationship
```

## 8. Failure-mode taxonomy (SIH 10% threshold, both methods jointly)
```
             bucket  n_cases  pct_of_cases
          both_fail       64     88.888889
classical_only_pass        6      8.333333
          both_pass        2      2.777778
```
88.9% of cases fail under BOTH methods - a velocity-source swap alone cannot fix these; heading error and/or fusion is required.

## 9. Robustness verdict
- The paired FDE difference is NOT statistically significant overall at alpha=0.05 - the 13C win/loss split is consistent with noise.
- The 95% bootstrap CI on AI-DR win rate INCLUDES 50% - the reported win rate is not distinguishable from a coin flip at this sample size.
- Neither method is robust to the SIH <10% drift target: 88.9% of cases fail under both methods, and per-run SIH pass rates in 13C were 11.1% (Classical) and 2.8% (AI-DR) - far below a usable pass rate.

## 10. Limitations
- Analysis is entirely derived from the 72 paired cases 13C sampled (<=3 starts per sequence/duration cell); it is not a re-sweep of every possible outage start.
- Robustness here means statistical/behavioural robustness of the two raw DR methods, not robustness of a deployed system - no fusion, filtering, or NHC is applied.
- Spearman correlation with distance is a speed *proxy*, not a direct speed-binned analysis.

## 11. Next step
STEP 14 - EKF / sensor fusion (classical DR + AI-DR forward-speed + NHC pseudo-measurements), motivated directly by Section 8 above: raw velocity-source swaps do not reach the SIH <10% drift target and a large share of cases fail under both methods.

---
### Declarations
13C RESULTS AUTHORITATIVE = YES  
RE-SIMULATION PERFORMED = NO  
GRU RETRAINED = NO  
EKF / FUSION USED = NO  
GNSS USED DURING OUTAGE = NO  
EKF AUDIT = CLEAN  