"""Rebuild or check the small, committed synthetic tutorial evidence set.

Run from an installed source checkout: python scripts/tutorial_materials.py --check
Only --write changes docs; --check uses temporary exports and tolerates numerical
roundoff, not changed parameters, stale answers, or replaced committed images.
"""

import argparse
import csv
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

import matplotlib
import numpy as np
from PIL import Image
import scipy

ROOT = Path(__file__).resolve().parents[1]
# Validate this checkout even if another copy is installed in the environment.
sys.path.insert(0, str(ROOT))

from virtual_instrument_lab import __version__
from virtual_instrument_lab.core import PRESETS, simulate
from virtual_instrument_lab.exports import DATA_KIND, export_csv, load_settings, save_settings
from virtual_instrument_lab.plotting import build_figure


DATA = ROOT / "docs" / "tutorial-data"
GUIDE = ROOT / "docs" / "tutorial.md"
CASES = {
    "clean_reference": ("Clean reference", {}),
    "buried_in_noise": ("Buried in noise", {}),
    "nearby_interference": ("Nearby interference", {}),
    "noise_short": ("Buried in noise", {"duration_s": 1.0}),
    "nearby_mismatch": ("Nearby interference", {"reference_frequency_hz": 49.0}),
}
SOURCES = ("core.py", "exports.py", "plotting.py", "__main__.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(path):
    # Git may check text out as CRLF on Windows; hash canonical UTF-8/LF text.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def close(actual, expected, name):
    """Absolute phase tolerance avoids false differences across +/-180 degrees."""
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        require(actual == expected, name + " changed")
    elif name.endswith("phase_deg"):
        require(abs((actual - expected + 180) % 360 - 180) <= 1e-6, name + " changed")
    elif name.endswith("_s"):
        require(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-10), name + " changed")
    elif isinstance(expected, int):
        require(actual == expected, name + " changed")
    else:
        require(math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-9), name + " changed")


def metrics(result):
    first = int(np.searchsorted(result.time_s, result.estimate_start_s))
    bin_index = int(np.argmin(abs(result.frequency_hz - result.config.frequency_hz)))
    require(abs(result.frequency_hz[bin_index] - result.config.frequency_hz) < 1e-10,
            "Tutorial expects a coherent main-signal FFT bin")
    return {
        "sample_count": len(result.time_s),
        "last_sample_s": float(result.time_s[-1]),
        "estimate_sample_count": len(result.time_s) - first,
        "estimate_start_s": result.estimate_start_s,
        "settling_time_s": result.settling_time_s,
        "settled": result.settled,
        "warnings": list(result.warnings),
        "x_v": result.estimate_x_v,
        "y_v": result.estimate_y_v,
        "amplitude_peak_v": result.estimate_amplitude_v,
        "phase_deg": result.estimate_phase_deg,
        "mean_instantaneous_amplitude_v": float(np.mean(result.amplitude_v[first:])),
        "main_bin_hz": float(result.frequency_hz[bin_index]),
        "input_main_bin_peak_v": float(result.input_spectrum_v[bin_index]),
        "filtered_main_bin_peak_v": float(result.filtered_spectrum_v[bin_index]),
    }


def check_csv(path, result, expected):
    with path.open(encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    metadata = dict(line[2:].rstrip().split("=", 1) for line in lines if line.startswith("# "))
    require(metadata["data_kind"] == DATA_KIND, "CSV lacks synthetic-data marker")
    require(json.loads(metadata["config"]) == asdict(result.config), "CSV settings changed")
    close(float(metadata["estimate_start_s"]), expected["estimate_start_s"], "CSV estimate_start_s")
    close(float(metadata["settling_time_s"]), expected["settling_time_s"], "CSV settling_time_s")
    require(metadata["settled"] == str(expected["settled"]).lower(), "CSV settled flag changed")
    rows = list(csv.DictReader(line for line in lines if not line.startswith("#")))
    require(len(rows) == expected["sample_count"], "CSV row count changed")
    columns = {
        "time_s": result.time_s, "clean_v": result.clean_v, "input_v": result.input_v,
        "filtered_v": result.filtered_v, "lockin_x_v": result.x_v, "lockin_y_v": result.y_v,
        "lockin_amplitude_peak_v": result.amplitude_v, "lockin_phase_deg": result.phase_deg,
        "after_startup": (result.time_s >= result.settling_time_s).astype(int),
    }
    require(set(rows[0]) == set(columns), "CSV columns changed")
    for key, values in columns.items():
        parsed = np.array([float(row[key]) if row[key] else np.nan for row in rows])
        np.testing.assert_allclose(parsed, values, rtol=1e-8, atol=1e-9, equal_nan=True,
                                   err_msg="CSV readback: " + key)
    first = int(np.searchsorted(result.time_s, expected["estimate_start_s"]))
    x = float(np.mean([float(row["lockin_x_v"]) for row in rows[first:]]))
    y = float(np.mean([float(row["lockin_y_v"]) for row in rows[first:]]))
    close(math.hypot(x, y), expected["amplitude_peak_v"], "CSV amplitude_peak_v")
    close(math.degrees(math.atan2(y, x)), expected["phase_deg"], "CSV phase_deg")


def png_info(path):
    with Image.open(path) as picture:
        picture.load()
        require(picture.format == "PNG", "Expected a PNG")
        require(picture.size == (1680, 1092), "Tutorial image dimensions changed")
        require(picture.info.get("Description") == "Synthetic simulation data. No hardware connected.",
                "PNG lacks synthetic-data metadata")
        return {"sha256": digest(path), "width": picture.width, "height": picture.height}


def block(slug, case):
    m = case["metrics"]
    status = "启动条件已满足" if m["settled"] else "**未充分稳定：临时估计**"
    phase = "未定义" if m["phase_deg"] is None else f'{m["phase_deg"]:.6f}°'
    lines = [
        f'合成记录 `{slug}`（seed = {case["config"]["seed"]}）：', "",
        "| 量 | 当前程序结果 |", "|---|---:|",
        f'| 样本数 / 最后采样时刻 | {m["sample_count"]} / {m["last_sample_s"]:.4f} s |',
        f'| 平均 X / 平均 Y | {m["x_v"]:.6f} / {m["y_v"]:.6f} V |',
        f'| 平均矢量幅值 R（峰值） | {m["amplitude_peak_v"]:.6f} V |',
        f"| 平均矢量相位 | {phase} |",
        f'| 启动阈值 / 估计区间起点 | {m["settling_time_s"]:.6f} / {m["estimate_start_s"]:.4f} s |',
        f'| 估计区间样本数 / 状态 | {m["estimate_sample_count"]} / {status} |',
    ]
    if slug == "clean_reference":
        lines.append(f'| {m["main_bin_hz"]:g} Hz 谱线：输入 / 低通后 | '
                     f'{m["input_main_bin_peak_v"]:.6f} / {m["filtered_main_bin_peak_v"]:.6f} V peak |')
    if slug in {"nearby_interference", "nearby_mismatch"}:
        lines.append(f'| 平均瞬时幅值 mean(R(t)) | {m["mean_instantaneous_amplitude_v"]:.6f} V |')
    if m["warnings"]:
        lines.extend(["", "程序警告："] + ["- " + warning for warning in m["warnings"]])
        lines.insert(lines.index("程序警告：") + 1, "")
    return "\n".join(lines)


def update_guide(text, cases):
    for slug, case in cases.items():
        start, end = f"<!-- tutorial-result:{slug}:start -->", f"<!-- tutorial-result:{slug}:end -->"
        pattern = re.escape(start) + r".*?" + re.escape(end)
        require(len(re.findall(pattern, text, flags=re.S)) == 1, "Missing/duplicate guide block: " + slug)
        text = re.sub(pattern, lambda _: start + "\n" + block(slug, case) + "\n" + end, text, flags=re.S)
    return text


def check_guide_links(text):
    # Detect swapped case pictures/settings even when both files are valid.
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    require(images == [f"tutorial-data/{slug}/simulation.png"
                       for slug, (_, overrides) in CASES.items() if not overrides],
            "Guide images are missing or in the wrong case order")
    settings = [link for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
                if link.endswith("/settings.json")]
    require(settings == [f"tutorial-data/{slug}/settings.json" for slug in
                         ("clean_reference", "buried_in_noise", "noise_short",
                          "nearby_interference", "nearby_mismatch")],
            "Guide settings links are missing or in the wrong case order")


def run(write):
    guide = GUIDE.read_text(encoding="utf-8")
    check_guide_links(guide)
    source_hashes = {name: source_digest(ROOT / "virtual_instrument_lab" / name) for name in SOURCES}
    manifest = {
        "schema_version": 1, "data_kind": DATA_KIND, "app_version": __version__,
        "generation_command": "python scripts/tutorial_materials.py --write",
        "program_source_hash_encoding": "UTF-8 with LF newlines",
        "program_source_sha256": source_hashes,
        "environment": {"python": platform.python_version(), "system": platform.system(),
                        "machine": platform.machine(), "numpy": np.__version__,
                        "scipy": scipy.__version__, "matplotlib": matplotlib.__version__,
                        "rng": type(np.random.default_rng(42).bit_generator).__name__},
        "comparison_tolerances": {"volts_atol": 1e-9, "volts_rtol": 1e-8,
                                  "phase_degrees_atol": 1e-6, "seconds_atol": 1e-10},
        "cases": {},
    }
    saved = None if write else json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    if saved:
        for name in ("schema_version", "data_kind", "app_version", "program_source_sha256",
                     "program_source_hash_encoding",
                     "comparison_tolerances"):
            require(saved[name] == manifest[name], "Regenerate tutorial after change: " + name)
        require(set(saved["cases"]) == set(CASES), "Tutorial cases changed")
    with tempfile.TemporaryDirectory(prefix="vil-tutorial-") as temporary:
        for slug, (preset, overrides) in CASES.items():
            config = replace(PRESETS[preset], **overrides)
            result = simulate(config)
            observed = metrics(result)
            directory = Path(temporary) / slug
            directory.mkdir()
            command = f'-m virtual_instrument_lab --headless --preset "{preset}" --output-dir output/tutorial/{slug}'
            if not overrides:
                require(".venv/bin/python " + command in guide, "Documented CLI changed: " + slug)
                completed = subprocess.run(
                    [sys.executable, "-m", "virtual_instrument_lab", "--headless", "--preset", preset,
                     "--output-dir", str(directory)], cwd=ROOT, check=True,
                    capture_output=True, text=True, encoding="utf-8", timeout=60)
                summary = json.loads(completed.stdout)
                for key in ("amplitude_peak_v", "phase_deg", "settled", "warnings"):
                    close(summary[key], observed[key], "CLI " + key)
                require(summary["data_kind"] == DATA_KIND and summary["preset"] == preset,
                        "CLI provenance changed")
            else:
                save_settings(config, directory / "settings.json")
                export_csv(result, directory / "simulation.csv")
            require(load_settings(directory / "settings.json") == config, "Settings readback changed")
            check_csv(directory / "simulation.csv", result, observed)
            case = {"preset": preset, "overrides": overrides, "config": asdict(config), "metrics": observed,
                    "generation": command if not overrides else "simulate + save_settings + export_csv"}
            if not overrides:
                figure = build_figure(result)
                case["figure"] = {**png_info(directory / "simulation.png"),
                                  "title": figure._suptitle.get_text(),
                                  "footer": figure._supxlabel.get_text()}
                figure.clear()
            manifest["cases"][slug] = case
            if saved:
                previous = saved["cases"][slug]
                for key in ("preset", "overrides", "config", "generation"):
                    require(previous[key] == case[key], f"{slug}: {key} changed")
                require(set(previous["metrics"]) == set(observed), slug + ": metric fields changed")
                for key, value in previous["metrics"].items():
                    close(observed[key], value, slug + ": " + key)
                require(load_settings(DATA / slug / "settings.json") == config, slug + ": saved settings changed")
                if "figure" in case:
                    for key, value in png_info(DATA / slug / "simulation.png").items():
                        require(previous["figure"][key] == value, slug + ": committed PNG changed")
                    for key in ("title", "footer"):
                        require(previous["figure"][key] == case["figure"][key], slug + ": figure text changed")
            print(f'{slug}: {observed["sample_count"]} CSV rows; R={observed["amplitude_peak_v"]:.6f} V peak; '
                  f'phase={observed["phase_deg"]:.6f} deg; settled={observed["settled"]}')
        if write:
            for slug, case in manifest["cases"].items():
                target = DATA / slug
                target.mkdir(parents=True, exist_ok=True)
                for filename in (["settings.json", "simulation.png"] if "figure" in case else ["settings.json"]):
                    shutil.copyfile(Path(temporary) / slug / filename, target / filename)
            (DATA / "results.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)
                                                + "\n", encoding="utf-8")
            GUIDE.write_text(update_guide(guide, manifest["cases"]), encoding="utf-8")
        else:
            require(guide == update_guide(guide, saved["cases"]), "Guide result blocks differ from saved evidence")
    print("Tutorial materials " + ("written." if write else "verified (no committed files changed)."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Regenerate tutorial evidence and result blocks")
    mode.add_argument("--check", action="store_true", help="Check committed evidence with temporary exports")
    args = parser.parse_args()
    try:
        run(args.write)
    except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Tutorial verification failed: {exc}\n")


if __name__ == "__main__":
    main()
