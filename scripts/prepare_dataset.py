"""IO-VNBD preprocessing pipeline  (SIH 2026 / PS 26168) - DATA PREP ONLY.

Runs every stage in order and writes the deliverables under artifacts/ and data/.
NO MODEL IS TRAINED.

    python scripts/prepare_dataset.py [--quick] [--no-inventory]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

from data.config import DEFAULT_CONFIG, INPUT_FEATURES                       # noqa: E402
from data.inventory import build_inventory                                  # noqa: E402
from data.synchronization import (discover_pairs, pairs_to_df,              # noqa: E402
                                  select_first_verified)
from data.preprocessing import (assign_splits, build_sequence,             # noqa: E402
                                sequence_stats)
from data.blackout import make_windows as make_blackout_windows, apply_mask  # noqa: E402
from data.windowing import make_windows as make_temporal_windows, measure_hz  # noqa: E402
from data.validation import quality_report, leakage_checks                   # noqa: E402
from data import plots as dplots                                            # noqa: E402

CFG = DEFAULT_CONFIG
A = CFG.artifacts


# semantic roles for the data dictionary (known IO-VNBD columns; else UNKNOWN)
_ROLE = {
    "phone": {
        "GPS LATITUDE": ("deg", "gnss_input_reference"), "GPS LONGITUDE": ("deg", "gnss_input_reference"),
        "GPS ALTITUDE": ("m", "gnss_aux"), "GPS SPEED": ("m/s (label says Kmh)", "gnss_derived_speed"),
        "GPS ACCURACY": ("m", "gnss_quality"), "GPS ORIENTATION": ("deg", "gnss_course"),
        "GPS SATELLITES": ("count", "gnss_quality"), "TIME SINCE START": ("ms", "clock_unreliable"),
        "DATE": ("timestamp", "clock_master"), "ACCELEROMETER": ("m/s^2", "imu_input"),
        "GRAVITY": ("m/s^2", "imu_aux"), "GYROSCOPE": ("rad/s", "imu_input"),
        "MAGNETIC FIELD": ("uT", "imu_input"), "ORIENTATION": ("deg", "orientation_input"),
    },
    "vehicle": {
        "Latitude": ("deg", "reference_position"), "Longitude": ("deg", "reference_position"),
        "Velocity": ("km/h", "reference_speed"), "Heading": ("deg", "reference_heading"),
        "Height": ("m (label says km)", "reference_aux"), "Vertical velocity": ("km/h", "reference_aux"),
        "Sample period": ("s", "clock"), "Steering Angle": ("deg", "vehicle_only_not_input"),
        "Wheel Speed": ("rad/s", "vehicle_only_not_input"), "Yaw Rate": ("deg/s", "vehicle_only_reference"),
        "Indicated Vehicle Speed": ("km/h", "vehicle_only_not_input"),
        "Indicated Longitudinal Acceleration": ("g", "vehicle_only_reference"),
        "Indicated Lateral Acceleration": ("g", "vehicle_only_reference"),
        "Time Since Start of Day": ("s", "clock_master"),
        "No of GPS Satellites": ("count", "gnss_quality"),
        "Handbrake": ("0/1", "vehicle_only_not_input"),
        "Gear Requested": ("gear 1-5", "vehicle_only_not_input"),
        "Gear ": ("gear 1-5", "vehicle_only_not_input"),
        "Engine Speed": ("rev/min", "vehicle_only_not_input"),
        "Coolant Temperature": ("degC", "vehicle_only_not_input"),
        "Clutch Position": ("0/1", "vehicle_only_not_input"),
        "Brake Pressure": ("psi", "vehicle_only_not_input"),
        "Brake Position": ("0/1", "vehicle_only_not_input"),
        "Battery Voltage": ("V", "vehicle_only_not_input"),
        "Air Temperature": ("degC", "vehicle_only_not_input"),
        "Accelerator Pedal Position": ("0/1", "vehicle_only_not_input"),
        "Vertical velocity": ("km/h", "reference_aux"),
    },
}


def _role_for(col: str, kind: str):
    for key, val in _ROLE[kind].items():
        if key.lower() in col.lower():
            return val
    return ("UNKNOWN", "UNKNOWN")


def stage(msg):
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70)


# --------------------------------------------------------------------------- #
def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")       # keep em-dash etc. on Windows
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="process a 12-sequence subset")
    ap.add_argument("--refresh-inventory", action="store_true",
                    help="re-scan every CSV instead of using the cached inventory")
    args = ap.parse_args()

    for d in CFG.dirs():
        d.mkdir(parents=True, exist_ok=True)
    (CFG.processed).mkdir(parents=True, exist_ok=True)

    # data/raw pointer note
    (DEFAULT_CONFIG.interim.parent / "raw" / "README.md").write_text(
        f"# data/raw\n\nRAW DATA IS NOT COPIED HERE. The immutable source tree is:\n\n"
        f"    {CFG.raw_root}\n\n(git-lfs pulled from github.com/onyekpeu/IO-VNBD). "
        f"Set env var IOVNBD_ROOT to relocate. Nothing in this pipeline writes to it.\n",
        encoding="utf-8")

    # ---------------------------------------------------------------- stage 4
    stage("STAGE 4  dataset inventory")
    inv = build_inventory(CFG, use_cache=not args.refresh_inventory)
    inv.to_csv(A / "dataset_inventory.csv", index=False)
    s_files = inv[inv.kind == "phone"]
    v_files = inv[inv.kind == "vehicle"]
    cat_sync = inv[inv.relpath.str.contains("Synchronised V abd S datasets") &
                   inv.relpath.str.contains("Categorised IOVNB Dataset")]
    cat_s = cat_sync[cat_sync.kind == "phone"]
    with open(A / "dataset_inventory.md", "w", encoding="utf-8") as fh:
        fh.write("# IO-VNBD dataset inventory\n\n")
        fh.write(f"- CSV files scanned: **{len(inv)}**  ({len(s_files)} `S-*`, {len(v_files)} `V-*`), "
                 f"total {inv.size_bytes.sum()/1e9:.2f} GB\n")
        fh.write(f"- the tree holds ~3 overlapping copies (Synchronised/Categorised, "
                 f"Synchronised/Uncategorised, Unsynchronised); the pipeline uses only "
                 f"**Synchronised / Categorised** ({len(cat_sync)} files, {len(cat_s)} pairs)\n\n")
        fh.write("## sampling rate (measured, not assumed)\n\n")
        fh.write(f"- Synchronised/Categorised `S-*`: median "
                 f"{cat_s.est_sampling_hz.median():.2f} Hz, "
                 f"range {cat_s.est_sampling_hz.min():.2f}-{cat_s.est_sampling_hz.max():.2f} "
                 f"(uniformly 10 Hz - see `timestamp_diagnostics.csv`)\n")
        fh.write(f"- all `S-*` incl. other pools: median {s_files.est_sampling_hz.median():.2f} Hz, "
                 f"range {s_files.est_sampling_hz.min():.2f}-{s_files.est_sampling_hz.max():.2f} "
                 f"(driver-A uncategorised logs are 2 Hz; a couple of `S-T*` files have "
                 f"sub-ms duplicate timestamps -> not used)\n")
        fh.write(f"- all `V-*`: median {v_files.est_sampling_hz.median():.2f} Hz\n")
        incomplete = inv[(inv.n_rows < 300) | (inv.get('error').notna() if 'error' in inv else False)]
        uniq = sorted({Path(r.relpath).name for _, r in incomplete.iterrows()})
        fh.write(f"\n## incomplete / do-not-use ({len(incomplete)} file entries, "
                 f"{len(uniq)} unique names across copies)\n\n")
        for name in uniq:
            rows = incomplete[incomplete.relpath.str.endswith(name)].n_rows.tolist()
            fh.write(f"- `{name}` - {rows} rows\n")
        fh.write("\nFull per-file detail: `dataset_inventory.csv`.\n")
    print(f"  {len(inv)} CSVs  ->  artifacts/dataset_inventory.csv/.md")

    # ---------------------------------------------------------------- stage 6
    stage("STAGE 6  discover + verify synchronised S/V pairs")
    pairs = discover_pairs(CFG)
    pdf = pairs_to_df(pairs)
    pdf.to_csv(A / "synchronized_pairs.csv", index=False)
    vc = pdf.synchronization_status.value_counts().to_dict()
    print(f"  {len(pairs)} candidate pairs; {vc}")
    sel = select_first_verified(pairs)
    print(f"  selected representative pair: {sel.pair_id}  "
          f"({sel.overlap_duration/60:.1f} min, speed corr@0 {sel.verify_speed_corr_lag0})")

    # ---------------------------------------------------------------- stage 7
    stage("STAGE 7  data dictionary (selected pair)")
    dd_rows = []
    for kind, path in (("phone", sel.S_path), ("vehicle", sel.V_path)):
        raw = pd.read_csv(path, encoding="latin-1", low_memory=False)
        for c in raw.columns:
            s = pd.to_numeric(raw[c], errors="coerce")
            unit, role = _role_for(c, kind)
            dd_rows.append({
                "source_file": Path(path).name, "column_name": c,
                "datatype": str(raw[c].dtype),
                "non_null_count": int(raw[c].notna().sum()),
                "missing_count": int(raw[c].isna().sum()),
                "min": None if s.notna().sum() == 0 else round(float(s.min()), 4),
                "max": None if s.notna().sum() == 0 else round(float(s.max()), 4),
                "mean": None if s.notna().sum() == 0 else round(float(s.mean()), 4),
                "std": None if s.notna().sum() == 0 else round(float(s.std()), 4),
                "likely_unit": unit, "semantic_role": role,
            })
    pd.DataFrame(dd_rows).to_csv(A / "data_dictionary.csv", index=False)
    print(f"  {len(dd_rows)} columns documented -> artifacts/data_dictionary.csv")

    # ---------------------------------------------------------------- stages 5,13,15
    stage("STAGE 5/13/15  build aligned timelines (interim)  +  local ENU reference")
    pool = pairs if not args.quick else pairs[:12]
    stats, built = [], {}
    for p in pool:
        if p.synchronization_status not in ("verified_synced", "synced_authors"):
            continue
        try:
            df = build_sequence(p, CFG)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {p.pair_id}: {e!r}")
            continue
        df.to_parquet(CFG.interim / f"{p.pair_id}.parquet", index=False)
        st = sequence_stats(df)
        stats.append(st)
        built[p.pair_id] = df
    stats_df = pd.DataFrame(stats)
    print(f"  {len(built)} aligned sequences -> data/interim/*.parquet")

    # trajectory_reference.csv for the selected pair
    if sel is not None and sel.pair_id in built:
        seldf = built[sel.pair_id]
    else:
        sel = next(p for p in pool if p.pair_id in built)
        seldf = built[sel.pair_id]
    seldf[["timestamp", "reference_latitude", "reference_longitude",
           "reference_x", "reference_y"]].rename(
        columns={"reference_latitude": "latitude", "reference_longitude": "longitude",
                 "reference_x": "x", "reference_y": "y"}
    ).to_csv(A / "trajectory_reference.csv", index=False)

    # ---------------------------------------------------------------- stage 10
    stage("STAGE 10  timestamp diagnostics")
    tdiag = []
    for sid, df in built.items():
        t = df["timestamp"].to_numpy(float)
        dt = np.diff(t)
        tdiag.append({
            "sequence_id": sid, "format": "seconds_from_start (phone DATE-derived)",
            "monotonic": bool(np.all(dt > 0)), "duplicate_timestamps": int((dt == 0).sum()),
            "n_gaps_gt_0p6s": int((dt > 0.6).sum()),
            "median_dt_s": round(float(np.median(dt)), 4), "mean_dt_s": round(float(dt.mean()), 4),
            "std_dt_s": round(float(dt.std()), 4), "min_dt_s": round(float(dt.min()), 4),
            "max_dt_s": round(float(dt.max()), 3),
            "est_hz": round(1.0 / float(np.median(dt)), 2),
        })
    pd.DataFrame(tdiag).to_csv(A / "timestamp_diagnostics.csv", index=False)
    hz_all = np.array([r["est_hz"] for r in tdiag])
    gnss_int = stats_df["gnss_update_interval_s"].to_numpy()
    print(f"  measured phone IMU rate : median {np.median(hz_all):.2f} Hz "
          f"(range {hz_all.min():.2f}-{hz_all.max():.2f})")
    print(f"  measured phone GNSS int.: median {np.nanmedian(gnss_int):.1f} s "
          f"(min {np.nanmin(gnss_int):.1f}, max {np.nanmax(gnss_int):.1f}) "
          f"-> NOT the assumed 1 Hz on most trips")

    # ---------------------------------------------------------------- stage 11
    stage("STAGE 11  data-quality checks (flag, never delete)")
    qrows = [quality_report(df, sid, CFG) for sid, df in built.items()]
    qdf = pd.DataFrame(qrows)
    with open(A / "data_quality_report.md", "w", encoding="utf-8") as fh:
        fh.write("# Data-quality report\n\nDriving events (pothole/brake spikes) are "
                 "legitimate and are flagged, not removed.\n\n")
        fh.write(qdf.to_markdown(index=False))
        fh.write("\n\n## summary\n")
        fh.write(f"- sequences: {len(qdf)}\n")
        fh.write(f"- with NaN in input channels: {(qdf.nan_cells>0).sum()}\n")
        fh.write(f"- with inf: {(qdf.inf_cells>0).sum()}\n")
        fh.write(f"- with duplicate timestamps: {(qdf.dup_timestamps>0).sum()}\n")
        fh.write(f"- with a gap > {CFG.max_gap_s}s: {(qdf.gaps_gt_max>0).sum()}\n")
        fh.write(f"- flagged extreme accel (kept): {(qdf.flag_acc_extreme).sum()}\n")
        fh.write(f"- flagged impossible speed: {(qdf.flag_speed_impossible).sum()}\n")
        fh.write(f"- constant input channel somewhere: {(qdf.constant_channels!='-').sum()}\n")
    print("  quality report -> artifacts/data_quality_report.md")

    # ---------------------------------------------------------------- stage 12
    stage("STAGE 12  sensor visualisation (representative drive)")
    made = dplots.all_sensor_plots(seldf, CFG.plots)
    for m in made:
        print(f"  {m.relative_to(CFG.artifacts)}")

    # ---------------------------------------------------------------- stage 21
    stage("STAGE 21  sequence-wise train/validation/test split")
    split_df = assign_splits(stats_df, CFG)
    split_df.to_csv(A / "dataset_split.csv", index=False)
    split_map = dict(zip(split_df.sequence_id, split_df.split))
    group_map = dict(zip(split_df.sequence_id, split_df.drive_group))
    counts = split_df.split.value_counts().to_dict()
    print(f"  {counts}")
    print(f"  drive groups: {split_df[split_df.split!='excluded'].drive_group.nunique()} "
          f"across {int((split_df.split!='excluded').sum())} sequences")

    # ---------------------------------------------------------------- stages 16/17/20/23
    stage("STAGE 16/17/20/23  blackout mask + temporal windows + save processed")
    manifest, windows_by_seq = [], {}
    n_win_total = 0
    for sid, df in built.items():
        sp = split_map.get(sid, "excluded")
        if sp == "excluded":
            continue
        bwins = make_blackout_windows(df, CFG, recurring=True)
        masked = apply_mask(df, bwins)
        outdir = CFG.processed / sp
        masked.to_parquet(outdir / f"{sid}.parquet", index=False)

        ws = make_temporal_windows(masked, CFG)
        ws.to_npz(outdir / f"{sid}_windows.npz")
        windows_by_seq[sid] = ws
        n_win_total += ws.X.shape[0]
        manifest.append({
            "sequence_id": sid, "split": sp, "rows": len(masked),
            "duration_s": round(float(masked.timestamp.iloc[-1]), 1),
            "est_hz": round(measure_hz(masked.timestamp.to_numpy()), 2),
            "window_len": ws.window_len, "n_windows": int(ws.X.shape[0]),
            "n_blackout_windows": len(bwins),
            "blackout_seconds": round(sum(w.duration_s for w in bwins), 1),
            "gnss_available_frac": round(float(masked.gnss_available.mean()), 3),
            "timeline_parquet": str((outdir / f"{sid}.parquet").relative_to(CFG.processed.parent)),
            "windows_npz": str((outdir / f"{sid}_windows.npz").relative_to(CFG.processed.parent)),
        })
    man_df = pd.DataFrame(manifest)
    man_df.to_csv(CFG.processed / "manifest.csv", index=False)
    print(f"  {len(man_df)} sequences saved, {n_win_total:,} temporal windows total")

    # ---------------------------------------------------------------- stage 22
    stage("STAGE 22  leakage checks")
    lk = leakage_checks(split_map, windows_by_seq, INPUT_FEATURES, group_map)
    with open(A / "leakage_report.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Leakage report\n\n**STATUS: {lk['status']}**\n\n")
        fh.write(f"- sequences: {lk['n_sequences']}\n- splits: {lk['splits']}\n\n")
        fh.write("## checks performed\n")
        fh.write("1. every sequence in exactly one split\n")
        fh.write("1b. author sub-segments of one drive (S3a/b/c, Vta01a/b, ...) stay in the same split\n")
        fh.write("2. no GNSS / reference field in the model input feature list\n")
        fh.write("3. window channel count matches the declared feature list\n")
        fh.write("4. windows never cross a sequence boundary or a logging gap "
                 "(enforced in windowing.py)\n")
        fh.write("5. input window ends at t; target taken at t (+horizon) - no past-of-target rows in X\n\n")
        if lk["issues"]:
            fh.write("## ISSUES\n")
            for i in lk["issues"]:
                fh.write(f"- {i}\n")
        else:
            fh.write("No issues found.\n")
    print(f"  leakage status: {lk['status']}")

    # ---------------------------------------------------------------- narrative artifacts
    stage("write reference / alignment / input / target docs")
    _write_reference_doc(sel)
    _write_alignment_doc(hz_all)
    _write_input_doc()
    _write_target_doc()

    # ---------------------------------------------------------------- final summary
    stage("IO-VNBD preprocessing completed.")
    n_tr = int((man_df.split == "train").sum())
    n_va = int((man_df.split == "validation").sum())
    n_te = int((man_df.split == "test").sum())
    print(f"  usable sequences        : {len(man_df)}")
    print(f"  total duration          : {man_df.duration_s.sum()/3600:.2f} h")
    print(f"  train / val / test seqs : {n_tr} / {n_va} / {n_te}")
    print(f"  input feature count     : {len(INPUT_FEATURES)}  {list(INPUT_FEATURES)}")
    print(f"  target definition       : {CFG.target} (horizon {CFG.target_horizon_steps} steps)")
    print(f"  sampling frequency      : {np.median(hz_all):.2f} Hz (measured)")
    print(f"  temporal windows        : {n_win_total:,} (window_len "
          f"{windows_by_seq and next(iter(windows_by_seq.values())).window_len})")
    miss = int(qdf.nan_cells.sum())
    print(f"  missing input cells     : {miss}")
    print(f"  leakage status          : {lk['status']}")
    print()
    if lk["status"] == "PASS" and n_tr and n_va and n_te:
        print("DATASET READY FOR STEP 12 — MODEL TRAINING")
    else:
        print("NOT READY - resolve the issues above before training.")


# --------------------------------------------------------------------------- #
def _write_reference_doc(sel):
    (A / "reference_definition.md").write_text(f"""# Reference trajectory definition

**Source:** vehicle (`V-*`) GNSS/INS channels - `Latitude`, `Longitude`,
`Velocity (km/hr)`, `Heading (degrees)`.

**Why this and not the phone GNSS:** the phone GPS updates at ~1 Hz, is held
between updates, and is the noisier consumer-grade receiver. The vehicle file
carries a survey-grade GNSS/INS solution at the full 10 Hz. Using the phone GNSS
as *both* a (masked) input and the ground truth would be circular, so the phone
GNSS is kept only for bookkeeping / `native_gnss_valid`, never as the target.

**Sampling rate:** 10 Hz, row-aligned with the phone stream in the synchronised
pairs (confirmed by smoothed phone-speed vs reference-speed correlation at
lag 0 = {sel.verify_speed_corr_lag0} for the selected pair `{sel.pair_id}`).

**Coordinates:** `reference_x`, `reference_y` are local ENU metres from the first
valid vehicle fix (equirectangular projection, R = 6378137 m). See
`src/data/coordinates.py`.

**Limitations:** still a GNSS-based solution (not cm-truth); brief outages /
multipath possible; a handful of trips show internal position-vs-speed
inconsistency and are flagged in `data_quality_report.md`.
""", encoding="utf-8")


def _write_alignment_doc(hz_all):
    (A / "alignment_report.md").write_text(f"""# Time-alignment report

**Master clock:** the smartphone IMU timeline, rebuilt from the phone `DATE`
column (the `TIME SINCE START (ms)` column is unreliable on several trips) and
rebased so each sequence starts at t = 0.

**Measured phone rate:** median {np.median(hz_all):.2f} Hz across sequences
(range {hz_all.min():.2f}-{hz_all.max():.2f}); this is *measured per file*, not
assumed.

**Phone <-> vehicle:** the "Synchronised / Categorised" pairs are already
sample-locked at 10 Hz by the dataset authors. Each pair is truncated to the
shorter length (mismatch is 0-230 rows, mostly the `Vf` driver) and then treated
as row-for-row aligned. This is verified per pair by cross-correlating phone
GNSS speed against vehicle reference speed (`synchronized_pairs.csv`).

**Target alignment:** because the streams are row-aligned, `reference_speed` is
taken directly at each IMU sample - **no interpolation, no forward-fill**. Rows
inside a logging gap (`dt > {DEFAULT_CONFIG.max_gap_s}` s) are left in the
timeline but no temporal window is allowed to span them.

**Phone GNSS is NOT upsampled** to 10 Hz and passed off as dense truth; it is
only used to derive `native_gnss_valid`.

**Measured phone GNSS refresh (not assumed):** the problem statement says ~1 Hz,
but the actual `GPS LATITUDE/LONGITUDE` columns refresh every **~9 s** on most
trips (only a few, e.g. `Vta02`, are true 1 Hz), with real dropouts of 30-150 s.
`gnss_update_interval_s` is recorded per sequence; `native_gnss_valid` uses a
12 s staleness threshold so a normal 9 s hold is still "valid" and only genuine
multi-fix outages are flagged.
""", encoding="utf-8")


def _write_input_doc():
    (A / "model_input_definition.md").write_text("""# Model input definition (phase: data prep - not trained)

Inputs available to the model **during a simulated GNSS outage** - phone inertial
/ orientation only:

| # | feature | source | unit |
|---|---------|--------|------|
| 1-3 | `acc_x/y/z` | phone accelerometer | m/s^2 |
| 4-6 | `gyro_x/y/z` | phone gyroscope | rad/s |
| 7-9 | `mag_x/y/z` | phone magnetometer | uT |
| 10-12 | `roll`,`pitch`,`yaw` | phone ORIENTATION | deg |

Channel order above is the order in the generated window tensors
(`*_windows.npz`, key `X`, shape `(n, window_len, 12)`).

**Explicitly excluded from inputs** (would leak the answer during an outage):
latitude, longitude, phone GNSS speed, phone GNSS heading, altitude, and every
`reference_*` field. Also excluded: all vehicle-only channels (steering, wheel
speed, OBD `Indicated Vehicle Speed`, engine rpm, ...) - per the PS, vehicle-side
data is reference/validation only, never a smartphone-model input.

`gravity_x/y/z` is retained in the interim timeline for optional
alignment/feature work but is **not** in the default input list.
""", encoding="utf-8")


def _write_target_doc():
    (A / "target_definition.md").write_text("""# Target definition (phase: data prep - not trained)

**Selected first target:** `forward_speed` - the vehicle's forward speed in m/s
at the window-end timestamp, taken from the reference channel
`Velocity (km/hr) / 3.6`.

Rationale: directly matches the SIH requirement (AI speed / motion estimation for
dead reckoning), is a single scalar that is easy to validate, and needs no
assumption about heading.

**Prepared but not selected** (generator supports switching via
`PrepConfig.target`):

| key | value | shape |
|-----|-------|-------|
| `forward_speed` | reference speed at t (+horizon) | scalar |
| `velocity_vector` | d(reference_x, reference_y)/dt | (vx, vy) |
| `displacement` | (reference_x, reference_y)[t+h] - [t] | (dx, dy) |

`target_horizon_steps = 0` -> nowcast (speed at the last input sample).
Set > 0 for short-horizon prediction; windowing then drops windows whose target
sample lies beyond a gap or the sequence end.

The target is derived **only** from the reference trajectory and is never placed
in the input tensor (checked in `leakage_report.md`).
""", encoding="utf-8")


if __name__ == "__main__":
    main()
