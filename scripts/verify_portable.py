"""Test the extracted native archive, outside the source tree and virtualenv."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_dir.resolve()
    (artifacts / "SELF_TEST.json").unlink(missing_ok=True)
    info = json.loads((artifacts / "BUILD_INFO.json").read_text(encoding="utf-8"))
    if os.environ.get("GITHUB_ACTIONS") == "true" and info["source_dirty"]:
        raise RuntimeError("CI review artifacts must come from a clean source commit")
    if info["system"] != platform.system() or info["machine"].lower() != platform.machine().lower():
        raise RuntimeError("A portable archive must be tested on its native OS and architecture")
    expected_hash, filename = (artifacts / "SHA256SUMS.txt").read_text().strip().split("  ", 1)
    if Path(filename).name != filename:
        raise RuntimeError("Checksum filename must be a basename")
    archive = artifacts / filename
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected_hash
    with tempfile.TemporaryDirectory(prefix="vil-portable-") as directory:
        root = Path(directory) / "Portable lab 中文 path"
        root.mkdir()
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as stream:
                # Only build-generated archives are accepted; reject traversal.
                for member in stream.namelist():
                    if Path(member).is_absolute() or ".." in Path(member).parts:
                        raise ValueError("Unsafe archive member")
                stream.extractall(root)
        else:
            with tarfile.open(archive) as stream:
                stream.extractall(root, filter="data")
        embedded_info = json.loads((root / "BUILD_INFO.json").read_text(encoding="utf-8"))
        if embedded_info != info:
            raise RuntimeError("Archive build metadata does not match its sidecar")
        executable = (root / "VirtualInstrumentLab.app" / "Contents" / "MacOS" / "VirtualInstrumentLab"
                      if platform.system() == "Darwin" else root / "VirtualInstrumentLab" / "VirtualInstrumentLab.exe")
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "TCL_LIBRARY", "TK_LIBRARY", "MPLBACKEND"):
            env.pop(key, None)
        env["PATH"] = (str(Path(env["SystemRoot"]) / "System32")
                       if platform.system() == "Windows" else "/usr/bin:/bin")
        env["MPLCONFIGDIR"] = str(root / "plot cache")
        env["PYTHONUTF8"] = "1"
        def invoke(*arguments):
            result = subprocess.run([str(executable), *arguments], cwd=root, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if result.returncode:
                raise RuntimeError("Bundled command failed: " + " ".join(arguments) + "\n" + result.stderr)
            return json.loads(result.stdout)
        diagnostic = invoke("--diagnostics")
        assert diagnostic["frozen"] is True, "Test must run the frozen app, not source Python"
        assert diagnostic["app_version"] == info["app_version"]
        output = root / "Export results 中文"
        result = invoke("--headless", "--preset", "Clean reference", "--output-dir", str(output))
        assert result["data_kind"] == "synthetic_simulation_no_hardware"
        assert abs(result["amplitude_peak_v"] - 1.0) < 0.002
        assert abs(result["phase_deg"] - 30.0) < 0.01
        with (output / "simulation.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(line for line in handle if not line.startswith("#")))
        assert len(rows) == 8000
        assert float(rows[-1]["time_s"]) == 3.9995
        settings = json.loads((output / "settings.json").read_text(encoding="utf-8"))
        assert settings["config"]["seed"] == 42
        from PIL import Image
        with Image.open(output / "simulation.png") as picture:
            picture.verify()
        gui = invoke("--smoke-test")
        assert gui["gui_smoke_passed"] and gui["presets"] == 3
        assert all(value is True for key, value in gui.items() if key != "presets")
        report = {"passed": True, "archive": archive.name, "sha256": expected_hash,
                  "source_commit": info["source_commit"], "source_dirty": info["source_dirty"],
                  "native_system": platform.system(), "native_machine": platform.machine(),
                  "diagnostics": diagnostic, "isolated_path": True,
                  "unicode_space_path": True, "csv_rows": len(rows),
                  "amplitude_peak_v": result["amplitude_peak_v"], "phase_deg": result["phase_deg"],
                  "settings_readback": True, "png_decode": True, "gui_smoke": gui}
    (artifacts / "SELF_TEST.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
