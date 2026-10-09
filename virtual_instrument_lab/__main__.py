"""Desktop launcher and reproducible headless demonstration."""

import argparse
import json
from pathlib import Path


def main(argv=None):
    from .core import PRESETS, simulate
    parser = argparse.ArgumentParser(description="Synthetic virtual instrument lab; no hardware connected.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="Export a preset without a desktop")
    mode.add_argument("--smoke-test", action="store_true", help="Exercise and close the Tk interface")
    parser.add_argument("--preset", choices=list(PRESETS), default=next(iter(PRESETS)))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    if args.headless:
        from .exports import export_csv, export_figure, save_settings
        result = simulate(PRESETS[args.preset])
        args.output_dir.mkdir(parents=True, exist_ok=True)
        export_csv(result, args.output_dir / "simulation.csv")
        save_settings(result.config, args.output_dir / "settings.json")
        export_figure(result, args.output_dir / "simulation.png")
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
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
