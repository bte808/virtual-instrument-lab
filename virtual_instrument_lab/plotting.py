"""Shared plotting for the desktop and headless PNG export."""

import textwrap

import numpy as np
from matplotlib.figure import Figure


def _line(ax, x, y, **kwargs):
    # Keep extrema per bucket so large records do not hide narrow spikes.
    if len(x) > 12000:
        width = int(np.ceil(len(x) / 6000))
        keep = [0, len(x) - 1]
        for start in range(0, len(x), width):
            block = y[start:start + width]
            if np.any(np.isfinite(block)):
                keep.extend((start + int(np.nanargmin(block)), start + int(np.nanargmax(block))))
        indices = np.unique(keep)
        x, y = x[indices], y[indices]
    return ax.plot(x, y, **kwargs)


def build_figure(result):
    figure = Figure(figsize=(12, 7.8), dpi=100, constrained_layout=True, facecolor="#f5f7fb")
    axes = figure.subplots(2, 2)
    time_ax, spectrum_ax, xy_ax, amplitude_ax = axes.ravel()
    colors = {"raw": "#75869a", "filtered": "#067a94", "clean": "#be6500",
              "x": "#2563b8", "y": "#a93d78"}
    _line(time_ax, result.time_s, result.input_v, color=colors["raw"], lw=0.65, alpha=0.75, label="Input")
    _line(time_ax, result.time_s, result.filtered_v, color=colors["filtered"], lw=1.0, label="Causal LP")
    _line(time_ax, result.time_s, result.clean_v, color=colors["clean"], lw=0.6, alpha=0.7, label="Signal + DC")
    time_ax.set(title="Time domain (startup retained)", xlabel="Time (s)", ylabel="Voltage (V)")
    _line(spectrum_ax, result.frequency_hz, result.input_spectrum_v,
          color=colors["raw"], lw=0.8, label="Input")
    _line(spectrum_ax, result.frequency_hz, result.filtered_spectrum_v,
          color=colors["filtered"], lw=1, label="Causal LP")
    spectrum_ax.set(title="Single-sided FFT • rectangular window", xlabel="Frequency (Hz)", ylabel="Amplitude (V peak)")
    spectrum_ax.set_xlim(0, result.config.sample_rate_hz / 2)
    _line(xy_ax, result.time_s, result.x_v, color=colors["x"], label="X = LP(2x cos)")
    _line(xy_ax, result.time_s, result.y_v, color=colors["y"], label="Y = LP(-2x sin)")
    xy_ax.set(title="Dual-phase lock-in (raw input)", xlabel="Time (s)", ylabel="X / Y (V)")
    _line(amplitude_ax, result.time_s, result.amplitude_v, color=colors["filtered"], label="R (V peak)")
    amplitude_ax.set(title="Lock-in amplitude and phase", xlabel="Time (s)", ylabel="Amplitude (V peak)")
    phase_ax = amplitude_ax.twinx()
    _line(phase_ax, result.time_s, result.phase_deg, color=colors["y"], lw=0.8, alpha=0.65, label="Phase (deg)")
    phase_ax.set(ylabel="Phase (deg)", ylim=(-185, 185))
    phase_ax.grid(False)
    for ax in (time_ax, xy_ax, amplitude_ax):
        ax.axvspan(0, min(result.settling_time_s, result.time_s[-1]), color="#efb54f", alpha=0.16)
        if result.settling_time_s <= result.time_s[-1]:
            ax.axvline(result.settling_time_s, color="#a66805", ls="--", lw=0.9)
        ax.set_xlim(0, result.time_s[-1])
    for ax in axes.ravel():
        ax.set_facecolor("white")
        ax.grid(True, color="#dce3eb", lw=0.6, alpha=0.65)
        ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
        ax.tick_params(labelsize=8)
    phase_ax.legend(loc="lower right", fontsize=8)
    phase = "undefined" if result.estimate_phase_deg is None else f"{result.estimate_phase_deg:.2f} deg"
    status = "Startup criterion met" if result.settled else "NOT SETTLED - provisional estimate"
    figure.suptitle(
        "SYNTHETIC SIMULATION DATA | NO HARDWARE CONNECTED\n"
        f"R = {result.estimate_amplitude_v:.5g} V peak   Phase = {phase}   |   {status}",
        fontsize=12, color="#152d46", fontweight="bold")
    footer = (
        f"Amber = startup < {result.settling_time_s:.3g} s. Mean X/Y estimate starts at {result.estimate_start_s:.3g} s. "
        "Settling criterion does not guarantee accuracy.")
    if result.warnings:
        footer += "\n" + "\n".join(textwrap.fill("Warning: " + message, width=140)
                                  for message in result.warnings)
    figure.supxlabel(footer, fontsize=8)
    return figure
