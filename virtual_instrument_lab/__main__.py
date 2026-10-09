"""Desktop launcher and reproducible headless demonstration."""

import argparse
import json
from pathlib import Path
import platform
import sys

from . import __version__


def _diagnostics():
    """Report portable runtime versions without opening Tk or leaking paths."""
    import matplotlib
    import numpy
    import scipy

    try:
        import tkinter
    except ImportError as exc:
        if exc.name not in {"tkinter", "_tkinter"}:
            raise
        tk_version = None
    else:
        tk_version = str(tkinter.TkVersion)
    return {
        "frozen": bool(getattr(sys, "frozen", False)),
        "app_version": __version__,
        "python_version": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
        "matplotlib_version": matplotlib.__version__,
        "tk_version": tk_version,
    }


def main(argv=None):
    from .core import PRESETS, simulate
    parser = argparse.ArgumentParser(description="Synthetic virtual instrument lab; no hardware connected.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="Export a preset without a desktop")
    mode.add_argument("--smoke-test", action="store_true", help="Exercise and close the Tk interface")
    mode.add_argument("--version", action="store_true", help="Print the application version")
    mode.add_argument("--diagnostics", action="store_true", help="Print runtime versions without opening a window")
    parser.add_argument("--preset", choices=list(PRESETS), default=next(iter(PRESETS)))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    if args.version:
        print("virtual-instrument-lab " + __version__)
        return 0
    if args.diagnostics:
        print(json.dumps(_diagnostics(), indent=2))
        return 0
    if args.headless:
        from .exports import export_csv, export_figure, save_settings
        result = simulate(PRESETS[args.preset])
        try:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            export_csv(result, args.output_dir / "simulation.csv")
            save_settings(result.config, args.output_dir / "settings.json")
            export_figure(result, args.output_dir / "simulation.png")
        except OSError as exc:
            parser.error("Cannot write exports to '{}': {}".format(
                args.output_dir, exc.strerror or str(exc)))
        print(json.dumps({"data_kind": "synthetic_simulation_no_hardware", "preset": args.preset,
                          "amplitude_peak_v": result.estimate_amplitude_v,
                          "phase_deg": result.estimate_phase_deg, "settled": result.settled,
                          "warnings": result.warnings, "output_dir": str(args.output_dir)}, indent=2))
        return 0
    if args.smoke_test:
        from .app import run_smoke_test
        report = run_smoke_test()
        print(json.dumps({"gui_smoke_passed": True, **report}, indent=2))
        return 0
    from .app import main as gui_main
    gui_main(preset_name=args.preset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
