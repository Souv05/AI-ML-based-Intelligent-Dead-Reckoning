"""Stage: temporal window generator (NOT training).

Given an aligned per-sequence timeline it emits fixed-length input windows and
the matching target, without ever crossing a sequence boundary or a logging gap.

    window_len = round(window_seconds * hz)      (hz measured per sequence)
    X[k]  = INPUT_FEATURES over samples [end-window_len+1 .. end]
    y[k]  = target at (end + target_horizon_steps)

Targets
    forward_speed    : reference_speed [m/s] (scalar)
    velocity_vector  : (vx, vy) from d(reference_x, reference_y)/dt  [m/s]
    displacement     : (dx, dy) over the next `target_horizon_steps` [m]

Nothing GNSS- or reference-derived is ever put into X.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import INPUT_FEATURES, PrepConfig, DEFAULT_CONFIG


@dataclass
class WindowSet:
    sequence_id: str
    X: np.ndarray                 # (n_windows, window_len, n_features)
    y: np.ndarray                 # (n_windows,) or (n_windows, 2)
    end_index: np.ndarray         # row index of each window end
    end_time: np.ndarray          # timestamp of each window end
    gnss_available_at_end: np.ndarray
    feature_names: tuple[str, ...]
    target: str
    window_len: int
    horizon: int

    def to_npz(self, path):
        np.savez_compressed(
            path,
            X=self.X.astype(np.float32),
            y=self.y.astype(np.float32),
            end_index=self.end_index.astype(np.int64),
            end_time=self.end_time.astype(np.float64),
            gnss_available_at_end=self.gnss_available_at_end.astype(np.int8),
            feature_names=np.array(self.feature_names),
            target=np.array(self.target),
            window_len=np.array(self.window_len),
            horizon=np.array(self.horizon),
        )


def measure_hz(t: np.ndarray) -> float:
    dt = np.diff(t)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    return float(1.0 / np.median(dt)) if dt.size else float("nan")


def _target_series(df: pd.DataFrame, cfg: PrepConfig):
    t = df["timestamp"].to_numpy(float)
    if cfg.target == "forward_speed":
        return df["reference_speed"].to_numpy(float), 1
    if cfg.target == "velocity_vector":
        vx = np.gradient(df["reference_x"].to_numpy(float), t)
        vy = np.gradient(df["reference_y"].to_numpy(float), t)
        return np.c_[vx, vy], 2
    if cfg.target == "displacement":
        return np.c_[df["reference_x"].to_numpy(float),
                     df["reference_y"].to_numpy(float)], 2
    raise ValueError(f"unknown target {cfg.target!r}")


def make_windows(df: pd.DataFrame, cfg: PrepConfig = DEFAULT_CONFIG) -> WindowSet:
    df = df.reset_index(drop=True)
    t = df["timestamp"].to_numpy(float)
    hz = measure_hz(t)
    wlen = max(2, int(round(cfg.window_seconds * hz)))
    horizon = int(cfg.target_horizon_steps)

    feats = df[list(INPUT_FEATURES)].to_numpy(float)
    tgt, _dim = _target_series(df, cfg)
    dts = np.diff(t)
    gaps_at = np.r_[False, (dts > cfg.max_gap_s) | (dts <= 0)]   # gaps + dup/non-monotonic

    Xs, ys, ends = [], [], []
    last = len(df) - 1 - max(horizon, 0)
    step = max(1, int(cfg.window_stride_steps))
    for end in range(wlen - 1, last + 1, step):
        sl = slice(end - wlen + 1, end + 1)
        if gaps_at[sl].any():
            continue
        tgt_idx = end + horizon
        if cfg.target == "displacement":
            if tgt_idx >= len(df) or gaps_at[end + 1:tgt_idx + 1].any():
                continue
            yv = tgt[tgt_idx] - tgt[end]
        else:
            yv = tgt[tgt_idx]
        xw = feats[sl]
        if not np.isfinite(xw).all() or not np.isfinite(np.atleast_1d(yv)).all():
            continue
        Xs.append(xw)
        ys.append(yv)
        ends.append(end)

    ends = np.asarray(ends, dtype=int)
    X = np.asarray(Xs, dtype=np.float32) if Xs else np.empty((0, wlen, len(INPUT_FEATURES)), np.float32)
    y = np.asarray(ys, dtype=np.float32) if ys else np.empty((0,), np.float32)
    ga = df["gnss_available"].to_numpy()[ends] if "gnss_available" in df and ends.size else np.zeros(0)
    et = t[ends] if ends.size else np.zeros(0)

    return WindowSet(
        sequence_id=str(df["sequence_id"].iloc[0]) if "sequence_id" in df else "?",
        X=X, y=y, end_index=ends, end_time=et, gnss_available_at_end=ga,
        feature_names=INPUT_FEATURES, target=cfg.target,
        window_len=wlen, horizon=horizon,
    )
