"""Stage 12: sensor visualisation for ONE representative synchronised drive.

All figures headless (Agg). Saved under artifacts/plots/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def triaxial(df: pd.DataFrame, cols, title, ylabel, out: Path) -> Path:
    t = df["timestamp"].to_numpy()
    fig, ax = plt.subplots(figsize=(13, 4))
    for c, lab in zip(cols, ("x", "y", "z")):
        ax.plot(t, df[c].to_numpy(), lw=0.6, label=lab)
    ax.set(title=title, xlabel="time [s]", ylabel=ylabel)
    ax.legend(loc="upper right")
    return _save(fig, out)


def heading_plot(df: pd.DataFrame, out: Path) -> Path:
    t = df["timestamp"].to_numpy()
    fig, ax = plt.subplots(figsize=(13, 4))
    if df["yaw"].notna().any():
        ax.plot(t, df["yaw"].to_numpy(), lw=0.6, label="phone yaw/heading")
    ax.plot(t, df["reference_heading"].to_numpy(), lw=0.6, label="reference heading")
    ax.set(title="Heading / orientation vs time", xlabel="time [s]", ylabel="deg")
    ax.legend(loc="upper right")
    return _save(fig, out)


def speed_plot(df: pd.DataFrame, out: Path) -> Path:
    t = df["timestamp"].to_numpy()
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.plot(t, df["gnss_speed"].to_numpy(), lw=0.7, label="phone GNSS speed [m/s]")
    ax.plot(t, df["reference_speed"].to_numpy(), lw=0.7, label="reference speed [m/s]")
    ax.set(title="Speed vs time", xlabel="time [s]", ylabel="m/s")
    ax.legend(loc="upper right")
    return _save(fig, out)


def trajectory_plot(df: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(df["reference_x"].to_numpy(), df["reference_y"].to_numpy(), lw=0.9,
            label="reference (vehicle GNSS/INS)")
    ax.scatter([0], [0], c="g", s=40, zorder=5, label="origin")
    ax.set(title="Trajectory (local ENU)", xlabel="east [m]", ylabel="north [m]")
    ax.axis("equal"); ax.legend()
    return _save(fig, out)


def timestamp_intervals_plot(df: pd.DataFrame, out: Path) -> Path:
    dt = np.diff(df["timestamp"].to_numpy())
    dt = dt[np.isfinite(dt) & (dt > 0)]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4))
    hi = max(0.3, np.percentile(dt, 99.5))
    ax[0].hist(dt[dt <= hi], bins=80)
    ax[0].set(title=f"timestep distribution (median {np.median(dt)*1000:.1f} ms)",
              xlabel="dt [s]", ylabel="count")
    ax[1].plot(df["timestamp"].to_numpy()[1:], dt, lw=0.4)
    ax[1].set(title="timestep vs time", xlabel="time [s]", ylabel="dt [s]")
    ax[1].set_yscale("log")
    return _save(fig, out)


def all_sensor_plots(df: pd.DataFrame, plots_dir: Path) -> list[Path]:
    plots_dir.mkdir(parents=True, exist_ok=True)
    p = plots_dir
    return [
        triaxial(df, ["acc_x", "acc_y", "acc_z"], "Accelerometer vs time", "m/s^2", p / "accelerometer.png"),
        triaxial(df, ["gyro_x", "gyro_y", "gyro_z"], "Gyroscope vs time", "rad/s", p / "gyroscope.png"),
        triaxial(df, ["mag_x", "mag_y", "mag_z"], "Magnetometer vs time", "uT", p / "magnetometer.png"),
        heading_plot(df, p / "heading.png"),
        speed_plot(df, p / "speed.png"),
        trajectory_plot(df, p / "trajectory.png"),
        timestamp_intervals_plot(df, p / "timestamp_intervals.png"),
    ]
