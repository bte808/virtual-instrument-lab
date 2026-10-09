"""Deterministic synthetic acquisition and causal educational signal processing.

Voltages and amplitudes use volts; sinusoidal amplitudes and FFT bins are peak,
not RMS. Filters begin at rest, so their startup transient is part of the data.
No function in this module accesses hardware, files, the network, or the GUI.
"""

from dataclasses import dataclass, fields
import math
from numbers import Integral, Real
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.signal import lfilter


MAX_SAMPLES = 1_000_000
MAX_VOLTAGE_V = 1_000_000.0
MAX_PHASE_DEG = 360_000.0
PHASE_ZERO_RELATIVE = 1e-10


@dataclass(frozen=True)
class SimulationConfig:
    sample_rate_hz: float = 2000.0
    duration_s: float = 4.0
    amplitude_v: float = 1.0
    frequency_hz: float = 50.0
    phase_deg: float = 30.0
    dc_offset_v: float = 0.2
    noise_std_v: float = 0.3
    interference_amplitude_v: float = 0.4
    interference_frequency_hz: float = 120.0
    interference_phase_deg: float = 0.0
    lowpass_cutoff_hz: float = 80.0
    reference_frequency_hz: float = 50.0
    lockin_cutoff_hz: float = 2.0
    seed: int = 42


@dataclass(frozen=True)
class SimulationResult:
    config: SimulationConfig
    time_s: np.ndarray
    clean_v: np.ndarray
    input_v: np.ndarray
    filtered_v: np.ndarray
    frequency_hz: np.ndarray
    input_spectrum_v: np.ndarray
    filtered_spectrum_v: np.ndarray
    x_v: np.ndarray
    y_v: np.ndarray
    amplitude_v: np.ndarray
    phase_deg: np.ndarray
    estimate_x_v: float
    estimate_y_v: float
    estimate_amplitude_v: float
    estimate_phase_deg: Optional[float]
    settling_time_s: float
    settled: bool
    estimate_start_s: float
    warnings: Tuple[str, ...]


PRESETS: Dict[str, SimulationConfig] = {
    "Clean reference": SimulationConfig(
        dc_offset_v=0.0, noise_std_v=0.0, interference_amplitude_v=0.0
    ),
    "Buried in noise": SimulationConfig(
        duration_s=6.0, amplitude_v=0.2, phase_deg=-45.0,
        dc_offset_v=0.4, noise_std_v=2.0, interference_amplitude_v=0.6,
        lockin_cutoff_hz=1.0,
    ),
    "Nearby interference": SimulationConfig(
        duration_s=8.0, phase_deg=60.0, noise_std_v=0.1,
        interference_amplitude_v=0.8, interference_frequency_hz=53.0,
        interference_phase_deg=-20.0, lockin_cutoff_hz=1.0,
    ),
}


def _finite_real(value: float, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number.") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _sample_rate(sample_rate_hz: float) -> float:
    rate = _finite_real(sample_rate_hz, "sample_rate_hz")
    if not 1e-6 <= rate <= 1e9:
        raise ValueError("sample_rate_hz must be between 1e-6 and 1e9 Hz.")
    return rate


def _filter_coefficient(sample_rate_hz: float, cutoff_hz: float) -> float:
    cutoff = _finite_real(cutoff_hz, "cutoff_hz")
    if not 0.0 < cutoff < sample_rate_hz / 2.0:
        raise ValueError("cutoff_hz must be positive and below the Nyquist frequency.")
    r = math.exp(-2.0 * math.pi * cutoff / sample_rate_hz)
    if r == 1.0:
        raise ValueError("cutoff_hz is too small for this sample rate's numerical precision.")
    return r


def validate_config(config: SimulationConfig) -> None:
    """Reject invalid, non-finite, aliased, or impractically large simulations.

    fs is in [1e-6, 1e9] Hz, duration in (0, 1e9] s, magnitudes at most
    1e6 V, and phase in [-360000, 360000] degrees. The acquisition must have
    an integral sample count (absolute tolerance 1e-7 sample), 16..1e6.
    A cutoff must also yield an RC coefficient distinguishable from one.
    """
    if not isinstance(config, SimulationConfig):
        raise ValueError("config must be a SimulationConfig.")
    values = {
        field.name: _finite_real(getattr(config, field.name), field.name)
        for field in fields(config) if field.name != "seed"
    }
    rate = _sample_rate(values["sample_rate_hz"])
    if not 0.0 < values["duration_s"] <= 1e9:
        raise ValueError("duration_s must be positive and at most 1e9 seconds.")
    sample_count = rate * values["duration_s"]
    rounded_count = round(sample_count)
    if not 16 <= rounded_count <= MAX_SAMPLES:
        raise ValueError(f"The acquisition must contain 16..{MAX_SAMPLES:,} samples.")
    if not math.isclose(sample_count, rounded_count, rel_tol=0.0, abs_tol=1e-7):
        raise ValueError("sample_rate_hz * duration_s must be a whole number of samples.")
    for name in ("amplitude_v", "noise_std_v", "interference_amplitude_v"):
        if not 0.0 <= values[name] <= MAX_VOLTAGE_V:
            raise ValueError(f"{name} must be between 0 and {MAX_VOLTAGE_V:g} V.")
    if abs(values["dc_offset_v"]) > MAX_VOLTAGE_V:
        raise ValueError(f"dc_offset_v magnitude must be at most {MAX_VOLTAGE_V:g} V.")
    for name in ("phase_deg", "interference_phase_deg"):
        if abs(values[name]) > MAX_PHASE_DEG:
            raise ValueError(f"{name} must be within +/-{MAX_PHASE_DEG:g} degrees.")
    for name in ("frequency_hz", "interference_frequency_hz", "reference_frequency_hz"):
        if not 0.0 < values[name] < rate / 2.0:
            raise ValueError(f"{name} must be positive and below the Nyquist frequency.")
    for name in ("lowpass_cutoff_hz", "lockin_cutoff_hz"):
        try:
            _filter_coefficient(rate, values[name])
        except ValueError as exc:
            raise ValueError(str(exc).replace("cutoff_hz", name)) from None
    if (isinstance(config.seed, (bool, np.bool_))
            or not isinstance(config.seed, Integral)
            or not 0 <= config.seed <= 2**32 - 1):
        raise ValueError("seed must be an integer between 0 and 4294967295.")


def _real_vector(values: np.ndarray) -> np.ndarray:
    """Validate helper inputs without silently discarding complex values."""
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.size == 0 or raw.size > MAX_SAMPLES:
        raise ValueError(f"values must be a one-dimensional array with 1..{MAX_SAMPLES:,} samples.")
    if raw.dtype.kind not in "iuf":
        raise ValueError("values must contain real numbers.")
    data = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(data)):
        raise ValueError("values must contain only finite numbers.")
    return data


def causal_lowpass(values: np.ndarray, sample_rate_hz: float,
                   cutoff_hz: float, stages: int = 1) -> np.ndarray:
    """Return one or more zero-state causal RC stages, without changing input.

    Each stage is y[n]=(1-r)*x[n]+r*y[n-1], r=exp(-2*pi*fc/fs).
    Its exact discrete-time response differs from an analog RC near Nyquist.
    """
    data = _real_vector(values)
    rate = _sample_rate(sample_rate_hz)
    r = _filter_coefficient(rate, cutoff_hz)
    if isinstance(stages, (bool, np.bool_)) or not isinstance(stages, Integral) or not 1 <= stages <= 16:
        raise ValueError("stages must be an integer between 1 and 16.")
    for _ in range(stages):
        data = lfilter([1.0 - r], [1.0, -r], data)
    return data


def single_sided_spectrum(values: np.ndarray,
                          sample_rate_hz: float) -> Tuple[np.ndarray, np.ndarray]:
    """Rectangular-window, one-sided peak spectrum, without detrending.

    DC and even-length Nyquist bins are not doubled. For odd lengths, the
    final rFFT bin is an ordinary positive-frequency bin and is doubled.
    Off-bin tones leak across bins; this is not an amplitude-fitting routine.
    """
    data = _real_vector(values)
    rate = _sample_rate(sample_rate_hz)
    size = data.size
    # Scale exceptionally large finite inputs before the transform: dividing
    # afterward cannot repair overflow in the FFT's intermediate sums.
    peak = float(np.max(np.abs(data)))
    scale = peak if peak > np.finfo(float).max / size else 1.0
    spectrum = np.abs(np.fft.rfft(data / scale if scale != 1.0 else data)) / size
    if size % 2 == 0:
        spectrum[1:-1] *= 2.0
    else:
        spectrum[1:] *= 2.0
    with np.errstate(over="ignore"):
        spectrum *= scale
    if not np.all(np.isfinite(spectrum)):
        raise ValueError("Spectrum amplitude exceeds the finite floating-point range.")
    return np.fft.rfftfreq(size, d=1.0 / rate), spectrum


def simulate(config: SimulationConfig) -> SimulationResult:
    """Generate synthetic data and extract quadratures from the raw input.

    The reference is cos(2*pi*f_ref*t). X=LP2(2*x*cos(ref)),
    Y=LP2(-2*x*sin(ref)); hypot(mean X,mean Y) is a peak voltage.
    Phase is undefined at R <= 1e-10*max(1, max(abs(input_v))) V. This
    numerical zero threshold is not a noise-based confidence test.
    """
    validate_config(config)
    # Validation accepts Real scalars (including NumPy integers and Fraction).
    # Use the same native-float arithmetic that was validated, rather than
    # allowing narrow NumPy multiplication to overflow or object-dtype arrays.
    config = SimulationConfig(**{
        field.name: (int(getattr(config, field.name)) if field.name == "seed"
                     else float(getattr(config, field.name)))
        for field in fields(config)
    })
    sample_count = round(config.sample_rate_hz * config.duration_s)
    time_s = np.arange(sample_count, dtype=float) / config.sample_rate_hz
    clean_v = (config.amplitude_v * np.cos(
        2.0 * np.pi * config.frequency_hz * time_s + np.deg2rad(config.phase_deg)
    ) + config.dc_offset_v)
    rng = np.random.default_rng(config.seed)
    input_v = (clean_v + rng.normal(0.0, config.noise_std_v, sample_count)
               + config.interference_amplitude_v * np.cos(
                   2.0 * np.pi * config.interference_frequency_hz * time_s
                   + np.deg2rad(config.interference_phase_deg)))
    filtered_v = causal_lowpass(input_v, config.sample_rate_hz, config.lowpass_cutoff_hz)
    reference_angle = 2.0 * np.pi * config.reference_frequency_hz * time_s
    x_v = causal_lowpass(2.0 * input_v * np.cos(reference_angle),
                        config.sample_rate_hz, config.lockin_cutoff_hz, stages=2)
    y_v = causal_lowpass(-2.0 * input_v * np.sin(reference_angle),
                        config.sample_rate_hz, config.lockin_cutoff_hz, stages=2)
    amplitude_v = np.hypot(x_v, y_v)
    zero_threshold = PHASE_ZERO_RELATIVE * max(1.0, float(np.max(np.abs(input_v))))
    phase_deg = np.rad2deg(np.arctan2(y_v, x_v))
    phase_deg[amplitude_v <= zero_threshold] = np.nan
    settling_time_s = max(7.0 / (2.0 * np.pi * config.lowpass_cutoff_hz),
                          10.0 / (2.0 * np.pi * config.lockin_cutoff_hz))
    settled = bool(time_s[-1] >= settling_time_s + 3.0 / config.reference_frequency_hz)
    if settled:
        estimate_index = int(np.searchsorted(time_s, settling_time_s))
    else:
        estimate_index = int(0.8 * sample_count)
    estimate_x_v = float(np.mean(x_v[estimate_index:]))
    estimate_y_v = float(np.mean(y_v[estimate_index:]))
    estimate_amplitude_v = math.hypot(estimate_x_v, estimate_y_v)
    estimate_phase_deg = (math.degrees(math.atan2(estimate_y_v, estimate_x_v))
                          if estimate_amplitude_v > zero_threshold else None)
    warnings = []
    if not settled:
        warnings.append("Not fully settled: estimates use the final 20% and are provisional.")
    if not math.isclose(config.frequency_hz, config.reference_frequency_hz, rel_tol=1e-9, abs_tol=0.0):
        warnings.append("Reference frequency differs from the signal: quadratures rotate and averaging can reduce amplitude.")
    if estimate_phase_deg is None:
        warnings.append("Phase is undefined at numerical zero amplitude.")
    mixer_ripple_hz = min(2.0 * config.reference_frequency_hz,
                         config.sample_rate_hz - 2.0 * config.reference_frequency_hz)
    if mixer_ripple_hz <= 10.0 * config.lockin_cutoff_hz:
        warnings.append("Twice-reference mixer ripple (including its sampled alias) is near the lock-in bandwidth; estimates may be biased.")
    frequency_hz, input_spectrum_v = single_sided_spectrum(input_v, config.sample_rate_hz)
    _, filtered_spectrum_v = single_sided_spectrum(filtered_v, config.sample_rate_hz)
    return SimulationResult(
        config=config, time_s=time_s, clean_v=clean_v, input_v=input_v,
        filtered_v=filtered_v, frequency_hz=frequency_hz,
        input_spectrum_v=input_spectrum_v, filtered_spectrum_v=filtered_spectrum_v,
        x_v=x_v, y_v=y_v, amplitude_v=amplitude_v, phase_deg=phase_deg,
        estimate_x_v=estimate_x_v, estimate_y_v=estimate_y_v,
        estimate_amplitude_v=estimate_amplitude_v, estimate_phase_deg=estimate_phase_deg,
        settling_time_s=float(settling_time_s), settled=settled,
        estimate_start_s=float(time_s[estimate_index]), warnings=tuple(warnings),
    )
