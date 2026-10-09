"""Build a native review artifact; never publishes a release or signs an identity."""

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DISTRIBUTIONS = (
    "numpy", "scipy", "matplotlib", "pillow", "contourpy", "cycler", "fonttools",
    "kiwisolver", "packaging", "pyparsing", "python-dateutil", "six",
)


def native_tag():
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if system == "Darwin" and machine == "arm64":
        return "macos-arm64"
    raise SystemExit("This recipe supports native Windows x64 and macOS arm64 only.")


def collect_licenses(target):
    """Preserve upstream notices, including bundled numerical-library notices."""
    target.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_DISTRIBUTIONS + ("pyinstaller",):
        dist = metadata.distribution(name)
        copied = 0
        for item in dist.files or ():
            if any(word in item.name.lower() for word in ("license", "copying", "notice")):
                source = Path(dist.locate_file(item))
                if source.is_file() and source.suffix.lower() not in (".py", ".pyc", ".so", ".pyd"):
                    # Keep hierarchy; avoid copying direct_url.json / local install paths.
                    relative = Path(*[part for part in item.parts if part not in ("..", ".")])
                    destination = target / name / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    copied += 1
        if not copied:
            raise RuntimeError("No upstream license found for " + name)
    # CPython's license file includes notices for its incorporated components.
    python_candidates = [Path(sys.base_prefix) / "LICENSE.txt",
                         Path(os.__file__).parent / "LICENSE.txt",
                         Path(sys.base_prefix) / "LICENSE"]
    python_license = next((path for path in python_candidates if path.is_file()), None)
    if python_license is None:
        raise RuntimeError("Cannot locate the installed Python license")
    shutil.copyfile(python_license, target / "PYTHON-LICENSE.txt")
    # Tcl/Tk support files may live outside the Python prefix on macOS.
    import tkinter
    interpreter = tkinter.Tcl()
    tcl_dir = Path(interpreter.eval("info library"))
    roots = [tcl_dir, tcl_dir.parent, Path(sys.base_prefix) / "tcl"]
    count = 0
    seen = set()
    for base in roots:
        if not base.is_dir():
            continue
        for pattern in ("license*", "*/license*", "*/*/license*"):
            for source in base.glob(pattern):
                if source.is_file() and source.resolve() not in seen:
                    seen.add(source.resolve())
                    shutil.copyfile(source, target / ("TCL-TK-" + str(count) + "-" + source.name))
                    count += 1
    # Some standalone Python builds omit these files; include official upstream
    # notices in all bundles as well as any notices carried by the installation.
    for source in (ROOT / "packaging" / "licenses").iterdir():
        if source.is_file():
            shutil.copyfile(source, target / source.name)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    tag = native_tag()
    sys.path.insert(0, str(ROOT))
    from virtual_instrument_lab import __version__
    dist_root = ROOT / "dist"
    artifacts = dist_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "SELF_TEST.json").unlink(missing_ok=True)
    # A task-local cache; do not modify the developer's global build cache.
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build" / "pyinstaller-cache")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(dist_root / "native"),
                    "--workpath", str(ROOT / "build" / "portable"),
                    str(ROOT / "packaging" / "virtual-instrument-lab.spec")],
                   cwd=ROOT, env=environment, check=True)
    stage = dist_root / ("portable-" + tag)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    app_name = "VirtualInstrumentLab.app" if tag.startswith("macos") else "VirtualInstrumentLab"
    shutil.copytree(dist_root / "native" / app_name, stage / app_name, symlinks=True)
    for source, destination in ((ROOT / "LICENSE", stage / "LICENSE"),
                                (ROOT / "packaging" / "PORTABLE_README.txt", stage / "PORTABLE_README.txt")):
        shutil.copyfile(source, destination)
    collect_licenses(stage / "THIRD_PARTY_LICENSES")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    info = {"app_version": __version__, "source_commit": commit, "source_dirty": dirty,
            "platform_tag": tag, "system": platform.system(), "machine": platform.machine(),
            "python_version": platform.python_version(), "pyinstaller_version": metadata.version("pyinstaller"),
            "dependencies": {name: metadata.version(name) for name in RUNTIME_DISTRIBUTIONS},
            "publisher_signed": False, "notarized": False,
            "macos_signature": "ad-hoc only" if tag.startswith("macos") else "not applicable",
            "data_kind": "synthetic_simulation_no_hardware"}
    (stage / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    stem = "portable-" + tag
    if tag.startswith("windows"):
        archive = Path(shutil.make_archive(str(artifacts / stem), "zip", root_dir=stage))
    else:
        archive = artifacts / (stem + ".tar.gz")
        def anonymous_owner(member):
            # Do not embed the building computer's local account identity.
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            return member
        with tarfile.open(archive, "w:gz") as stream:
            for child in sorted(stage.iterdir()):
                stream.add(child, arcname=child.name, filter=anonymous_owner)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (artifacts / "SHA256SUMS.txt").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    shutil.copyfile(stage / "BUILD_INFO.json", artifacts / "BUILD_INFO.json")
    print(json.dumps({"archive": archive.name, "sha256": digest, "platform_tag": tag}))


if __name__ == "__main__":
    main()
