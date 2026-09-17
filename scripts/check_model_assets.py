"""Check model asset consistency: server and Flutter each use their own frozen model.

The server runs GRU v2 (window=60, Step 16E), which won the model-selection
evaluation (Step 16D) on median FDE.

The Flutter on-device fallback uses TCN-GRU (window=40, Step 16B), which is
5x smaller and 2x faster — the correct edge-deployment choice.

These are intentionally different models, so this checker verifies each side
against its OWN metadata (not cross-comparing them), plus checks that the
Flutter Dart constants in gru_v2_speed_estimator.dart match Flutter's metadata.

Usage:
    python scripts/check_model_assets.py
    python scripts/check_model_assets.py --flutter-dir /path/to/flutter/assets/models

Exit 0 = all checks pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

# ── Server paths ──────────────────────────────────────────────────────────────
_SERVER_ONNX   = _ROOT / "models" / "exported" / "onnx" / "gru_v2.onnx"
_SERVER_META   = _ROOT / "models" / "gru" / "gru_v2_metadata.json"
_SERVER_SCALER = _ROOT / "models" / "gru" / "scaler.json"

# ── Flutter paths (default — adjust with --flutter-dir if needed) ─────────────
_FLUTTER_DIR_DEFAULT = (
    _ROOT.parent / "SIH 2026" / "intelligent_dead_reckoning" / "assets" / "models"
)

# ── Flutter Dart constants (from gru_v2_speed_estimator.dart) ─────────────────
# These must match the Flutter metadata file exactly.
_DART_WINDOW_LENGTH  = 40          # kGruV2WindowLength
_DART_NUM_CHANNELS   = 12          # kGruV2NumChannels
_DART_INPUT_NAME     = "sensor_window"   # kGruV2InputName
_DART_OUTPUT_NAME    = "speed_normalised"  # kGruV2OutputName
_DART_FEATURE_ORDER  = [
    "acc_x", "acc_y", "acc_z",
    "gyro_x", "gyro_y", "gyro_z",
    "mag_x", "mag_y", "mag_z",
    "roll", "pitch", "yaw",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ok(label: str) -> None:
    print(f"  OK   {label}")


def _fail(label: str, expected, actual, failures: list[str]) -> None:
    msg = f"  FAIL {label}: expected {expected!r}  got {actual!r}"
    print(msg)
    failures.append(msg)


def _check(label: str, expected, actual, failures: list[str]) -> None:
    if expected == actual:
        _ok(label)
    else:
        _fail(label, expected, actual, failures)


def _close(a: float, b: float, tol: float = 1e-7) -> bool:
    return abs(a - b) <= tol


def _lists_close(a: list, b: list, tol: float = 1e-7) -> bool:
    return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))


# ── Check sets ────────────────────────────────────────────────────────────────

def _check_server(failures: list[str]) -> None:
    print("\n[Server] GRU v2 (window=60)  — primary navigation model")
    for p, label in [(_SERVER_ONNX, "gru_v2.onnx"),
                     (_SERVER_META, "gru_v2_metadata.json"),
                     (_SERVER_SCALER, "scaler.json")]:
        if p.exists():
            size_kb = p.stat().st_size // 1024
            _ok(f"{label} exists  ({size_kb} KB)")
        else:
            msg = f"  FAIL missing: {p}"
            print(msg)
            failures.append(msg)

    meta   = _load(_SERVER_META)
    scaler = _load(_SERVER_SCALER)

    if meta:
        _check("input_name",       "sensor_window",    meta.get("input_name"),       failures)
        _check("output_name",      "speed_normalised", meta.get("output_name"),      failures)
        _check("sequence_length",  60,                 meta.get("sequence_length"),  failures)
        _check("input_size",       12,                 meta.get("input_size"),       failures)

    if scaler:
        n_mean = len(scaler.get("x_mean", []))
        n_std  = len(scaler.get("x_std",  []))
        _check("scaler x_mean channels", 12, n_mean, failures)
        _check("scaler x_std  channels", 12, n_std,  failures)
        if meta:
            # Scaler inside metadata should match standalone scaler.json
            inline = meta.get("scaler", {}) if isinstance(meta.get("scaler"), dict) else {}
            if inline:
                ok_mean = _lists_close(inline.get("x_mean", []), scaler.get("x_mean", []))
                ok_std  = _lists_close(inline.get("x_std",  []), scaler.get("x_std",  []))
                if ok_mean: _ok("metadata scaler.x_mean == scaler.json.x_mean")
                else: _fail("metadata scaler.x_mean vs scaler.json", "matching", "mismatch", failures)
                if ok_std:  _ok("metadata scaler.x_std  == scaler.json.x_std")
                else: _fail("metadata scaler.x_std  vs scaler.json", "matching", "mismatch", failures)


def _check_flutter(flutter_dir: Path, failures: list[str]) -> None:
    print(f"\n[Flutter] TCN-GRU (window=40)  — on-device fallback model")
    print(f"          dir: {flutter_dir}")

    fl_onnx   = flutter_dir / "gru_v2.onnx"
    fl_scaler = flutter_dir / "scaler.json"
    fl_meta   = flutter_dir / "gru_v2_metadata.json"

    for p, label in [(fl_onnx, "gru_v2.onnx"),
                     (fl_scaler, "scaler.json"),
                     (fl_meta,   "gru_v2_metadata.json")]:
        if p.exists():
            size_kb = p.stat().st_size // 1024
            _ok(f"{label} exists  ({size_kb} KB)")
        else:
            msg = f"  FAIL missing: {p}"
            print(msg)
            failures.append(msg)

    meta   = _load(fl_meta)
    scaler = _load(fl_scaler)

    if meta:
        _check("input_name",      "sensor_window",    meta.get("input_name"),      failures)
        _check("output_name",     "speed_normalised", meta.get("output_name"),     failures)
        _check("sequence_length", 40,                 meta.get("sequence_length"), failures)
        _check("input_size",      12,                 meta.get("input_size"),      failures)

    if scaler:
        n_mean = len(scaler.get("x_mean", []))
        n_std  = len(scaler.get("x_std",  []))
        _check("scaler x_mean channels", 12, n_mean, failures)
        _check("scaler x_std  channels", 12, n_std,  failures)

    print("\n[Flutter Dart constants vs Flutter metadata]")
    if meta:
        _check("kGruV2WindowLength  == sequence_length", _DART_WINDOW_LENGTH,  meta.get("sequence_length"),  failures)
        _check("kGruV2NumChannels   == input_size",       _DART_NUM_CHANNELS,   meta.get("input_size"),       failures)
        _check("kGruV2InputName     == input_name",       _DART_INPUT_NAME,     meta.get("input_name"),       failures)
        _check("kGruV2OutputName    == output_name",      _DART_OUTPUT_NAME,    meta.get("output_name"),      failures)
        _check("kGruV2FeatureOrder  == feature_order",    _DART_FEATURE_ORDER,  meta.get("feature_order"),    failures)
    else:
        print("  SKIP (Flutter metadata not found)")

    # Note: y_mean differs between the two models by design (different training)
    print("\n[Expected differences between server and Flutter models]")
    sv_meta = _load(_SERVER_META)
    if meta and sv_meta:
        sv_win = sv_meta.get("sequence_length", "?")
        fl_win = meta.get("sequence_length",    "?")
        sv_mod = sv_meta.get("model", "?")
        fl_mod = meta.get("model",    "?")
        print(f"  INFO server:  {sv_mod}, window={sv_win}  (GRU v2 — best FDE)")
        print(f"  INFO flutter: {fl_mod}, window={fl_win}  (TCN-GRU — 5x smaller)")
        if sv_win != fl_win:
            print("  OK   window lengths differ by design (60 vs 40)")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--flutter-dir", default=str(_FLUTTER_DIR_DEFAULT),
                   help=f"Flutter assets/models dir (default: {_FLUTTER_DIR_DEFAULT})")
    args = p.parse_args()

    flutter_dir = Path(args.flutter_dir)

    failures: list[str] = []

    print("=" * 60)
    print("Model Asset Consistency Check")
    print("=" * 60)

    _check_server(failures)

    if flutter_dir.exists():
        _check_flutter(flutter_dir, failures)
    else:
        print(f"\n[Flutter] SKIP — directory not found: {flutter_dir}")
        print("  Run with --flutter-dir <path> to check Flutter assets.")

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S)")
        for f in failures:
            print(f"  {f.strip()}")
        sys.exit(1)
    else:
        print("RESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
