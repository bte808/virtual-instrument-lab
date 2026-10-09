import csv
import json
import struct
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest

from virtual_instrument_lab.core import PRESETS, SimulationConfig, simulate
from virtual_instrument_lab.exports import DATA_KIND, export_csv, export_figure, load_settings, save_settings


@pytest.fixture
def result():
    return simulate(replace(SimulationConfig(), duration_s=0.1))


def test_settings_roundtrip_reproduces_every_sample(tmp_path):
    config = next(iter(PRESETS.values()))
    target = tmp_path / "settings ü 中文.json"
    save_settings(config, target)
    restored = load_settings(target)
    assert asdict(restored) == asdict(config)
    assert np.array_equal(simulate(restored).input_v, simulate(config).input_v)
    assert json.loads(target.read_text(encoding="utf-8"))["data_kind"] == DATA_KIND


def test_numpy_scalar_config_exports(tmp_path):
    config = replace(SimulationConfig(), seed=np.int64(42), amplitude_v=np.float32(0.5), duration_s=0.1)
    path = save_settings(config, tmp_path / "numpy.json")
    assert load_settings(path) == config
    export_csv(simulate(config), tmp_path / "numpy.csv")


def test_settings_deep_nesting_is_a_validation_error(tmp_path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 1100 + "0" + "]" * 1100, encoding="utf-8")
    # JSON parser depth limits differ across Python releases; both early
    # parser rejection and later schema rejection must be normal input errors.
    with pytest.raises(ValueError):
        load_settings(path)


def test_plot_preserves_reference_mismatch_warning():
    from virtual_instrument_lab.plotting import build_figure
    result = simulate(replace(PRESETS["Clean reference"], reference_frequency_hz=51.0))
    figure = build_figure(result)
    assert any("Reference frequency differs" in text.get_text() for text in figure.texts)
    figure.clear()


def test_csv_roundtrip_and_synthetic_metadata(result, tmp_path):
    path = export_csv(result, tmp_path / "simulation ü 中文.csv")
    text = path.read_text(encoding="utf-8")
    assert DATA_KIND in text and "no_hardware_connected" in text
    rows = list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))
    assert len(rows) == len(result.time_s)
    mapping = {"time_s": "time_s", "clean_v": "clean_v", "input_v": "input_v",
               "filtered_v": "filtered_v", "lockin_x_v": "x_v", "lockin_y_v": "y_v",
               "lockin_amplitude_peak_v": "amplitude_v"}
    for column, field in mapping.items():
        np.testing.assert_array_equal([float(row[column]) for row in rows], getattr(result, field))
    np.testing.assert_allclose([float(row["lockin_phase_deg"]) if row["lockin_phase_deg"] else np.nan
                               for row in rows], result.phase_deg, equal_nan=True)
    assert rows[-1]["time_s"] != str(result.config.duration_s)


def test_zero_phase_csv_is_blank(tmp_path):
    zero = simulate(replace(SimulationConfig(), amplitude_v=0, dc_offset_v=0, noise_std_v=0,
                            interference_amplitude_v=0, duration_s=0.1))
    path = export_csv(zero, tmp_path / "zero.csv")
    rows = list(csv.DictReader(line for line in path.read_text().splitlines() if not line.startswith("#")))
    assert all(row["lockin_phase_deg"] == "" for row in rows)


def test_png_is_real_image_and_contains_provenance(result, tmp_path):
    path = tmp_path / "plot ü 中文.PNG"
    path.write_bytes(b"previous image")
    assert export_figure(result, path) == path
    content = path.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", content[16:24])
    assert width >= 1000 and height >= 800
    assert b"Synthetic simulation data" in content
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("existing", [False, True])
def test_failed_png_write_preserves_destination_and_clears_figure(result, tmp_path, monkeypatch, existing):
    from matplotlib.figure import Figure
    from virtual_instrument_lab import plotting

    path = tmp_path / "plot.png"
    if existing:
        path.write_bytes(b"previous image")
    figure = Figure()
    figure.subplots()
    monkeypatch.setattr(plotting, "build_figure", lambda _result: figure)

    def fail_write(destination, **_kwargs):
        # Fail after bytes were written, as an interrupted/disk-full write can.
        if hasattr(destination, "write"):
            destination.write(b"partial image")
        else:
            Path(destination).write_bytes(b"partial image")
        raise OSError("simulated PNG write failure")

    monkeypatch.setattr(figure, "savefig", fail_write)
    with pytest.raises(OSError, match="simulated PNG write failure"):
        export_figure(result, path)
    if existing:
        assert path.read_bytes() == b"previous image"
    else:
        assert not path.exists()
    assert list(tmp_path.iterdir()) == ([path] if existing else [])
    assert figure.axes == []


@pytest.mark.parametrize("kind", ["csv", "json", "png"])
def test_failed_replacement_preserves_existing_export_and_removes_temp(result, tmp_path, monkeypatch, kind):
    from virtual_instrument_lab import exports

    path = tmp_path / ("existing." + kind)
    path.write_bytes(b"previous export")
    original_temporary_file = exports.tempfile.NamedTemporaryFile
    temporary_handles = []

    def track_temporary_file(*args, **kwargs):
        handle = original_temporary_file(*args, **kwargs)
        temporary_handles.append(handle)
        return handle

    def fail_replace(source, destination):
        assert Path(source).parent == path.parent
        assert Path(source).stat().st_size > 0
        assert Path(destination) == path
        # An open temporary file cannot be renamed on Windows.
        assert temporary_handles and all(handle.closed for handle in temporary_handles)
        raise PermissionError("simulated destination is locked")

    monkeypatch.setattr(exports.tempfile, "NamedTemporaryFile", track_temporary_file)
    monkeypatch.setattr(exports.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="simulated destination is locked"):
        if kind == "json":
            save_settings(result.config, path)
        elif kind == "csv":
            export_csv(result, path)
        else:
            export_figure(result, path)
    assert path.read_bytes() == b"previous export"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=2),
    lambda p: p.update(schema_version=True),
    lambda p: p.update(data_kind="actual_measurement"),
    lambda p: p.update(extra="unexpected"),
    lambda p: p["config"].pop("seed"),
    lambda p: p["config"].update(amplitude_v="1.0"),
    lambda p: p["config"].update(seed=True),
    lambda p: p["config"].update(noise_std_v=-1),
])
def test_reject_malformed_settings(tmp_path, mutation):
    path = tmp_path / "settings.json"
    save_settings(SimulationConfig(), path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        load_settings(path)


@pytest.mark.parametrize("content", ['{"schema_version":1,"schema_version":1}', 'NaN', '[]', '{'])
def test_reject_invalid_json(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_headless_cli_exports_without_importing_tk(tmp_path):
    code = """
import sys
from virtual_instrument_lab.__main__ import main
main(['--headless', '--output-dir', sys.argv[1]])
assert 'tkinter' not in sys.modules
"""
    completed = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True,
                               text=True, check=True, timeout=60)
    summary = json.loads(completed.stdout)
    assert summary["data_kind"] == DATA_KIND
    assert {path.name for path in tmp_path.iterdir()} == {"simulation.csv", "settings.json", "simulation.png"}


def test_invalid_save_does_not_replace_existing_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError):
        save_settings(replace(SimulationConfig(), sample_rate_hz=-1), path)
    assert path.read_text() == "keep me"


def test_missing_directory_and_wrong_image_format(result, tmp_path):
    with pytest.raises(OSError):
        export_csv(result, tmp_path / "missing" / "data.csv")
    with pytest.raises(ValueError, match="png"):
        export_figure(result, tmp_path / "plot.jpg")
