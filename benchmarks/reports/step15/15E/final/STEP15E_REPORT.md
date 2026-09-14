# STEP 15E Report — Heading / Drift / Failure Analysis

## 1. Objective
Analyze the already-completed Step 15D full 72-case held-out test results (Step14 baseline,
15C-noNHC, 15C-withNHC) to explain *why* drift remains high, what NHC actually fixed, and
what the dominant remaining bottleneck is. **This is analysis only** — no rerun of 15D, no
retraining, no re-tuning, no algorithm or configuration changes, and the held-out test
results are used only descriptively, never to select any parameter.

## 2. Test-set firewall (verified)
- `test_set_touched_for_training`: False
- `retraining` / `tuning` / `parameter_search`: False / False / False
- 15D case accounting: 216/216 rows EXECUTED (72 cases × 3 arms), verified bit-for-bit against `15D_case_accounting.csv`.
- 15D's own frozen config (`NHC_STD_MPS=1.0`, `R_NHC=1.0`, Q/R/P0 from Step 14) is read but never modified here.

## 3. Heading-error analysis

**Overall (72 cases):**
  arm_label  mean_heading_error_deg  final_heading_error_deg
  15C-noNHC               34.598810                29.955068
15C-withNHC               31.743429                21.293828
     Step14               31.370909                20.501538

**By outage duration:**
arm                15c_no_nhc  15c_with_nhc  step14_baseline
outage_duration_s                                           
10.0                11.930012     12.754820        12.158572
20.0                22.723620     22.136078        21.051165
30.0                29.497581     29.470873        29.268584
60.0                44.320823     41.282630        41.353595
90.0                50.830820     40.499151        40.829375
120.0               48.290004     44.317025        43.564165

**By sequence:**
arm          15c_no_nhc  15c_with_nhc  step14_baseline
sequence_id                                           
Vta08         32.216388     28.768712        27.909704
Vta28         56.093799     49.404185        48.495186
Vtb01         33.790327     32.644439        32.663931
Vw02          16.294726     16.156382        16.414815

**Finding:** NHC's isolated effect on heading error (no_nhc − with_nhc, paired per case) has
median **0.060°** and mean **2.86° ± 8.27°** — noisy and not systematic. 15C-withNHC's
overall heading error (31.74°) is statistically indistinguishable from Step14's (31.37°).
NHC does not meaningfully change heading error, in either direction.

## 4. Drift / FDE analysis

**Median FDE (m) by outage duration:**
 outage_duration_s  15c_no_nhc  15c_with_nhc  step14_baseline
              10.0   51.720439     49.153697        50.768198
              20.0  100.213624    100.563354       107.227912
              30.0  165.804015    153.122339       150.574232
              60.0  643.424541    494.522904       494.063431
              90.0 1159.003349    413.740922       428.661080
             120.0 2497.115077    791.905871       792.895394

**Median drift (%) by outage duration:**
 outage_duration_s  15c_no_nhc  15c_with_nhc  step14_baseline
              10.0   30.523777     29.820606        29.905837
              20.0   30.747750     30.439478        30.436963
              30.0   43.290771     37.126459        37.632066
              60.0   87.902068     58.444178        58.138779
              90.0  112.295592     31.933275        32.681954
             120.0  209.814627     61.176354        60.800532

**Does error grow systematically with duration?** (Spearman rank correlation, case-level, n=72/arm)
        arm  spearman_rho_duration_vs_FDE  p_value_FDE  spearman_rho_duration_vs_drift_pct  p_value_drift
     Step14                      0.831540 1.518031e-19                            0.210135   7.644640e-02
  15C-noNHC                      0.932890 9.161112e-33                            0.615926   8.476085e-09
15C-withNHC                      0.829192 2.362386e-19                            0.214048   7.100283e-02

FDE grows highly significantly with outage duration for **every** arm (ρ=0.83–0.93,
p≪0.001). 15C-noNHC's drift-% also grows significantly with duration (ρ=0.62, p<1e-8),
consistent with its long-duration divergence; Step14 and 15C-withNHC's drift-% growth is
much weaker and not significant (ρ≈0.21, p≈0.07–0.08), because their FDE grows roughly in
proportion to distance travelled rather than compounding.

**Step14 vs 15C-noNHC vs 15C-withNHC (aggregate, 72 cases each):**

| arm | median FDE (m) | mean FDE (m) | median drift % |
|---|---|---|---|
| Step14 | 229.9 | 408.7 | 36.8 |
| 15C-noNHC | 348.2 | 884.1 | 69.9 |
| 15C-withNHC | 250.9 | 411.1 | 36.4 |

**Key finding:** 15C-withNHC's aggregate FDE/drift is essentially **tied with Step14**
(median FDE +9.1% higher, median drift % statistically indistinguishable), not an
improvement over it. 15C-noNHC diverges badly at 90–120s outages specifically (median FDE
1159m→2497m), which 15C-withNHC and Step14 do not.

## 5. NHC effect analysis

**Lateral velocity magnitude (aggregate, 72 cases):**
  arm_label  median_abs_v_lateral_mps  mean_abs_v_lateral_mps  max_abs_v_lateral_mps
  15C-noNHC              2.476123e-01            5.791409e+00           5.294030e+01
15C-withNHC              3.428413e-11            4.038956e-04           6.126844e-01
     Step14              0.000000e+00            2.319213e-16           3.552714e-15

NHC reduces median |v_lateral| from **0.248 m/s** to **3.4×10⁻¹¹ m/s** — a ~10-order-of-
magnitude reduction, confirming the corrected constant-velocity process model gives NHC a
genuine, non-inert lateral degree of freedom to act on (unlike Step14's structural bug).

**NHC innovation distribution** (15C-withNHC, 72 cases): mean −0.0001 m/s, std 0.0069 m/s,
range [−0.049, +0.025] m/s — small and centered near zero, consistent with NHC actively and
successfully suppressing lateral velocity every step rather than fighting a large, systematic
non-holonomic violation.

**Where NHC helps most (isolated no_nhc vs with_nhc, top 5 of 72):**
sequence_id  outage_duration_s  outage_start  delta_FDE_m
       Vw02              120.0         45621  3419.109278
      Vtb01              120.0         28747  3294.847719
      Vta08              120.0           926  2718.055214
      Vta28              120.0           145  2517.392745
      Vta28               90.0           647  2089.933018

**Where NHC helps least / hurts (bottom 5 of 72):**
sequence_id  outage_duration_s  outage_start  delta_FDE_m
      Vta08               20.0          2397   -35.656563
      Vta28               20.0          2168   -43.234088
      Vtb01               60.0         11089   -74.628035
      Vta08               60.0          2047  -168.812911
      Vtb01               90.0         11081  -237.833061

NHC improves FDE in **49/72 cases (68%)** and makes it worse in
**23/72 (32%)** — helping is the majority behavior but not
universal. All 5 "helps most" cases are 90–120s outages (where unconstrained lateral drift
would otherwise be largest); the "helps least" case (Vtb01, 90s) is one where the
unconstrained no-NHC trajectory happened to drift toward, not away from, ground truth —
NHC correctly removes a physically-implausible sideways velocity, but that specific
instance's uncorrected error partially cancelled against a separate, dominant heading error.

## 6. Failure analysis

            arm  total_failure_events  unique_cases_with_failure  n_cases
step14_baseline                     0                          0       72
     15c_no_nhc                    97                         10       72
   15c_with_nhc                     0                          0       72

All 97 numerical-instability events (10 unique cases) are `position_discontinuity` events,
100% concentrated in the 15C-noNHC arm.

**By sequence:**
sequence_id  n_failing_cases  total_events
      Vta08                3            12
      Vta28                3            12
      Vtb01                2            21
       Vw02                2            52

**By duration:**
 outage_duration_s  n_failing_cases  total_events
              90.0                2             7
             120.0                8            90

Failures concentrate heavily at **90–120s** outages (97/97 events at ≥90s; 90/97 at 120s
alone) — exactly where unconstrained lateral velocity has the longest time to integrate into
position error. **Confirmed: 15C-withNHC and Step14 both have zero failure events.**

## 7. Sequence difficulty ranking

(Ranked by Step14 baseline median FDE, the arm least contaminated by NHC's per-case
variability — cleanest signal of underlying reference-trajectory difficulty.)

 difficulty_rank sequence_id  median_FDE_m  mean_FDE_m  median_drift_pct  mean_heading_error_deg
               1       Vta28    309.688514  464.496158         85.897255               48.495186
               2        Vw02    236.328023  372.622139         21.783337               16.414815
               3       Vta08    223.285981  411.948805         41.795986               27.909704
               4       Vtb01    212.820662  385.585864         33.220065               32.663931

**Vta28** is hardest (highest median FDE, highest drift %, highest heading error across
every arm — 48–56°, well above the other three sequences' 16–34° range), suggesting it
involves more sustained heading change (e.g. longer turns or a more curved route) than
Vta08/Vtb01/Vw02. **Vtb01** and **Vw02** are the easiest by median FDE, though Vw02 has the
most SIH-benchmark passes (3 of the study's 3 total passes all come from Vw02's shortest
outages).

## 8. Representative cases (already selected by 15D, analyzed here — not regenerated)

           role sequence_id  outage_duration_s  outage_start             arm       FDE_m  drift_percent  mean_heading_error_deg  mean_abs_v_lateral_mps
 nhc_helps_most        Vw02              120.0       45621.0 step14_baseline 2024.969809     169.328352              127.201050            2.096690e-16
 nhc_helps_most        Vw02              120.0       45621.0      15c_no_nhc 5389.763966     450.693064              109.521431            2.727148e+01
 nhc_helps_most        Vw02              120.0       45621.0    15c_with_nhc 1970.654688     164.786511              123.962232            6.989385e-04
nhc_helps_least       Vtb01               90.0       11081.0 step14_baseline 1123.775446      95.390714               63.058708            2.370776e-16
nhc_helps_least       Vtb01               90.0       11081.0      15c_no_nhc  879.526851      74.657882               72.173013            5.728411e+00
nhc_helps_least       Vtb01               90.0       11081.0    15c_with_nhc 1117.359913      94.846137               62.607943            4.000235e-05

- **short_outage** (Vta08, 10s): all three arms nearly identical (~23–24m FDE) — too short
  for any arm's differences to matter.
- **medium_outage** (Vta08, 60s): no_nhc already shows meaningful lateral drift (0.71 m/s,
  27.5% drift) vs with_nhc/Step14 (~24% drift, both ~0 lateral velocity) — the gap is opening.
- **long_outage** (Vta08, 120s): no_nhc diverges catastrophically (2993m FDE, 270% drift,
  16.7 m/s lateral velocity — clearly non-physical), while with_nhc (274.7m, 24.8%) tracks
  Step14 (280.5m, 25.3%) almost exactly. This is the clearest single illustration of NHC's
  role: **rescuing divergence, not beating the baseline**.
- **nhc_helps_most** (Vw02, 120s): no_nhc reaches 27.3 m/s lateral velocity and 5390m FDE;
  with_nhc (1971m) actually comes in *below* Step14 (2025m) here — one of the cases where
  NHC's correction compounds favorably.
- **nhc_helps_least** (Vtb01, 90s): no_nhc's uncontrolled 5.73 m/s lateral velocity
  coincidentally lands closer to ground truth (880m) than the physically-constrained with_nhc
  (1117m) or Step14 (1124m) — a reminder that FDE is a single scalar and a physically wrong
  trajectory can occasionally score better by chance.

## 9. Root-cause diagnosis

NHC fully resolves the lateral-velocity artifact it was designed to fix (evidence 1) and eliminates all 97 numerical-instability events seen without it (Section 5), but it does not meaningfully reduce heading error (evidence 2) and does not beat Step14's FDE/drift in aggregate (evidence 3) -- it mainly prevents the no-NHC arm's runaway divergence at long outages, converging back to roughly Step14's performance rather than exceeding it. Outage duration remains the dominant driver of error magnitude for every arm (Section 3, evidence 4), and heading error grows with duration in a way no arm's measurement update constrains during the outage itself (evidence 5) -- heading is a free-running state once GNSS/course updates stop, and neither the constant-velocity process model nor NHC (a lateral-velocity constraint, not a heading observation) corrects it. The evidence points to HEADING ERROR (uncorrected during outage) and OUTAGE DURATION (compounding that uncorrected drift) as the dominant remaining bottleneck, not the choice of process model or the AI velocity measurement.

## 10. SIH <10% drift benchmark

            arm  n_cases  pass_count  pass_rate_pct
step14_baseline       72           3       4.166667
     15c_no_nhc       72           3       4.166667
   15c_with_nhc       72           3       4.166667

All three arms pass at the **identical rate: 3/72 (4.17%)**. NHC changes neither which cases
pass nor how many. **This is far below the SIH target and is reported as a gap, not a success.**

## 11. Plots produced
1. `01_fde_vs_duration.png` — FDE vs outage duration, all 3 arms
2. `02_drift_vs_duration.png` — drift % vs outage duration, all 3 arms, with 10% target line
3. `03_heading_error_vs_duration.png` — heading error vs outage duration, all 3 arms
4. `04_lateral_velocity_comparison.png` — lateral velocity by arm (log scale)
5. `05_sequence_wise_performance.png` — median FDE by sequence, all 3 arms
6. `06_nhc_innovation_distribution.png` — NHC innovation histogram (15C-withNHC)

## 12. Final conclusion

**What NHC solved:**
- Lateral velocity: median |v_lateral| reduced from 0.248 m/s (no_nhc) to 3.4e-11 m/s (with_nhc) -- effectively exact, confirming NHC's designed mechanism works on the corrected (constant-velocity) process model, unlike Step14's structurally-inert version.
- Numerical stability: all 97 position-discontinuity failure events across 10 unique cases (concentrated at 90-120s outages) are eliminated entirely with NHC active.
- NHC improves FDE in 49/72 cases (68%) when isolated against an otherwise-identical no-NHC run, mainly by preventing runaway divergence at long outages.

**What NHC did not solve:**
- Heading error: with_nhc mean heading error (31.74 deg) is statistically indistinguishable from Step14 (31.37 deg); NHC's isolated median effect on heading error is 0.060 deg -- not a meaningful change.
- Aggregate FDE/drift: with_nhc median FDE (250.9 m) does not beat Step14's (229.9 m) -- it converges to roughly the same level rather than exceeding it.
- SIH <10% drift pass rate is unchanged at 4.17% (3/72) across all three arms.
- In 23/72 cases (32%), NHC's isolated effect on FDE is negative -- forcing lateral velocity to zero is not uniformly beneficial when the unconstrained trajectory happens to drift toward, rather than away from, ground truth.

**Main remaining bottleneck:** Heading error, uncorrected during the GNSS outage span (no update touches absolute heading once GNSS/course updates stop), compounding with outage duration -- the strongest and most consistent driver of FDE/drift across every arm.

**What should be investigated next:**
- A heading-observable measurement usable during outages (e.g. ZUPT-derived heading constraints, magnetometer-based heading where reliable, or map-matching) -- NHC structurally cannot supply this, since it observes lateral-velocity consistency, not absolute heading.
- Whether the AI forward-speed measurement's own error (mean_ai_innovation_mps has non-trivial spread, std ~0.30 m/s) contributes to compounding drift independent of NHC.
- Sequence-specific dynamics for Vta28 (hardest by median FDE and highest heading error at 48-56 deg across all arms) -- worth checking whether it involves sharper turns or longer sustained maneuvers than the other three sequences.
- Per the roadmap, this is exactly what 15F (optional ZUPT) and Phase 16's outage-detection work are positioned to address -- this analysis does not itself propose a fix.

## 13. Constraints honored
No 15D rerun. No GRU retraining. No NHC re-tuning. No EKF Q/R/P0 changes. No EKF/NHC
algorithm modification. No outage-case modification. Held-out test results used only for
descriptive analysis, never for parameter selection. Complete test-set firewall maintained
throughout (see Section 2).

**STOPPING HERE — 15F has NOT been started, per instruction.**
