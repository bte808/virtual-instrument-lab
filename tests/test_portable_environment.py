from pathlib import Path

import pytest

from scripts.verify_portable import isolated_environment


@pytest.mark.parametrize("key", ["SYSTEMROOT", "SystemRoot", "systemroot"])
def test_windows_environment_survives_plain_dict_case_normalization(tmp_path, key):
    original = {key: r"C:\Windows", "Path": r"C:\Python312",
                "PythonPath": "external-source", "TCL_LIBRARY": "external-tcl"}
    isolated = isolated_environment(original, tmp_path, "Windows")
    assert isolated["PATH"] == r"C:\Windows\System32"
    assert "Path" not in isolated and "PythonPath" not in isolated
    assert "TCL_LIBRARY" not in isolated
    assert original["Path"] == r"C:\Python312"
    assert Path(isolated["MPLCONFIGDIR"]).parent == tmp_path


def test_windows_requires_system_root(tmp_path):
    with pytest.raises(RuntimeError, match="SystemRoot"):
        isolated_environment({}, tmp_path, "Windows")


def test_macos_drops_source_and_virtual_environment(tmp_path):
    isolated = isolated_environment({"PATH": "/some/venv/bin", "PYTHONHOME": "external",
                                     "VIRTUAL_ENV": "external"}, tmp_path, "Darwin")
    assert isolated["PATH"] == "/usr/bin:/bin"
    assert "PYTHONHOME" not in isolated and "VIRTUAL_ENV" not in isolated
