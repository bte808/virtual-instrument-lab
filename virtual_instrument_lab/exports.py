"""Portable, headless exports. Exported records always identify synthetic data."""

import csv
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .core import SimulationConfig, validate_config


DATA_KIND = "synthetic_simulation_no_hardware"


def _config_payload(config):
    # Core also accepts NumPy numeric scalars; JSON requires builtin numbers.
    return {name: int(value) if name == "seed" else float(value)
            for name, value in asdict(config).items()}


@contextmanager
def _atomic_text(path):
    """Do not replace an existing export until the complete write succeeds."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            yield handle
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_settings(config, path):
    validate_config(config)
    payload = {"schema_version": 1, "data_kind": DATA_KIND, "config": _config_payload(config)}
    with _atomic_text(path) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return Path(path)


def _reject_constant(value):
    raise ValueError("Settings must contain only finite JSON numbers")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate settings key: " + key)
        result[key] = value
    return result


def load_settings(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024:
        raise ValueError("Settings file is too large (maximum 64 KiB)")
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle, parse_constant=_reject_constant,
                                object_pairs_hook=_unique_object)
    except RecursionError as exc:
        raise ValueError("Settings document nesting is too deep") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "data_kind", "config"}:
        raise ValueError("Invalid settings document structure")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Unsupported settings schema version")
    if payload["data_kind"] != DATA_KIND:
        raise ValueError("Only synthetic simulation settings are supported")
    config_data = payload["config"]
    expected = set(SimulationConfig.__dataclass_fields__)
    if not isinstance(config_data, dict) or set(config_data) != expected:
        raise ValueError("Settings must contain exactly the documented configuration fields")
    config = SimulationConfig(**config_data)
    validate_config(config)
    return config


def export_csv(result, path):
    """CSV comments carry metadata; skip lines beginning with # when importing."""
    with _atomic_text(path) as handle:
        handle.write("# data_kind=" + DATA_KIND + "\n")
        handle.write("# voltage_amplitudes=peak; phase=degrees; no_hardware_connected\n")
        handle.write("# config=" + json.dumps(_config_payload(result.config), allow_nan=False) + "\n")
        handle.write("# settling_time_s=" + str(result.settling_time_s) + "\n")
        handle.write("# estimate_start_s=" + str(result.estimate_start_s) + "\n")
        handle.write("# settled=" + str(result.settled).lower() + "\n")
        writer = csv.writer(handle)
        writer.writerow(["time_s", "clean_v", "input_v", "filtered_v", "lockin_x_v",
                         "lockin_y_v", "lockin_amplitude_peak_v", "lockin_phase_deg",
                         "after_startup"])
        for t, clean, raw, filtered, x, y, amplitude, phase in zip(
                result.time_s, result.clean_v, result.input_v, result.filtered_v,
                result.x_v, result.y_v, result.amplitude_v, result.phase_deg):
            writer.writerow([t, clean, raw, filtered, x, y, amplitude,
                             phase if np.isfinite(phase) else "",
                             int(t >= result.settling_time_s)])
    return Path(path)


def export_figure(result, path):
    """PNG only; construct an Agg canvas without importing Tk."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from .plotting import build_figure

    path = Path(path)
    if path.suffix.lower() != ".png":
        raise ValueError("Figure export requires a .png filename")
    figure = build_figure(result)
    FigureCanvasAgg(figure)
    figure.savefig(path, dpi=140, format="png", facecolor=figure.get_facecolor(),
                   metadata={"Description": "Synthetic simulation data. No hardware connected."})
    figure.clear()
    return path
