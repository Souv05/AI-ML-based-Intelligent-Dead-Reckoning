# STEP 16E Report — Phase-16 Winner Frozen

## Selection
- Selected: 16A GRU v2 (test RMSE=4.4016 m/s, among 3 live candidate(s)).
- Significance vs other tested model(s): CONFIRMED (p<0.05 against at least one).
- Low-speed-regime severe-collapse flag: True.

## Frozen reference
```json
{
  "model_name": "16A GRU v2",
  "source_step": "16A",
  "model_class": "GRURegressor (2-layer causal GRU, last-hidden-state -> Linear(128,1); no attention pooling -- see 16A's own model-definition cell / models/step16a_gru_v2.py)",
  "model_kwargs": {
    "hidden_size": 128,
    "num_layers": 2,
    "dropout": 0.2,
    "input_size": 12
  },
  "state_dict_path": "outputs/step16e/final/gru_v2_best.pt",
  "window_length": 60
}
```

## Consumer note
Downstream notebooks (17A+) must import `GRURegressor (2-layer causal GRU, last-hidden-state -> Linear(128,1); no attention pooling -- see 16A's own model-definition cell / models/step16a_gru_v2.py)` from 16A's own notebook — this file does not redefine that class, only points to its frozen weights and hyperparameters.

## Caveats carried forward
- significance_verified: True
- low_speed_regime_flag: True
- Both caveats are informational, not blocking -- Phase 16 has to conclude with a concrete choice; 17A and later steps should read authoritative_status.json before treating this freeze as beyond question.