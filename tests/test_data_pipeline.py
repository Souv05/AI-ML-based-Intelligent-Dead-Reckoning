"""Unit tests for the IO-VNBD data-prep pipeline (run: python -m pytest -q).

These guard the correctness-critical preprocessing functions; they do NOT train.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data.config import INPUT_FEATURES, PrepConfig
from data.coordinates import latlon_to_local_xy, path_length_m, first_valid_origin
from data.blackout import native_gnss_valid, make_windows as bo_windows, apply_mask
from data.windowing import make_windows as tw_windows, measure_hz
from data.preprocessing import assign_splits, drive_group
from data.validation import leakage_checks


def _synthetic_timeline(n=1200, hz=10.0, seq="TEST"):
    t = np.arange(n) / hz
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"timestamp": t, "sequence_id": seq})
    for c in INPUT_FEATURES:
        df[c] = rng.normal(size=n)
    speed = 10 + 5 * np.sin(t / 20)
    df["reference_speed"] = speed
    df["reference_x"] = np.cumsum(speed) / hz
    df["reference_y"] = 0.0
    df["reference_heading"] = 90.0
    df["latitude"] = 52.0 + t * 1e-6
    df["longitude"] = -1.5 + t * 1e-6
    df["gnss_speed"] = speed
    df["gnss_heading"] = 90.0
    df["altitude"] = 100.0
    df["reference_latitude"] = df["latitude"]
    df["reference_longitude"] = df["longitude"]
    df["native_gnss_valid"] = 1
    df["gnss_available"] = 1
    return df


# ---------------------------------------------------------------- coordinates
def test_enu_origin_is_zero_and_metric():
    lat = np.array([52.0, 52.001, 52.002])
    lon = np.array([-1.5, -1.5, -1.5])
    x, y, (lat0, lon0) = latlon_to_local_xy(lat, lon)
    assert abs(x[0]) < 1e-6 and abs(y[0]) < 1e-6
    # 0.001 deg latitude ~ 111.32 m
    assert 110 < y[1] < 113
    assert lat0 == 52.0


def test_first_valid_origin_skips_zeros_and_nans():
    lat = np.array([0.0, np.nan, 52.0, 52.1])
    lon = np.array([0.0, np.nan, -1.5, -1.5])
    i, la, lo = first_valid_origin(lat, lon)
    assert i == 2 and la == 52.0


def test_path_length_positive():
    lat = np.linspace(52.0, 52.01, 50)
    lon = np.full(50, -1.5)
    assert path_length_m(lat, lon) > 1000


# ---------------------------------------------------------------- windowing
def test_windows_shape_and_channel_order():
    df = _synthetic_timeline()
    cfg = PrepConfig(window_seconds=2.0)
    ws = tw_windows(df, cfg)
    assert ws.window_len == 20
    assert ws.X.shape[1:] == (20, len(INPUT_FEATURES))
    assert tuple(ws.feature_names) == tuple(INPUT_FEATURES)
    assert ws.y.ndim == 1                       # forward_speed is scalar


def test_windows_do_not_cross_gaps():
    df = _synthetic_timeline(n=600)
    # inject a 5 s gap at row 300
    t = df["timestamp"].to_numpy().copy()
    t[300:] += 5.0
    df["timestamp"] = t
    cfg = PrepConfig(window_seconds=2.0, max_gap_s=0.6)
    ws = tw_windows(df, cfg)
    # no window may contain both sides of the gap
    for e in ws.end_index:
        seg = df["timestamp"].to_numpy()[e - ws.window_len + 1:e + 1]
        assert np.max(np.diff(seg)) <= cfg.max_gap_s + 1e-9


def test_target_matches_reference_speed_nowcast():
    df = _synthetic_timeline()
    ws = tw_windows(df, PrepConfig(window_seconds=2.0, target="forward_speed"))
    ref = df["reference_speed"].to_numpy()[ws.end_index]
    assert np.allclose(ws.y, ref, atol=1e-4)


def test_no_reference_or_gnss_channel_in_X():
    df = _synthetic_timeline()
    ws = tw_windows(df, PrepConfig())
    assert not ({"reference_speed", "gnss_speed", "latitude", "longitude"}
                & set(ws.feature_names))


# ---------------------------------------------------------------- blackout
def test_blackout_masks_inputs_not_reference():
    df = _synthetic_timeline(n=1500)
    cfg = PrepConfig(blackout_warmup_s=30, blackout_duration_s=30)
    wins = bo_windows(df, cfg, recurring=False)
    assert wins, "expected at least one blackout window"
    masked = apply_mask(df, wins)
    w = wins[0]
    assert (masked["gnss_available"].to_numpy()[w.start_idx:w.end_idx] == 0).all()
    # reference columns untouched
    assert masked["reference_speed"].equals(df["reference_speed"])
    assert masked["reference_x"].equals(df["reference_x"])


def test_native_gnss_valid_flags_bad_coords():
    df = _synthetic_timeline(n=200)
    df.loc[10:20, "latitude"] = np.nan
    df.loc[30:40, ["latitude", "longitude"]] = 0.0
    ngv = native_gnss_valid(df)
    assert not ngv[15] and not ngv[35] and ngv[100]


# ---------------------------------------------------------------- split + leakage
def test_split_is_sequence_wise_and_disjoint():
    stats = pd.DataFrame({
        "sequence_id": [f"S{i}" for i in range(20)],
        "duration_s": np.linspace(80, 4000, 20),
        "path_len_km": np.linspace(0.5, 40, 20),
    })
    sp = assign_splits(stats, PrepConfig(split_seed=1))
    per_seq = sp.groupby("sequence_id").split.nunique()
    assert (per_seq == 1).all()
    assert set(sp.split) <= {"train", "validation", "test", "excluded"}


def test_drive_group_collapses_subsegments():
    assert drive_group("S3a") == "S3" and drive_group("S3c") == "S3"
    assert drive_group("Vta01a") == "Vta01" and drive_group("Vta01b") == "Vta01"
    assert drive_group("Vw14b") == "Vw14"
    assert drive_group("Vta02") == "Vta02"           # digit-terminal, unchanged
    assert drive_group("V-Vfa01") == "V-Vfa01"


def test_subsegments_share_a_split():
    stats = pd.DataFrame({
        "sequence_id": ["D1a", "D1b", "D1c", "D2", "D3a", "D3b", "D4", "D5", "D6", "D7"],
        "duration_s": [300, 300, 300, 900, 400, 400, 900, 900, 900, 900],
        "path_len_km": [3, 3, 3, 9, 4, 4, 9, 9, 9, 9],
    })
    sp = assign_splits(stats, PrepConfig(split_seed=3))
    g = sp.set_index("sequence_id").split
    assert g["D1a"] == g["D1b"] == g["D1c"]
    assert g["D3a"] == g["D3b"]


def test_leakage_report_flags_banned_feature():
    bad = tuple(INPUT_FEATURES) + ("reference_speed",)
    rep = leakage_checks({"S1": "train"}, {}, bad)
    assert rep["status"] == "FAIL"
    rep_ok = leakage_checks({"S1": "train", "S2": "test"}, {}, INPUT_FEATURES)
    assert rep_ok["status"] == "PASS"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
