"""Stage 4: inventory every dataset CSV actually present on disk.

Reads real files - no assumptions about names or columns. Results are cached to
data/interim/_inventory_cache.parquet so re-runs are instant.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PrepConfig, DEFAULT_CONFIG

_ENC = "latin-1"


def _timestamp_column(cols: list[str]) -> str | None:
    low = [c.lower() for c in cols]
    for key in ("time since start of day", "date", "time since start"):
        for c, l in zip(cols, low):
            if key in l:
                return c
    return None


def _parse_ts(series: pd.Series, name: str) -> np.ndarray:
    n = name.lower()
    if "date" in n:
        s = series.astype(str).str.strip().str.replace(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):(\d+)$", r"\1.\2", regex=True)
        ts = pd.to_datetime(s, errors="coerce")
        return (ts - ts.iloc[0]).dt.total_seconds().to_numpy()
    v = pd.to_numeric(series, errors="coerce").to_numpy(float)
    if "ms" in n:
        v = v / 1000.0
    return v - np.nanmin(v)


def inventory_file(path: Path) -> dict:
    size = path.stat().st_size
    try:
        df = pd.read_csv(path, encoding=_ENC, low_memory=False)
    except Exception as e:  # noqa: BLE001
        return {"filename": path.name, "relpath": str(path), "filetype": path.suffix,
                "size_bytes": size, "error": repr(e)}

    cols = list(df.columns)
    tcol = _timestamp_column(cols)
    ts = _parse_ts(df[tcol], tcol) if tcol else np.arange(len(df), dtype=float) * 0.1
    ts = ts[np.isfinite(ts)]
    dt = np.diff(np.sort(ts)) if ts.size > 1 else np.array([])
    dt = dt[dt > 0]

    kind = "phone" if path.name.upper().startswith("S-") else \
           "vehicle" if path.name.upper().startswith("V-") else "other"

    return {
        "filename": path.name,
        "relpath": str(path.relative_to(path.parents[len(path.parents) - 1])) if False else str(path),
        "kind": kind,
        "filetype": path.suffix.lower(),
        "size_bytes": size,
        "size_mb": round(size / 1e6, 2),
        "n_rows": len(df),
        "n_cols": len(cols),
        "columns": " | ".join(cols),
        "timestamp_column": tcol or "(none - assumed 10Hz index)",
        "first_timestamp_s": round(float(ts[0]), 3) if ts.size else None,
        "last_timestamp_s": round(float(ts[-1]), 3) if ts.size else None,
        "duration_s": round(float(ts[-1] - ts[0]), 2) if ts.size else None,
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_timestamps": int((dt == 0).sum()) if dt.size else 0,
        "est_sampling_interval_s": round(float(np.median(dt)), 4) if dt.size else None,
        "est_sampling_hz": round(1.0 / float(np.median(dt)), 2) if dt.size else None,
        "max_gap_s": round(float(dt.max()), 2) if dt.size else None,
    }


def build_inventory(cfg: PrepConfig = DEFAULT_CONFIG, use_cache: bool = True) -> pd.DataFrame:
    cache = cfg.interim / "_inventory_cache.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    rows = []
    for dp, _d, files in os.walk(cfg.raw_root):
        for f in files:
            if f.lower().endswith(".csv"):
                rows.append(inventory_file(Path(dp) / f))
    df = pd.DataFrame(rows).sort_values(["kind", "relpath"]).reset_index(drop=True)
    cfg.interim.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df
