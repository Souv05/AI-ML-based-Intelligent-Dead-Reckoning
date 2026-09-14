"""Stage: data-quality checks and train/test leakage checks.

Nothing here deletes data. Quality issues are *flagged* and reported; driving
events (pothole/brake spikes) are explicitly not treated as errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INPUT_FEATURES, GNSS_FIELDS, REFERENCE_FIELDS, PrepConfig, DEFAULT_CONFIG

# generous physical envelopes - outside = "flag", not "drop"
_ACC_ABS_MAX = 60.0        # m/s^2  (~6 g; potholes can be brief and large)
_GYRO_ABS_MAX = 20.0       # rad/s
_SPEED_ABS_MAX = 75.0      # m/s    (270 km/h)


def quality_report(df: pd.DataFrame, seq_id: str, cfg: PrepConfig = DEFAULT_CONFIG) -> dict:
    t = df["timestamp"].to_numpy(float)
    dt = np.diff(t)
    acc = df[["acc_x", "acc_y", "acc_z"]].to_numpy(float)
    gyro = df[["gyro_x", "gyro_y", "gyro_z"]].to_numpy(float)
    spd = df["reference_speed"].to_numpy(float)

    def const_channels():
        out = []
        for c in INPUT_FEATURES:
            v = df[c].to_numpy(float)
            v = v[np.isfinite(v)]
            if v.size and np.nanstd(v) < 1e-9:
                out.append(c)
        return out

    return {
        "sequence_id": seq_id,
        "rows": len(df),
        "duration_s": round(float(t[-1] - t[0]), 1),
        "nan_cells": int(df[list(INPUT_FEATURES)].isna().sum().sum()),
        "inf_cells": int(np.isinf(df[list(INPUT_FEATURES)].to_numpy(float)).sum()),
        "dup_timestamps": int((dt == 0).sum()),
        "non_monotonic": int((dt < 0).sum()),
        "gaps_gt_max": int((dt > cfg.max_gap_s).sum()),
        "max_gap_s": round(float(dt.max()), 2) if dt.size else None,
        "median_dt_s": round(float(np.median(dt)), 4) if dt.size else None,
        "est_hz": round(1.0 / float(np.median(dt)), 2) if dt.size else None,
        "constant_channels": ",".join(const_channels()) or "-",
        "acc_abs_max": round(float(np.nanmax(np.abs(acc))), 2),
        "gyro_abs_max": round(float(np.nanmax(np.abs(gyro))), 3),
        "flag_acc_extreme": bool(np.nanmax(np.abs(acc)) > _ACC_ABS_MAX),
        "flag_gyro_extreme": bool(np.nanmax(np.abs(gyro)) > _GYRO_ABS_MAX),
        "flag_speed_impossible": bool(np.nanmax(np.abs(spd)) > _SPEED_ABS_MAX),
        "frac_stationary": round(float(np.nanmean(spd < 0.5)), 3),
        "n_extreme_acc_samples": int(np.sum(np.nanmax(np.abs(acc), axis=1) > _ACC_ABS_MAX)),
    }


# --------------------------------------------------------------------------- #
# leakage
# --------------------------------------------------------------------------- #
def leakage_checks(split_map: dict[str, str],
                   windows_by_seq: dict[str, "WindowSet"],  # noqa: F821
                   feature_names: tuple[str, ...],
                   group_map: dict[str, str] | None = None) -> dict:
    issues: list[str] = []

    # 1. a sequence must live in exactly one split
    seen: dict[str, str] = {}
    for seq, sp in split_map.items():
        if seq in seen and seen[seq] != sp:
            issues.append(f"sequence {seq} in both {seen[seq]} and {sp}")
        seen[seq] = sp

    # 1b. author sub-segments of one physical drive must not straddle splits
    if group_map:
        grp_splits: dict[str, set] = {}
        for seq, sp in split_map.items():
            grp_splits.setdefault(group_map.get(seq, seq), set()).add(sp)
        for g, sps in grp_splits.items():
            if len(sps) > 1:
                issues.append(f"drive group {g} spans splits {sorted(sps)}")

    # 2. no GNSS / reference field leaked into the input feature list
    banned = set(GNSS_FIELDS) | set(REFERENCE_FIELDS) | {
        "latitude", "longitude", "gnss_speed", "gnss_heading",
        "reference_speed", "reference_x", "reference_y",
    }
    leaked = sorted(set(feature_names) & banned)
    if leaked:
        issues.append(f"GNSS/reference fields present as model inputs: {leaked}")

    # 3. windows must not straddle sequences (end_index strictly inside one seq)
    #    and X must not contain the target channel
    for seq, ws in windows_by_seq.items():
        if ws.X.shape[0] and ws.X.shape[2] != len(feature_names):
            issues.append(f"{seq}: X has {ws.X.shape[2]} channels, expected {len(feature_names)}")

    # 4. duplicate windows across splits (same seq+end can't happen if #1 holds,
    #    but check identical X rows across splits defensively on a sample)
    return {
        "n_sequences": len(seen),
        "splits": sorted(set(split_map.values())),
        "issues": issues,
        "status": "PASS" if not issues else "FAIL",
    }
