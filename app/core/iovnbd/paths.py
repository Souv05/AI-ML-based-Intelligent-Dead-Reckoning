"""Dataset location and trip discovery.

The IO-VNBD tree (after `git lfs pull`) looks like::

    dataset/IO-VNBD/
        Synchronised V abd S datasets/            # note: upstream typo "abd"
            Categorised IOVNB Dataset/
                <Driver folder>/<trip folder>/S-*.csv + V-*.csv   (+ V-*.JPG)
            Uncategorised IOVNB Dataset/
                S-Dataset/S-*.csv
                V-Dataset/V-*.csv
        Unsynchronised V and S Dataset/
            ...

Only the *Categorised* part of *Synchronised* gives row-aligned S/V pairs, which
is what we need for supervised speed-labelling and for the drift benchmark.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Root resolution
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[2]                      # D:\SIH 2026
DATASET_ROOT = Path(
    os.environ.get("IOVNBD_ROOT", _PROJECT_ROOT / "dataset" / "IO-VNBD")
)

SYNCED_CATEGORISED = (
    DATASET_ROOT / "Synchronised V abd S datasets" / "Categorised IOVNB Dataset"
)
SYNCED_UNCATEGORISED = (
    DATASET_ROOT / "Synchronised V abd S datasets" / "Uncategorised IOVNB Dataset"
)
UNSYNCED_ROOT = DATASET_ROOT / "Unsynchronised V and S Dataset"

OUTPUT_ROOT = Path(os.environ.get("IOVNBD_OUT", _PROJECT_ROOT / "outputs"))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Trip records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SyncedTrip:
    """A row-aligned smartphone/vehicle pair."""

    trip_id: str          # e.g. "Vta29"
    driver: str           # e.g. "Vta (Driver E)"
    folder: Path
    phone_csv: Path
    vehicle_csv: Path

    @property
    def key(self) -> str:
        return f"{self.driver.split(' ')[0]}/{self.trip_id}"


@dataclass(frozen=True)
class PhoneOnlyTrip:
    trip_id: str
    phone_csv: Path


def _looks_like_lfs_pointer(p: Path) -> bool:
    try:
        with open(p, "rb") as fh:
            return fh.read(40).startswith(b"version https://git-lfs")
    except OSError:
        return True


def find_synced_trips(check_pointers: bool = True) -> list[SyncedTrip]:
    """Every categorised folder that holds exactly one S-*.csv and one V-*.csv."""
    trips: list[SyncedTrip] = []
    if not SYNCED_CATEGORISED.is_dir():
        raise FileNotFoundError(
            f"{SYNCED_CATEGORISED} not found. Did `git lfs pull` complete?"
        )
    for dirpath, _dirs, files in os.walk(SYNCED_CATEGORISED):
        s = sorted(f for f in files if f.upper().startswith("S-") and f.lower().endswith(".csv"))
        v = sorted(f for f in files if f.upper().startswith("V-") and f.lower().endswith(".csv"))
        if not (s and v):
            continue
        folder = Path(dirpath)
        driver = folder.relative_to(SYNCED_CATEGORISED).parts[0]
        phone_csv = folder / s[0]
        vehicle_csv = folder / v[0]
        if check_pointers and (
            _looks_like_lfs_pointer(phone_csv) or _looks_like_lfs_pointer(vehicle_csv)
        ):
            continue
        trip_id = folder.name if folder.name != driver else s[0][2:-4]
        trips.append(
            SyncedTrip(
                trip_id=trip_id,
                driver=driver,
                folder=folder,
                phone_csv=phone_csv,
                vehicle_csv=vehicle_csv,
            )
        )
    trips.sort(key=lambda t: (t.driver, t.trip_id))
    return trips


def find_phone_only_trips() -> list[PhoneOnlyTrip]:
    """All S-*.csv under the uncategorised synchronised S-Dataset pool."""
    out: list[PhoneOnlyTrip] = []
    sdir = SYNCED_UNCATEGORISED / "S-Dataset"
    if sdir.is_dir():
        for f in sorted(sdir.glob("S-*.csv")):
            if not _looks_like_lfs_pointer(f):
                out.append(PhoneOnlyTrip(trip_id=f.stem[2:], phone_csv=f))
    return out


if __name__ == "__main__":
    ts = find_synced_trips()
    print(f"DATASET_ROOT = {DATASET_ROOT}")
    print(f"{len(ts)} synced categorised trips")
    for t in ts:
        print(f"  {t.key:<16}  {t.phone_csv.name:<12} + {t.vehicle_csv.name}")
