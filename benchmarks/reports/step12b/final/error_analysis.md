# Step 12B-F error analysis

- Mean residual (y_true - y_pred, bias): 3.2891 m/s
- Low-speed (bottom tercile) MAE: 2.7721102237701416
- High-speed (top tercile) MAE: 9.084100723266602
- GNSS-blackout-window MAE: 5.237030982971191
- GNSS-available-window MAE: 5.159870147705078
- Highest-RMSE test sequence: `Vw02`
- Lowest-RMSE test sequence: `Vta08`

Only stationary/acceleration/braking/turning scenario labels would require metadata not
present in the current window-level dataset, so they are not reported here (not invented).
