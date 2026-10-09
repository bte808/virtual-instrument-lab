"""Tk desktop workbench for synthetic, offline measurement experiments."""

from dataclasses import asdict
import math
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from .core import PRESETS, SimulationConfig, simulate, validate_config
from .exports import export_csv, export_figure, load_settings, save_settings
from .plotting import build_figure


_BACKGROUND = "#eef3f7"
_INK = "#182e42"
_MUTED = "#526779"
_ACCENT = "#087f8c"
_WARNING = "#95540b"

_FIELD_GROUPS = (
    (
        "1  Acquisition",
        "Sampling sets the time and frequency resolution.",
        (
            ("sample_rate_hz", "Sample rate (Hz)"),
            ("duration_s", "Duration (s)"),
            ("seed", "Noise seed"),
        ),
    ),
    (
        "2  Source signal",
        "A cos(2πft + φ); A is peak amplitude.",
        (
            ("amplitude_v", "Amplitude (V peak)"),
            ("frequency_hz", "Frequency (Hz)"),
            ("phase_deg", "Phase (degrees)"),
            ("dc_offset_v", "DC offset (V)"),
        ),
    ),
    (
        "3  Noise & interference",
        "Seeded Gaussian noise + one cosine interferer.",
        (
            ("noise_std_v", "Noise standard dev. (V)"),
            ("interference_amplitude_v", "Interference (V peak)"),
            ("interference_frequency_hz", "Interference freq. (Hz)"),
            ("interference_phase_deg", "Interference phase (°)"),
        ),
    ),
    (
        "4  Causal filters & reference",
        "One RC stage for input; two for lock-in X and Y.",
        (
            ("lowpass_cutoff_hz", "Input cutoff (Hz)"),
            ("reference_frequency_hz", "Reference (Hz)"),
            ("lockin_cutoff_hz", "Lock-in cutoff (Hz)"),
        ),
    ),
)
_FIELD_LABELS = {
    name: label
    for _heading, _description, fields in _FIELD_GROUPS
    for name, label in fields
}


class LabApp:
    """A synchronous Tk interface; numerical work lives in :mod:`core`."""

    def __init__(self, root: tk.Tk, preset_name: Optional[str] = None) -> None:
        self.root = root
        self.result = None
        self._figure = None
        self._figure_canvas = None
        self._navigation = None
        self.config_vars = {
            name: tk.StringVar(root, value=str(value))
            for name, value in asdict(SimulationConfig()).items()
        }
        self.preset_var = tk.StringVar(
            root, value=preset_name if preset_name is not None else next(iter(PRESETS))
        )
        self.status_var = tk.StringVar(root, value="Ready to simulate.")
        self.amplitude_var = tk.StringVar(root, value="—")
        self.phase_var = tk.StringVar(root, value="—")
        self.quadrature_var = tk.StringVar(root, value="—")
        self.settling_var = tk.StringVar(root, value="—")
        self.warning_var = tk.StringVar(root, value="")

        root.title("Virtual Instrument Lab — synthetic simulation")
        width = min(1420, max(1000, root.winfo_screenwidth() - 60))
        height = min(980, max(700, root.winfo_screenheight() - 100))
        root.geometry("{}x{}".format(width, height))
        root.minsize(1000, 700)
        root.configure(background=_BACKGROUND)
        self._configure_style()
        self._build_ui()
        root.bind("<Control-Return>", self.run_simulation)
        if sys.platform == "darwin":
            root.bind("<Command-Return>", self.run_simulation)
        root.bind("<MouseWheel>", self._scroll_controls, add="+")
        root.bind("<Button-4>", self._scroll_controls, add="+")
        root.bind("<Button-5>", self._scroll_controls, add="+")
        self.apply_preset()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=_BACKGROUND)
        style.configure("TLabel", background=_BACKGROUND, foreground=_INK)
        style.configure("TButton", padding=(10, 7))
        style.configure("TEntry", padding=4)
        style.configure("TCombobox", padding=4)
        style.configure("Panel.TFrame", background="white")
        style.configure("Panel.TLabel", background="white", foreground=_INK)
        style.configure(
            "Muted.TLabel", background="white", foreground=_MUTED, font=("Helvetica", 10)
        )
        style.configure(
            "Section.TLabel", background="white", foreground=_INK,
            font=("Helvetica", 12, "bold"),
        )
        style.configure(
            "Metric.TLabel", background="white", foreground=_ACCENT,
            font=("Helvetica", 18, "bold"),
        )
        style.configure(
            "MetricSmall.TLabel", background="white", foreground=_INK,
            font=("Helvetica", 12, "bold"),
        )
        style.configure(
            "Run.TButton", background=_ACCENT, foreground="white",
            font=("Helvetica", 12, "bold"), padding=(14, 10),
        )
        style.map("Run.TButton", background=[("active", "#066773")])

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        header = tk.Frame(self.root, background=_INK, padx=20, pady=14)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(
            header, text="Virtual Instrument Lab", background=_INK,
            foreground="white", font=("Helvetica", 23, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header, text="Explore signals, filtering and dual-phase lock-in detection",
            background=_INK, foreground="#c5d9e8", font=("Helvetica", 11), anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            header, text="SYNTHETIC DATA\nOFFLINE · NO HARDWARE", justify="right",
            background=_INK, foreground="#8fe4db", font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=1, rowspan=2, padx=(20, 0))

        body = ttk.Frame(self.root, padding=(12, 12, 12, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self._build_controls(body)
        self._build_results(body)
        ttk.Label(
            self.root, textvariable=self.status_var, foreground=_MUTED,
            padding=(16, 8), anchor="w",
        ).grid(row=2, column=0, sticky="ew")

    def _build_controls(self, body: ttk.Frame) -> None:
        sidebar = ttk.Frame(body, style="Panel.TFrame", width=330)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)
        preset = ttk.Frame(sidebar, style="Panel.TFrame", padding=12)
        preset.grid(row=0, column=0, columnspan=2, sticky="ew")
        preset.columnconfigure(0, weight=1)
        ttk.Label(preset, text="TEACHING PRESETS", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.preset_combo = ttk.Combobox(
            preset, textvariable=self.preset_var, values=tuple(PRESETS), state="readonly"
        )
        self.preset_combo.grid(row=1, column=0, sticky="ew")
        self.preset_combo.bind("<<ComboboxSelected>>", self.apply_preset)
        ttk.Label(
            preset, text="Choose an experiment, then adjust its parameters.",
            style="Muted.TLabel", wraplength=296,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.controls_canvas = tk.Canvas(
            sidebar, background="white", highlightthickness=0, borderwidth=0, width=307
        )
        self.controls_canvas.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.controls_canvas.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.controls_canvas.configure(yscrollcommand=scroll.set)
        self.controls_frame = ttk.Frame(self.controls_canvas, style="Panel.TFrame", padding=12)
        window = self.controls_canvas.create_window((0, 0), window=self.controls_frame, anchor="nw")
        self.controls_frame.bind(
            "<Configure>",
            lambda _event: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")),
        )
        self.controls_canvas.bind(
            "<Configure>", lambda event: self.controls_canvas.itemconfigure(window, width=event.width)
        )
        self.controls_frame.columnconfigure(0, weight=1)
        self.entries = {}
        row = 0
        for heading, description, fields in _FIELD_GROUPS:
            ttk.Label(self.controls_frame, text=heading, style="Section.TLabel").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(8 if row else 0, 4)
            )
            row += 1
            ttk.Label(
                self.controls_frame, text=description, style="Muted.TLabel", wraplength=285
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
            row += 1
            for name, label in fields:
                ttk.Label(self.controls_frame, text=label, style="Panel.TLabel").grid(
                    row=row, column=0, sticky="w", padx=(0, 6), pady=4
                )
                entry = ttk.Entry(self.controls_frame, textvariable=self.config_vars[name], width=10)
                entry.grid(row=row, column=1, sticky="e", pady=4)
                self.entries[name] = entry
                row += 1
            ttk.Separator(self.controls_frame).grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=(10, 4)
            )
            row += 1
        ttk.Label(
            self.controls_frame,
            text="Lock-in uses the raw input.\nX = LP(2x cos reference)\nY = LP(−2x sin reference)\nR = hypot(X, Y), peak volts\nφ = atan2(Y, X)",
            style="Muted.TLabel", justify="left", wraplength=285,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 4))
        self.run_button = ttk.Button(
            sidebar, text="Run simulation", command=self.run_simulation, style="Run.TButton"
        )
        self.run_button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)

    def _build_results(self, body: ttk.Frame) -> None:
        output = ttk.Frame(body)
        output.grid(row=0, column=1, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(2, weight=1)
        metrics = ttk.Frame(output, style="Panel.TFrame", padding=12)
        metrics.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            metrics.columnconfigure(column, weight=1, uniform="metrics")
        for column, (label, variable, style) in enumerate((
            ("LOCK-IN AMPLITUDE", self.amplitude_var, "Metric.TLabel"),
            ("LOCK-IN PHASE", self.phase_var, "Metric.TLabel"),
            ("MEAN QUADRATURES", self.quadrature_var, "MetricSmall.TLabel"),
        )):
            ttk.Label(metrics, text=label, style="Muted.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0, 12)
            )
            ttk.Label(metrics, textvariable=variable, style=style).grid(
                row=1, column=column, sticky="w", padx=(0, 12), pady=(6, 0)
            )
        settling_label = ttk.Label(
            metrics, textvariable=self.settling_var, style="Muted.TLabel", wraplength=600
        )
        settling_label.grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(9, 0)
        )
        metrics.bind(
            "<Configure>", lambda event: settling_label.configure(wraplength=max(250, event.width - 28))
        )

        actions = ttk.Frame(output, padding=(0, 9, 0, 9))
        actions.grid(row=1, column=0, sticky="ew")
        for index, (text, command) in enumerate((
            ("Export CSV…", self.export_csv),
            ("Save settings…", self.save_settings),
            ("Load settings…", self.load_settings),
            ("Export plot…", self.export_figure),
        )):
            ttk.Button(actions, text=text, command=command).grid(
                row=0, column=index, padx=(0, 6), sticky="w"
            )
        self.plot_frame = ttk.Frame(output, style="Panel.TFrame")
        self.plot_frame.grid(row=2, column=0, sticky="nsew")
        self.plot_frame.columnconfigure(0, weight=1)
        self.plot_frame.rowconfigure(0, weight=1)
        self.warning_label = ttk.Label(
            output, textvariable=self.warning_var, foreground=_WARNING,
            background="#fff4dd", padding=(12, 9), justify="left", wraplength=650,
        )
        self.warning_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        output.bind(
            "<Configure>",
            lambda event: self.warning_label.configure(wraplength=max(250, event.width - 28)),
        )

    def _scroll_controls(self, event) -> None:
        widget_name = str(event.widget)
        if not (
            event.widget == self.controls_canvas
            or widget_name.startswith(str(self.controls_frame))
        ):
            return
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return
            # macOS sends small deltas; Windows commonly sends multiples of 120.
            units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.controls_canvas.yview_scroll(units, "units")

    def _read_config(self) -> SimulationConfig:
        values = {}
        for name, variable in self.config_vars.items():
            try:
                raw = variable.get().strip()
                values[name] = int(raw) if name == "seed" else float(raw)
            except ValueError as exc:
                self.entries[name].focus_set()
                self.entries[name].selection_range(0, tk.END)
                expected = "a whole number" if name == "seed" else "a number"
                raise ValueError("{} must be {}.".format(_FIELD_LABELS[name], expected)) from exc
        config = SimulationConfig(**values)
        validate_config(config)
        return config

    def _set_config(self, config: SimulationConfig) -> None:
        for name, value in asdict(config).items():
            self.config_vars[name].set(str(value))

    def _error(self, title: str, error: Exception) -> None:
        self.status_var.set("{}: {}".format(title, error))
        messagebox.showerror(title, str(error), parent=self.root)

    def apply_preset(self, _event=None) -> None:
        name = self.preset_var.get()
        if name not in PRESETS:
            self._error("Unknown preset", ValueError("Choose one of the three teaching presets."))
            return
        self._set_config(PRESETS[name])
        self.run_simulation()

    def run_simulation(self, _event=None) -> bool:
        try:
            config = self._read_config()
        except (ValueError, TypeError, OverflowError) as exc:
            self._error("Invalid parameters", exc)
            return False
        self.status_var.set("Computing synthetic signals…")
        self.root.configure(cursor="watch")
        self.run_button.configure(state="disabled")
        self.root.update_idletasks()
        try:
            result = simulate(config)
            figure = build_figure(result)
            self._display_figure(figure)
            self.result = result
            self._display_estimates()
            if PRESETS.get(self.preset_var.get()) != config:
                self.preset_var.set("Custom settings")
            self.status_var.set(
                "Synthetic simulation complete · {:,} samples · data/plot exports use this run.".format(
                    len(result.time_s)
                )
            )
            return True
        except (ValueError, TypeError, OverflowError, RuntimeError) as exc:
            self._error("Simulation failed", exc)
            return False
        finally:
            self.root.configure(cursor="")
            self.run_button.configure(state="normal")

    def _dispose_figure(self) -> None:
        canvas = self._figure_canvas
        figure = self._figure
        navigation = self._navigation

        def cancel_pending_callbacks() -> None:
            if canvas is None:
                return
            # Embedded canvases have no FigureManagerTk to cancel these jobs.
            # Do so before destroying their Tcl widget, as that manager does.
            for attribute in ("_idle_draw_id", "_event_loop_id"):
                callback_id = getattr(canvas, attribute, None)
                if callback_id is not None:
                    canvas.get_tk_widget().after_cancel(callback_id)
                    setattr(canvas, attribute, None)

        cancel_pending_callbacks()
        if figure is not None:
            # Figure.clear() can call toolbar.update(); its buttons must still
            # exist here. Clearing can also schedule a new idle draw.
            figure.clear()
        cancel_pending_callbacks()
        if navigation is not None:
            navigation.destroy()
        if canvas is not None:
            canvas.get_tk_widget().destroy()
            canvas.toolbar = None
            canvas.figure = None
        if navigation is not None:
            navigation.canvas = None
        if figure is not None:
            figure.set_canvas(None)
        self._navigation = None
        self._figure_canvas = None
        self._figure = None

    def _display_figure(self, figure) -> None:
        self._dispose_figure()
        self._figure = figure
        self._figure_canvas = FigureCanvasTkAgg(figure, master=self.plot_frame)
        self._figure_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._navigation = NavigationToolbar2Tk(
            self._figure_canvas, self.plot_frame, pack_toolbar=False
        )
        self._navigation.grid(row=1, column=0, sticky="ew")
        self._figure_canvas.draw()

    def _display_estimates(self) -> None:
        result = self.result
        self.amplitude_var.set("{:.5g} V peak".format(result.estimate_amplitude_v))
        phase = result.estimate_phase_deg
        self.phase_var.set(
            "Undefined" if phase is None or not math.isfinite(phase)
            else "{:+.3f}°".format(phase)
        )
        self.quadrature_var.set(
            "X  {:+.5g} V\nY  {:+.5g} V".format(result.estimate_x_v, result.estimate_y_v)
        )
        if result.settled:
            self.settling_var.set(
                "Startup criterion met · averaging from {:.3g} s · marker at {:.3g} s".format(
                    result.estimate_start_s, result.settling_time_s
                )
            )
        else:
            self.settling_var.set(
                "PROVISIONAL — not fully settled · last 20% estimate · startup marker {:.3g} s".format(
                    result.settling_time_s
                )
            )
        notices = list(result.warnings)
        notices.append(
            "Synthetic simulation only; no connected hardware or real measurement. "
            "Startup criterion is not an accuracy guarantee."
        )
        self.warning_var.set("\n".join(notices))

    def _output_path(self, title: str, filename: str, extension: str, description: str) -> Optional[str]:
        return filedialog.asksaveasfilename(
            parent=self.root, title=title, initialfile=filename,
            defaultextension=extension, filetypes=[(description, "*" + extension)],
        ) or None

    def export_csv(self) -> None:
        if self.result is None:
            return
        path = self._output_path("Export synthetic data", "synthetic-data.csv", ".csv", "CSV data")
        if path:
            try:
                export_csv(self.result, path)
                self.status_var.set("Exported synthetic data: {}".format(Path(path).name))
            except (OSError, ValueError) as exc:
                self._error("CSV export failed", exc)

    def save_settings(self) -> None:
        try:
            config = self._read_config()
        except (ValueError, TypeError, OverflowError) as exc:
            self._error("Invalid parameters", exc)
            return
        path = self._output_path("Save current controls", "lab-settings.json", ".json", "JSON settings")
        if path:
            try:
                save_settings(config, path)
                self.status_var.set("Saved current controls: {}".format(Path(path).name))
            except (OSError, ValueError) as exc:
                self._error("Settings save failed", exc)

    def load_settings(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Load experiment settings", filetypes=[("JSON settings", "*.json")]
        )
        if path:
            try:
                config = load_settings(path)
                validate_config(config)
            except (OSError, ValueError, TypeError) as exc:
                self._error("Settings load failed", exc)
                return
            self._set_config(config)
            self.preset_var.set("Imported settings")
            if self.run_simulation():
                self.status_var.set("Loaded and simulated: {}".format(Path(path).name))

    def export_figure(self) -> None:
        if self.result is None:
            return
        path = self._output_path("Export synthetic plots", "synthetic-plots.png", ".png", "PNG image")
        if path:
            try:
                export_figure(self.result, path)
                self.status_var.set("Exported synthetic plots: {}".format(Path(path).name))
            except (OSError, ValueError) as exc:
                self._error("Plot export failed", exc)


def run_smoke_test() -> dict:
    """Exercise Tk callbacks with isolated files and no interactive dialogs.

    This still requires a working graphical Tk installation. It withdraws only
    the window it creates and never interacts with another application's UI.
    """
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    root = tk.Tk()
    root.withdraw()
    try:
        with patch(__name__ + ".messagebox.showerror") as showerror:
            app = LabApp(root)
            root.update_idletasks()
            assert set(app.config_vars) == set(asdict(SimulationConfig()))
            assert app.result is not None
            for name, config in PRESETS.items():
                app.preset_var.set(name)
                app.apply_preset()
                assert app.result.config == config, name
                assert app._figure_canvas.get_tk_widget().winfo_exists()
            assert not showerror.called, "Valid presets produced an error"

            previous = app.result
            app.config_vars["sample_rate_hz"].set("not-a-number")
            assert app.run_simulation() is False
            assert showerror.call_count == 1
            assert app.result is previous, "Invalid input replaced the last valid run"
            app.config_vars["sample_rate_hz"].set(str(previous.config.sample_rate_hz))
            assert app.run_simulation() is True
            assert "complete" in app.status_var.get().lower()

            # All-zero input must not present a made-up phase angle.
            for field in ("amplitude_v", "dc_offset_v", "noise_std_v", "interference_amplitude_v"):
                app.config_vars[field].set("0")
            assert app.run_simulation() is True
            assert app.result.estimate_phase_deg is None
            assert "undefined" in app.phase_var.get().lower()

            with TemporaryDirectory(prefix="vil-gui-smoke-") as temp_dir:
                paths = {ext: Path(temp_dir) / ("roundtrip." + ext) for ext in ("csv", "json", "png")}
                for extension, callback in (
                    ("csv", app.export_csv), ("json", app.save_settings), ("png", app.export_figure)
                ):
                    with patch(__name__ + ".filedialog.asksaveasfilename", return_value=str(paths[extension])):
                        callback()
                    assert paths[extension].stat().st_size > 0, extension
                saved = load_settings(paths["json"])
                assert saved == app.result.config
                assert paths["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                app.config_vars["amplitude_v"].set("7")
                with patch(__name__ + ".filedialog.askopenfilename", return_value=str(paths["json"])):
                    app.load_settings()
                assert app.result.config == saved
                assert app.config_vars["amplitude_v"].get() == str(saved.amplitude_v)

                # Cancelled file dialogs preserve the current result and do no work.
                previous = app.result
                with patch(__name__ + ".filedialog.asksaveasfilename", return_value=""), patch(
                    __name__ + ".filedialog.askopenfilename", return_value=""
                ):
                    app.export_csv()
                    app.save_settings()
                    app.export_figure()
                    app.load_settings()
                assert app.result is previous
            assert showerror.call_count == 1, "An export or import showed an unexpected error"
            root.update_idletasks()
            return {
                "presets": len(PRESETS),
                "input_error_recovery": True,
                "undefined_phase": True,
                "csv_export": True,
                "png_export": True,
                "settings_roundtrip": True,
                "cancelled_dialogs": True,
            }
    finally:
        root.destroy()


def main(preset_name: Optional[str] = None) -> None:
    root = tk.Tk()
    LabApp(root, preset_name=preset_name)
    root.mainloop()


if __name__ == "__main__":
    main()
