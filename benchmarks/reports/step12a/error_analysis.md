# Step 12A error analysis

1. **Where does the model perform well?** Lowest-RMSE test sequence: `Vta08`.
2. **Where does it perform poorly?** Highest-RMSE test sequence: `Vw02`.
3. **Systematic overprediction?** Mean residual (y_true - y_pred) = 4.8525 m/s
   (under-prediction on average if nonzero).
4. **Systematic underprediction?** See above; a positive bias indicates underprediction.
5. **Highest-RMSE test sequence:** `Vw02`.
6. **Lowest-RMSE test sequence:** `Vta08`.
7. **Improvement over Baseline 0 (test RMSE):** 3.77% if improvement_pct is not None else "N/A"

Low-speed (bottom tercile of y_test) MAE: 2.7125369192238558
High-speed (top tercile of y_test) MAE: 12.234640703641713

Only scenarios directly computable from available window-level metadata are reported here;
no turning/braking/vibration scenario labels are invented (none are present in the current
window metadata).
