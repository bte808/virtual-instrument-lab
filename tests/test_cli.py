"""Portable launcher behavior that does not need a graphical session."""

import builtins
import errno
import json
import platform
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from virtual_instrument_lab import __version__
from virtual_instrument_lab.__main__ import main
from virtual_instrument_lab import exports


def test_version_matches_package_and_does_not_load_tk(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "virtual-instrument-lab " + __version__


@pytest.mark.parametrize("first,second", [
    ("--version", "--headless"),
    ("--headless", "--diagnostics"),
    ("--diagnostics", "--smoke-test"),
    ("--smoke-test", "--version"),
    ("--version", "--diagnostics"),
])
def test_modes_are_mutually_exclusive(first, second, capsys):
    with pytest.raises(SystemExit) as error:
        main([first, second])
    assert error.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_diagnostics_reports_versions_without_a_tk_root_or_paths(monkeypatch, capsys):
    root = Mock(side_effect=AssertionError("Diagnostics must not create Tk windows"))
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(TkVersion=8.6, Tk=root))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert main(["--diagnostics"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {
        "frozen", "app_version", "python_version", "system", "machine",
        "numpy_version", "scipy_version", "matplotlib_version", "tk_version",
    }
    assert report["frozen"] is True
    assert report["app_version"] == __version__
    assert report["python_version"] == platform.python_version()
    assert report["system"] == platform.system()
    assert report["machine"] == platform.machine()
    assert report["tk_version"] == "8.6"
    assert all(report[key] for key in ("numpy_version", "scipy_version", "matplotlib_version"))
    assert all("/" not in value and "\\" not in value for value in report.values() if isinstance(value, str))
    root.assert_not_called()


def test_diagnostics_reports_unavailable_tk_as_null(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert main(["--diagnostics"]) == 0
    assert json.loads(capsys.readouterr().out)["tk_version"] is None


def test_headless_has_no_tk_import_and_supports_unicode_spaces(tmp_path, capsys, monkeypatch):
    real_import = builtins.__import__

    def reject_tk_import(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter.") or name == "_tkinter":
            raise AssertionError("Headless mode must not import Tk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_tk_import)
    directory = tmp_path / "教学 输出目录"
    assert main(["--headless", "--preset", "Clean reference", "--output-dir", str(directory)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["preset"] == "Clean reference"
    assert report["data_kind"] == "synthetic_simulation_no_hardware"
    assert {item.name for item in directory.iterdir()} == {"simulation.csv", "settings.json", "simulation.png"}
    assert (directory / "simulation.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_headless_directory_collision_has_concise_error(tmp_path, capsys):
    target = tmp_path / "existing file"
    target.write_text("preserve this file", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["--headless", "--output-dir", str(target)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "Cannot write exports" in output.err
    assert "Traceback" not in output.err
    assert not output.out
    assert target.read_text(encoding="utf-8") == "preserve this file"


def test_headless_permission_error_has_status_two(tmp_path, capsys, monkeypatch):
    def fail_write(*_args):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(exports, "export_csv", fail_write)
    with pytest.raises(SystemExit) as error:
        main(["--headless", "--output-dir", str(tmp_path)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "Cannot write exports" in output.err
    assert "Permission denied" in output.err
    assert not output.out


def test_headless_does_not_swallow_programming_errors(tmp_path, monkeypatch):
    def broken_export(*_args):
        raise RuntimeError("unexpected implementation failure")

    monkeypatch.setattr(exports, "export_csv", broken_export)
    with pytest.raises(RuntimeError, match="unexpected implementation failure"):
        main(["--headless", "--output-dir", str(tmp_path)])


def test_gui_receives_the_requested_preset_without_starting_tk(monkeypatch):
    gui_main = Mock()
    monkeypatch.setitem(sys.modules, "virtual_instrument_lab.app", SimpleNamespace(main=gui_main))
    assert main(["--preset", "Buried in noise"]) == 0
    gui_main.assert_called_once_with(preset_name="Buried in noise")
