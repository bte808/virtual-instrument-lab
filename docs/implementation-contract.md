# Implementation contract

An offline educational simulator; all data are synthetic and no hardware is connected.

## Shared Python API

`virtual_instrument_lab.core` exports frozen dataclass `SimulationConfig`, `SimulationResult`, `PRESETS` (dict of three English names to configs), `simulate(config)`, `validate_config(config)`, `single_sided_spectrum(values, sample_rate_hz)`, and `causal_lowpass(values, sample_rate_hz, cutoff_hz, stages=1)`.

Config fields (all floats except seed): `sample_rate_hz=2000.0`, `duration_s=4.0`, `amplitude_v=1.0`, `frequency_hz=50.0`, `phase_deg=30.0`, `dc_offset_v=0.2`, `noise_std_v=0.3`, `interference_amplitude_v=0.4`, `interference_frequency_hz=120.0`, `interference_phase_deg=0.0`, `lowpass_cutoff_hz=80.0`, `reference_frequency_hz=50.0`, `lockin_cutoff_hz=2.0`, `seed=42`.

Result fields: `config`, `time_s`, `clean_v` (signal plus DC), `input_v` (clean + seeded Gaussian noise + interference), `filtered_v`, `frequency_hz`, `input_spectrum_v`, `filtered_spectrum_v`, `x_v`, `y_v`, `amplitude_v`, `phase_deg` (NaN when undefined), `estimate_x_v`, `estimate_y_v`, `estimate_amplitude_v`, `estimate_phase_deg` (None when undefined), `settling_time_s`, `settled` (bool), `estimate_start_s`, `warnings` (tuple of strings).

Sampling uses N=round(fs*duration) and t=arange(N)/fs, no endpoint duplication; reject noninteger fs*duration (within numeric tolerance), N<16 or N>1,000,000. fs>0, duration>0, amplitudes/noise>=0, all values finite, cutoff in (0,fs/2), signal/interference/reference frequencies in (0,fs/2), seed integer 0..2**32-1. Peak input signal A*cos(2*pi*f*t+phase); interference uses same cosine convention. DC signed. Signal/phase and voltage magnitudes bounded to safe numerical ranges (document bounds).

Causal low pass: one RC stage with r=exp(-2*pi*fc/fs), b=[1-r], a=[1,-r], zero initial state, applied with scipy.signal.lfilter. Input filter uses one stage; lock-in uses two cascaded stages. X=LP2(2*input*cos(reference)), Y=LP2(-2*input*sin(reference)). Mixing always uses raw input. FFT rectangular-window single-sided peak amplitudes = abs(rfft)/N; double interior bins only, including final bin only when N odd; DC and even-N Nyquist not doubled.

Conservative startup marker: max(7/(2*pi*lowpass_fc),10/(2*pi*lockin_fc)). `settled` requires at least three reference cycles after this marker. Estimate is mean X,Y over the stable portion when settled; otherwise last 20% as provisional. R=hypot(mean X,mean Y), phase=atan2(mean Y,mean X) in degrees; undefined near zero (document numerical threshold). Marker is startup criterion, not an accuracy guarantee; mismatched reference and noise/bandwidth can affect estimate. Show time-series transients.

## Application modules

`exports.py`: `save_settings(config, path)`, `load_settings(path)->config`, `export_csv(result,path)`, `export_figure(result,path)` returning Path. CSV contains all time-domain fields and synthetic-data metadata. JSON strict versioned schema. All filenames accepted as pathlib Path or string. PNG image supports Agg without Tk.

`plotting.py`: `build_figure(result)` returns Matplotlib Figure showing input/clean/filtered time trace, single-sided amplitude spectrum, X/Y transient, and amplitude/phase transient; synthetic-data label, startup shading/marker and provisional status.

`app.py`: `LabApp(root)` with `config_vars` dict of Tk StringVar, `preset_var`, `apply_preset()`, `run_simulation()` (validation errors shown without crashing), `result`, `status_var`, `export_csv()`, `save_settings()`, `load_settings()`, `export_figure()` with standard file dialogs. UI must keep readable controls and scrollable input area, show startup/mismatch warnings and undefined phase. `main()`.

CLI in `__main__.py`: default launches app, `--headless --preset NAME --output-dir PATH` exports CSV, settings JSON, PNG and prints estimates. `--smoke-test` starts Tk, applies all presets, tests invalid input error recovery without blocking messageboxes, closes cleanly. GUI smoke will be run separately from mandatory numerical/export tests.

Support Python >=3.9 for this available Mac environment; documented recommended Python 3.11/3.12 with Tk 8.6 on Windows/macOS. No hardware/network runtime dependency.
