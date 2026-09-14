"""Matplotlib figures for EDA and for the drift benchmark. Headless (Agg)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .deadreckon import DRResult
from .loader import Trip


def trip_overview(trip: Trip, out: Path) -> Path:
    p = trip.phone
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle(f"{trip.key}  -  {trip.length_m/1000:.1f} km / {trip.duration_s/60:.1f} min")

    ax[0, 0].plot(trip.east_m, trip.north_m, lw=0.8)
    ax[0, 0].scatter([0], [0], c="g", s=30, zorder=5, label="start")
    ax[0, 0].set(title="ground-truth track (ENU)", xlabel="E [m]", ylabel="N [m]")
    ax[0, 0].axis("equal"); ax[0, 0].legend()

    ax[0, 1].plot(trip.t, trip.vehicle.speed_ms * 3.6, lw=0.8)
    ax[0, 1].set(title="ground-truth speed", xlabel="t [s]", ylabel="km/h")

    pt = p.df["t"].to_numpy()
    pdt = np.diff(pt)
    pdt = pdt[np.isfinite(pdt) & (pdt > 0)]
    ax[1, 0].hist(pdt, bins=np.linspace(0, max(0.5, np.percentile(pdt, 99)), 60))
    ax[1, 0].set(title=f"phone sample interval (median {np.median(pdt)*1000:.0f} ms)",
                 xlabel="dt [s]", ylabel="count")

    if "gps_acc_m" in p.df:
        ax[1, 1].plot(trip.t, p.df["gps_acc_m"].to_numpy(), lw=0.6)
        ax[1, 1].axhline(15, color="r", ls="--", lw=0.8, label="poor (>15 m)")
        ax[1, 1].set(title="phone GPS accuracy", xlabel="t [s]", ylabel="m")
        ax[1, 1].legend()

    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def drift_figure(trip: Trip, results: list[DRResult], out: Path) -> Path:
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
    r0 = results[0]
    ax[0].plot(r0.east_true, r0.north_true, "k-", lw=2.4, label="truth")
    for r in results:
        ax[0].plot(r.east_hat, r.north_hat, lw=1.3,
                   label=f"{r.speed_source}/{r.heading_source}  "
                         f"{r.drift_pct:.1f}%")
    ax[0].scatter([r0.east_true[0]], [r0.north_true[0]], c="g", s=40, zorder=6)
    ax[0].scatter([r0.east_true[-1]], [r0.north_true[-1]], c="r", s=40, zorder=6)
    ax[0].set(title=f"{trip.key}: outage {r0.t[-1]-r0.t[0]:.0f} s "
                    f"/ {r0.path_len_m:.0f} m",
              xlabel="E [m]", ylabel="N [m]")
    ax[0].axis("equal"); ax[0].legend(fontsize=8)

    for r in results:
        err = np.hypot(r.east_hat - r.east_true, r.north_hat - r.north_true)
        ax[1].plot(r.t - r.t[0], err, lw=1.3,
                   label=f"{r.speed_source}/{r.heading_source}")
    ax[1].axhline(0.10 * r0.path_len_m, color="r", ls="--", lw=1,
                  label="ISRO 10% bound")
    ax[1].set(title="position error vs outage time", xlabel="t [s]", ylabel="error [m]")
    ax[1].legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out
