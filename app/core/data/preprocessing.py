"""Stage: build the aligned per-sequence timeline and the sequence-wise split.

raw S-/V- CSV
   -> load (canonical names, parsed clocks)          [loader.py]
   -> row-align phone & vehicle (synced pairs are sample-locked at ~10 Hz)
   -> master timeline = phone IMU clock
   -> attach GNSS fields (phone) + reference fields (vehicle GNSS/INS)
   -> local ENU reference_x / reference_y                [coordinates.py]
   -> native_gnss_valid + gnss_available (= native, pre-blackout)  [blackout.py]
   -> data/interim/<seq>.parquet   (aligned, nothing masked/removed)
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .blackout import native_gnss_valid
from .config import (BOOKKEEPING_FIELDS, GNSS_FIELDS, INPUT_FEATURES,
                     REFERENCE_FIELDS, PrepConfig, DEFAULT_CONFIG)
from .coordinates import latlon_to_local_xy, path_length_m
from .loader import load_phone_file, load_vehicle_file
from .synchronization import Pair

TIMELINE_COLUMNS = (
    ["timestamp", "sequence_id"]
    + list(INPUT_FEATURES)
    + list(GNSS_FIELDS)
    + list(REFERENCE_FIELDS)
    + ["native_gnss_valid", "gnss_available"]
)


def build_sequence(pair: Pair, cfg: PrepConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    ph = load_phone_file(pair.S_path)
    ve = load_vehicle_file(pair.V_path)
    P, V = ph.canonical, ve.canonical

    n = min(len(P), len(V))
    P, V = P.iloc[:n].reset_index(drop=True), V.iloc[:n].reset_index(drop=True)

    # master timeline = phone IMU clock (rebased to 0)
    t = P["t"].to_numpy(float)
    t = t - t[0]

    df = pd.DataFrame({"timestamp": t})
    df["sequence_id"] = pair.pair_id
    for c in INPUT_FEATURES:
        df[c] = P[c].to_numpy(float)

    # phone GNSS (kept for bookkeeping / native-availability; NOT a model input)
    df["latitude"] = P["latitude"].to_numpy(float)
    df["longitude"] = P["longitude"].to_numpy(float)
    df["gnss_speed"] = P["gnss_speed"].to_numpy(float)
    df["gnss_heading"] = P["gnss_heading"].to_numpy(float)
    df["altitude"] = P["altitude"].to_numpy(float)

    # reference trajectory = vehicle GNSS/INS
    rlat = V["reference_latitude"].to_numpy(float)
    rlon = V["reference_longitude"].to_numpy(float)
    rx, ry, origin = latlon_to_local_xy(rlat, rlon)
    df["reference_latitude"] = rlat
    df["reference_longitude"] = rlon
    df["reference_speed"] = V["reference_speed"].to_numpy(float)          # m/s
    df["reference_heading"] = V["reference_heading"].to_numpy(float)
    df["reference_x"] = rx
    df["reference_y"] = ry

    ngv = native_gnss_valid(df)
    df["native_gnss_valid"] = ngv.astype(np.int8)
    df["gnss_available"] = ngv.astype(np.int8)        # blackout not applied yet

    df.attrs["origin_latlon"] = origin
    df.attrs["path_len_m"] = path_length_m(rlat, rlon)
    df.attrs["pair_id"] = pair.pair_id
    df.attrs["driver"] = pair.driver
    return df[TIMELINE_COLUMNS]


def _gnss_update_interval_s(df: pd.DataFrame) -> float:
    lat = df["latitude"].to_numpy(float)
    lon = df["longitude"].to_numpy(float)
    t = df["timestamp"].to_numpy(float)
    chg = np.r_[True, (np.diff(lat) != 0) | (np.diff(lon) != 0)]
    ct = t[chg]
    d = np.diff(ct)
    return float(np.median(d)) if d.size else float("nan")


def sequence_stats(df: pd.DataFrame) -> dict:
    t = df["timestamp"].to_numpy(float)
    dt = np.diff(t)
    return {
        "sequence_id": df["sequence_id"].iloc[0],
        "rows": len(df),
        "duration_s": round(float(t[-1] - t[0]), 1),
        "duration_min": round(float(t[-1] - t[0]) / 60, 2),
        "path_len_km": round(df.attrs.get("path_len_m", np.nan) / 1000, 3),
        "est_hz": round(1.0 / float(np.median(dt)), 2) if dt.size else None,
        "mean_speed_kmh": round(float(np.nanmean(df["reference_speed"])) * 3.6, 1),
        "max_speed_kmh": round(float(np.nanmax(df["reference_speed"])) * 3.6, 1),
        "frac_stationary": round(float(np.nanmean(df["reference_speed"] < 0.5)), 3),
        "native_gnss_valid_frac": round(float(df["native_gnss_valid"].mean()), 3),
        "gnss_update_interval_s": round(_gnss_update_interval_s(df), 2),
        "n_gaps_gt_0p6s": int((dt > 0.6).sum()),
        "max_gap_s": round(float(dt.max()), 2) if dt.size else None,
    }


# --------------------------------------------------------------------------- #
# sequence-wise split
# --------------------------------------------------------------------------- #
def drive_group(sequence_id: str) -> str:
    """Collapse author sub-segments of one physical drive to a single key so
    they never straddle the split boundary, e.g. S3a/S3b/S3c -> S3,
    Vta01a/Vta01b -> Vta01, Vw14a/b/c -> Vw14.  A trailing lowercase letter is
    stripped only when it directly follows a digit (Vfa01, Vta02 keep their id)."""
    return re.sub(r"(?<=\d)[a-z]$", "", str(sequence_id))


def assign_splits(stats_df: pd.DataFrame, cfg: PrepConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Whole *drives* (grouped sub-segments included) go to one split.
    Allocation is by cumulative DURATION so the splits are balanced in time,
    not file count. Deterministic (seeded)."""
    usable = stats_df[
        (stats_df["duration_s"] >= cfg.min_sequence_seconds)
        & (stats_df["path_len_km"] >= cfg.min_sequence_km)
    ].copy()
    usable["group"] = usable["sequence_id"].map(drive_group)

    grp_dur = usable.groupby("group")["duration_s"].sum().to_dict()
    rng = np.random.default_rng(cfg.split_seed)
    groups = list(grp_dur)
    rng.shuffle(groups)

    total = sum(grp_dur.values())
    f_tr, f_va, _ = cfg.split_fractions
    cum, gsplit = 0.0, {}
    for g in groups:
        frac = cum / total if total else 1.0
        gsplit[g] = "train" if frac < f_tr else "validation" if frac < f_tr + f_va else "test"
        cum += grp_dur[g]

    rows = []
    for _, r in stats_df.iterrows():
        sid = r["sequence_id"]
        g = drive_group(sid)
        rows.append({
            "sequence_id": sid,
            "drive_group": g,
            "source_file": f"S-{sid}.csv + V-{sid}.csv",
            "duration_s": r["duration_s"],
            "path_len_km": r["path_len_km"],
            "split": gsplit.get(g, "excluded"),
        })
    return pd.DataFrame(rows).sort_values(["split", "sequence_id"]).reset_index(drop=True)
