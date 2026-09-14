# SIH 2026 — ISRO Intelligent Dead Reckoning (PS 26168)

Two things live here:

1. **`src/data/` + `scripts/prepare_dataset.py`** — the IO-VNBD **data-preparation
   pipeline** (inventory → verify sync → canonical schema → ENU reference →
   GNSS-blackout mask → temporal windows → sequence-wise split → leakage check →
   `data/processed/`). Produces a model-ready dataset. **No training.** See
   [`DATA_PREP_REPORT.md`](DATA_PREP_REPORT.md) and `artifacts/`.
2. **`src/iovnbd/` + `scripts/01-03`** — EDA/catalog and a synthetic
   GNSS-blackout **drift benchmark** with a baseline non-holonomic
   dead-reckoning engine, scored against ISRO's "< 10 % of distance" target.
   See [`outputs/FINDINGS.md`](outputs/FINDINGS.md).

---

## Data-prep pipeline (`src/data/`)

```bash
python -m pytest -q tests/test_data_pipeline.py     # 13 checks
python scripts/prepare_dataset.py                   # ~80 s; --quick for a subset
```

| module | stage |
|---|---|
| `config.py` | every tunable (feature list, window, blackout, split) |
| `inventory.py` | scan all 564 CSVs (cached) |
| `loader.py` | raw + canonical frames, fail-loud on missing columns |
| `synchronization.py` | discover + verify S/V pairs (smoothed speed corr @ lag 0) |
| `coordinates.py` | lat/lon → local ENU metres |
| `preprocessing.py` | aligned per-sequence timeline, drive-group split |
| `blackout.py` | `native_gnss_valid` + engineered outage mask (inputs only) |
| `windowing.py` | sliding windows, configurable target, gap-aware |
| `validation.py` | quality flags + train/test leakage checks |
| `plots.py` | 7 sensor figures for one drive |

Outputs: `artifacts/*` (12 docs + `plots/`), `data/interim/*.parquet`,
`data/processed/{train,validation,test}/<seq>.parquet` + `<seq>_windows.npz`,
`data/processed/manifest.csv`. Raw data under `dataset/IO-VNBD/` is never modified.

---

## Drift-benchmark toolkit (`src/iovnbd/`)

Robust loading, EDA, synthetic GNSS-blackout generation, a baseline
non-holonomic dead-reckoning engine, and a drift benchmark scored against ISRO's
"< 10 % of distance travelled" target.

## Layout

```
dataset/IO-VNBD/            real data (git lfs pull from github.com/onyekpeu/IO-VNBD)
dataset/IO-VNBD-master/     original pointer-stub extraction (kept as fallback)
src/iovnbd/
  paths.py       dataset root + trip discovery
  schema.py      raw header -> canonical column mapping (token-based, 2 phone layouts)
  loader.py      PhoneLog / VehicleLog / Trip  (canonical units, common clock, ENU truth)
  geo.py         lat/lon <-> local ENU, haversine, angle helpers
  eda.py         per-trip summary, quality flags, IMU-coupling + truth-consistency metrics
  align.py       phone -> vehicle orientation estimate (ISRO "orientation detection")
  blackout.py    synthetic GNSS-outage windows + scenario presets
  deadreckon.py  NHC dead-reckoning; pluggable speed_source / heading_source
  metrics.py     drift metrics + ISRO pass/fail + aggregation
  plots.py       matplotlib figures (headless)
  harness.py     trips x scenarios x sources evaluation loop
scripts/
  01_build_catalog.py        -> outputs/catalog.csv, catalog_brief.md
  02_eda_report.py           -> outputs/eda/*.png, summary.txt
  03_run_drift_benchmark.py  -> outputs/benchmark/{detail,summary}.csv|md, *.png
outputs/FINDINGS.md          consolidated results write-up
```

## Setup

```bash
python -m pip install -r requirements.txt
# dataset (once): from dataset/  ->
#   $env:GIT_LFS_SKIP_SMUDGE=1; git clone https://github.com/onyekpeu/IO-VNBD.git IO-VNBD
#   git -C IO-VNBD lfs pull --include="*.csv,*.JPG"
```

Point elsewhere with `IOVNBD_ROOT=/path/to/IO-VNBD`.

## Canonical signals

`Trip.phone.df` : `t, lat, lon, alt_m, gps_speed_ms, gps_acc_m, gps_course_deg,
gps_sats, acc_{x,y,z}, grav_{x,y,z}, gyro_{x,y,z}, mag_{x,y,z},
ori_{yaw,pitch,roll}`

`Trip.vehicle.df` : `t, lat, lon, vel_kmh, heading_deg, height_m, dt_s,
steer_deg, ws_{fl,fr,rl,rr}, yaw_rate_dps, ind_speed_kmh, acc_long_g,
acc_lat_g, engine_rpm, brake_psi, …`

`Trip` also carries row-aligned `east_m, north_m, dist_m` (ENU truth, origin =
first vehicle fix) and a common `t` (s from 0).

## Dead-reckoning sources

speed  : `truth | hold | gps_decay | imu_integrate | obd | wheel_speed` or a
`callable(trip, slice, ctx) -> np.ndarray[m/s]`
heading: `truth | gps_hold | gyro | imu_aligned | veh_yawrate` or a callable.

An ML speed/heading model is dropped in as the callable — see
`outputs/FINDINGS.md` §5.

See `outputs/FINDINGS.md` for dataset quirks and baseline results.
