"""Stage: find and VERIFY synchronised smartphone/vehicle pairs.

The "Synchronised V abd S datasets / Categorised IOVNB Dataset" tree provides
folders each holding one S-*.csv and one V-*.csv that the dataset authors
manually time-aligned.  We do not trust that blindly - each pair is verified by
cross-correlating the phone GNSS speed against the vehicle reference speed and
reporting the best lag and its correlation.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PrepConfig, DEFAULT_CONFIG
from .loader import load_phone_file, load_vehicle_file

SYNCED_CATEGORISED_REL = Path("Synchronised V abd S datasets") / "Categorised IOVNB Dataset"


@dataclass
class Pair:
    pair_id: str
    driver: str
    S_file: str
    V_file: str
    S_path: str
    V_path: str
    n_rows_S: int
    n_rows_V: int
    row_mismatch: int
    synchronization_status: str
    overlapping_start_time: float
    overlapping_end_time: float
    overlap_duration: float
    verify_speed_corr_lag0: float
    verify_speed_corr_best: float
    verify_best_lag_samples: int
    verify_note: str


def _smooth(x: np.ndarray, k: int = 20) -> np.ndarray:
    """Centred moving average - removes the ~9 s staircase of the held phone GPS
    speed so it can be compared against the smooth vehicle speed."""
    if k < 2:
        return x
    kern = np.ones(k) / k
    return np.convolve(np.nan_to_num(x, nan=0.0), kern, mode="same")


def _speed_corr(a: np.ndarray, b: np.ndarray, max_lag: int = 60):
    """(corr_at_lag0, best_corr, best_lag) between phone speed `a` and vehicle
    speed `b`, on moving samples, after smoothing both."""
    n = min(len(a), len(b))
    a, b = _smooth(a[:n]), _smooth(b[:n])
    move = (b > 3.0) & np.isfinite(a) & np.isfinite(b)
    if move.sum() < 200:
        return 0.0, 0.0, 0

    def corr(shift):
        bb = np.roll(b, shift)
        m = move & np.isfinite(bb)
        if m.sum() < 200 or np.std(a[m]) < 1e-6 or np.std(bb[m]) < 1e-6:
            return 0.0
        r = float(np.corrcoef(a[m], bb[m])[0, 1])
        return r if np.isfinite(r) else 0.0

    r0 = corr(0)
    best_r, best_l = r0, 0
    for lag in range(-max_lag, max_lag + 1):
        r = corr(lag)
        if abs(r) > abs(best_r):
            best_r, best_l = r, lag
    return r0, best_r, best_l


def discover_pairs(cfg: PrepConfig = DEFAULT_CONFIG) -> list[Pair]:
    root = cfg.raw_root / SYNCED_CATEGORISED_REL
    if not root.is_dir():
        raise FileNotFoundError(f"missing synchronised tree: {root}")

    pairs: list[Pair] = []
    for dirpath, _dirs, files in os.walk(root):
        s = sorted(f for f in files if f.upper().startswith("S-") and f.lower().endswith(".csv"))
        v = sorted(f for f in files if f.upper().startswith("V-") and f.lower().endswith(".csv"))
        if not (s and v):
            continue
        folder = Path(dirpath)
        driver = folder.relative_to(root).parts[0]
        s_path, v_path = folder / s[0], folder / v[0]
        pair_id = folder.name if folder.name != driver else s[0][2:-4]

        try:
            ph = load_phone_file(s_path)
            ve = load_vehicle_file(v_path)
        except Exception as e:  # noqa: BLE001
            pairs.append(Pair(pair_id, driver, s[0], v[0], str(s_path), str(v_path),
                              -1, -1, -1, f"LOAD_ERROR: {e!r}",
                              0.0, 0.0, 0.0, 0.0, 0.0, 0, "unloadable"))
            continue

        nS, nV = len(ph.canonical), len(ve.canonical)
        n = min(nS, nV)
        tS = ph.canonical["t"].to_numpy()
        tV = ve.canonical["t"].to_numpy()
        ov_end = float(min(tS[n - 1], tV[n - 1]))

        r0, rbest, lag = _speed_corr(
            ph.canonical["gnss_speed"].to_numpy()[:n],
            ve.canonical["reference_speed"].to_numpy()[:n],
        )
        # these are the authors' manually synchronised pairs; our smoothed
        # speed cross-correlation is a confirmation, not the source of truth.
        if r0 >= 0.75 and abs(nS - nV) <= 300:
            status, note = "verified_synced", f"row-aligned; speed corr@0 = {r0:.2f}"
        elif r0 >= 0.5:
            status, note = "synced_authors", f"authors' sync; speed corr@0 = {r0:.2f}"
        else:
            status, note = "sync_suspect", f"speed corr@0 only {r0:.2f} (best {rbest:.2f}@{lag})"

        pairs.append(Pair(
            pair_id=pair_id, driver=driver, S_file=s[0], V_file=v[0],
            S_path=str(s_path), V_path=str(v_path),
            n_rows_S=nS, n_rows_V=nV, row_mismatch=abs(nS - nV),
            synchronization_status=status,
            overlapping_start_time=0.0,
            overlapping_end_time=round(ov_end, 3),
            overlap_duration=round(ov_end, 3),
            verify_speed_corr_lag0=round(r0, 3),
            verify_speed_corr_best=round(rbest, 3),
            verify_best_lag_samples=int(lag),
            verify_note=note,
        ))

    pairs.sort(key=lambda p: (p.driver, p.pair_id))
    return pairs


def pairs_to_df(pairs: list[Pair]) -> pd.DataFrame:
    return pd.DataFrame([asdict(p) for p in pairs])


def select_first_verified(pairs: list[Pair]) -> Pair | None:
    for p in pairs:
        if p.synchronization_status == "verified_synced" and p.overlap_duration >= 120:
            return p
    return next((p for p in pairs
                 if p.synchronization_status in ("verified_synced", "synced_authors")), None)


USABLE_SYNC_STATUS = ("verified_synced", "synced_authors")
