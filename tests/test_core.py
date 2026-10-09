"""Numerical regression tests against closed-form, independent expectations."""

from dataclasses import replace
from fractions import Fraction
import math
import warnings

import numpy as np
import pytest

from virtual_instrument_lab.core import (
    PRESETS, SimulationConfig, causal_lowpass, simulate,
    single_sided_spectrum, validate_config,
)


@pytest.fixture
def clean_config():
    return replace(PRESETS["Clean reference"], duration_s=6.0)


def test_sampling_has_no_repeated_endpoint(clean_config):
    result = simulate(clean_config)
    assert len(result.time_s) == 12000
    assert result.time_s[0] == 0.0
    assert result.time_s[-1] == clean_config.duration_s - 1 / clean_config.sample_rate_hz
    np.testing.assert_allclose(np.diff(result.time_s), 1 / clean_config.sample_rate_hz)


@pytest.mark.parametrize("phase", [-170.0, -90.0, -30.0, 0.0, 30.0, 90.0, 170.0])
def test_lockin_recovers_peak_amplitude_and_signed_phase(clean_config, phase):
    config = replace(clean_config, amplitude_v=2.5, phase_deg=phase,
                     dc_offset_v=0.7, interference_amplitude_v=0.3,
                     interference_frequency_hz=120.0)
    result = simulate(config)
    expected_x = config.amplitude_v * math.cos(math.radians(phase))
    expected_y = config.amplitude_v * math.sin(math.radians(phase))
    assert result.settled
    assert result.estimate_x_v == pytest.approx(expected_x, abs=4e-5)
    assert result.estimate_y_v == pytest.approx(expected_y, abs=4e-5)
    assert result.estimate_amplitude_v == pytest.approx(config.amplitude_v, abs=4e-5)
    assert result.estimate_phase_deg == pytest.approx(phase, abs=0.001)


def test_mixing_uses_raw_input_not_display_lowpass(clean_config):
    result = simulate(replace(clean_config, lowpass_cutoff_hz=5.0))
    assert result.estimate_amplitude_v == pytest.approx(1.0, abs=3e-5)
    # A display filter attenuates the tone strongly without changing demodulation.
    assert np.std(result.filtered_v[4000:]) < 0.1


def test_gaussian_noise_is_reproducible_without_global_rng_side_effects(clean_config):
    config = replace(clean_config, noise_std_v=0.7)
    saved_state = np.random.get_state()
    np.random.seed(987)
    expected_global = np.random.random(4)
    np.random.seed(987)
    first = simulate(config)
    second = simulate(config)
    different = simulate(replace(config, seed=config.seed + 1))
    np.testing.assert_array_equal(first.input_v, second.input_v)
    np.testing.assert_array_equal(first.x_v, second.x_v)
    assert not np.array_equal(first.input_v, different.input_v)
    np.testing.assert_array_equal(np.random.random(4), expected_global)
    np.random.set_state(saved_state)
    np.testing.assert_array_equal(first.clean_v, different.clean_v)
    noise = first.input_v - first.clean_v
    assert np.mean(noise) == pytest.approx(0.0, abs=0.025)
    assert np.std(noise) == pytest.approx(0.7, abs=0.025)


@pytest.mark.parametrize("size", [31, 32, 101, 100])
def test_fft_dc_and_interior_peak_normalization(size):
    index = np.arange(size)
    values = 0.7 + 2.5 * np.cos(2 * np.pi * 3 * index / size + 0.37)
    frequencies, amplitude = single_sided_spectrum(values, 1000.0)
    assert len(amplitude) == size // 2 + 1
    assert frequencies[3] == pytest.approx(3000.0 / size)
    assert amplitude[0] == pytest.approx(0.7, abs=1e-14)
    assert amplitude[3] == pytest.approx(2.5, abs=1e-14)
    amplitude[[0, 3]] = 0.0
    assert np.max(amplitude) < 1e-13


def test_fft_even_nyquist_not_doubled():
    values = 1.75 * (-1.0) ** np.arange(32)
    frequencies, amplitude = single_sided_spectrum(values, 1000.0)
    assert frequencies[-1] == 500.0
    assert amplitude[-1] == pytest.approx(1.75)
    assert np.max(amplitude[:-1]) < 1e-14


def test_fft_odd_final_bin_is_doubled():
    size = 31
    values = 1.75 * np.cos(2 * np.pi * (size // 2) * np.arange(size) / size)
    frequencies, amplitude = single_sided_spectrum(values, 1000.0)
    assert frequencies[-1] < 500.0
    assert amplitude[-1] == pytest.approx(1.75, abs=1e-14)


def test_fft_large_finite_dc_does_not_overflow_intermediate_sum():
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        _, amplitude = single_sided_spectrum(np.full(16, 1e308), 1000.0)
    assert amplitude[0] == pytest.approx(1e308)
    np.testing.assert_array_equal(amplitude[1:], np.zeros(8))


def test_fft_rejects_amplitude_that_cannot_be_represented():
    # A square wave's fundamental peak exceeds its time-domain peak.
    values = np.sign(np.cos(2 * np.pi * np.arange(16) / 16)) * np.finfo(float).max
    with pytest.raises(ValueError, match="floating-point range"):
        single_sided_spectrum(values, 1000.0)


def test_rc_step_and_two_stage_startup_match_closed_form():
    rate, cutoff = 1000.0, 3.0
    size = 2000
    r = math.exp(-2 * math.pi * cutoff / rate)
    indices = np.arange(1, size + 1)
    one_stage = causal_lowpass(np.ones(size), rate, cutoff)
    two_stages = causal_lowpass(np.ones(size), rate, cutoff, stages=2)
    np.testing.assert_allclose(one_stage, 1 - r**indices, atol=3e-15)
    np.testing.assert_allclose(two_stages, 1 - r**indices * (1 + indices * (1 - r)), atol=5e-15)
    assert one_stage[0] == pytest.approx(1 - r)
    assert two_stages[0] == pytest.approx((1 - r)**2)
    assert np.all(np.diff(one_stage) >= 0)
    assert one_stage[-1] == pytest.approx(1.0)
    assert two_stages[-1] == pytest.approx(1.0)


@pytest.mark.parametrize("stages", [1, 2])
def test_rc_sinusoidal_gain_and_phase_match_exact_discrete_response(stages):
    rate, cutoff, frequency = 2000.0, 60.0, 250.0
    time_s = np.arange(12000) / rate
    omega = 2 * np.pi * frequency / rate
    r = math.exp(-2 * math.pi * cutoff / rate)
    response = ((1 - r) / (1 - r * np.exp(-1j * omega)))**stages
    filtered = causal_lowpass(1.4 * np.cos(2 * np.pi * frequency * time_s + 0.2),
                               rate, cutoff, stages=stages)
    expected = 1.4 * abs(response) * np.cos(
        2 * np.pi * frequency * time_s + 0.2 + np.angle(response))
    np.testing.assert_allclose(filtered[2000:], expected[2000:], atol=2e-12, rtol=0)


def test_filter_is_causal_and_does_not_change_source():
    values = np.zeros(1000)
    values[700] = 1.0
    original = values.copy()
    filtered = causal_lowpass(values, 1000.0, 20.0)
    np.testing.assert_array_equal(values, original)
    np.testing.assert_array_equal(filtered[:700], np.zeros(700))
    assert filtered[700] > 0


def test_zero_and_numerical_zero_phase_are_undefined(clean_config):
    for amplitude in (0.0, 1e-12):
        result = simulate(replace(clean_config, amplitude_v=amplitude))
        assert result.estimate_phase_deg is None
        assert np.all(np.isnan(result.phase_deg))
        assert any("undefined" in message for message in result.warnings)


def test_phase_is_defined_above_documented_zero_threshold(clean_config):
    result = simulate(replace(clean_config, amplitude_v=2e-10))
    assert result.estimate_phase_deg == pytest.approx(30.0, abs=0.001)


def test_seed_does_not_change_noiseless_input(clean_config):
    first = simulate(clean_config)
    second = simulate(replace(clean_config, seed=123))
    np.testing.assert_array_equal(first.input_v, second.input_v)


def test_settling_requires_marker_plus_three_reference_cycles(clean_config):
    short = simulate(replace(clean_config, duration_s=0.8))
    assert not short.settled
    assert short.estimate_start_s == short.time_s[int(0.8 * len(short.time_s))]
    assert short.estimate_x_v == np.mean(short.x_v[int(0.8 * len(short.time_s)):])
    assert any("provisional" in warning for warning in short.warnings)
    complete = simulate(clean_config)
    expected_marker = 10 / (2 * np.pi * clean_config.lockin_cutoff_hz)
    assert complete.settling_time_s == pytest.approx(expected_marker)
    assert complete.estimate_start_s >= complete.settling_time_s
    assert complete.estimate_start_s - complete.settling_time_s < 1 / clean_config.sample_rate_hz
    assert complete.settled
    between = simulate(replace(clean_config, duration_s=0.82))
    assert between.time_s[-1] > between.settling_time_s
    assert not between.settled  # Startup passed, but fewer than 3 reference cycles.


def test_reference_mismatch_warns_even_after_startup(clean_config):
    result = simulate(replace(clean_config, reference_frequency_hz=51.0))
    assert result.settled
    assert any("differs" in warning for warning in result.warnings)
    assert result.estimate_amplitude_v < 0.1


def test_settling_exact_sample_boundary():
    config = replace(PRESETS["Clean reference"], sample_rate_hz=256,
                     duration_s=304 / 256, frequency_hz=16,
                     reference_frequency_hz=16, interference_frequency_hz=40,
                     lowpass_cutoff_hz=40, lockin_cutoff_hz=5 / np.pi)
    before = simulate(config)
    on_boundary = simulate(replace(config, duration_s=305 / 256))
    assert before.settling_time_s == 1.0
    assert not before.settled
    assert on_boundary.settled


def test_near_nyquist_mixer_alias_is_warned(clean_config):
    result = simulate(replace(clean_config, frequency_hz=998, reference_frequency_hz=998))
    assert any("sampled alias" in warning for warning in result.warnings)


@pytest.mark.parametrize("field,value", [
    ("sample_rate_hz", 0), ("sample_rate_hz", -1), ("sample_rate_hz", 1e10),
    ("duration_s", 0), ("duration_s", -1), ("duration_s", 1e10),
    ("duration_s", 0.001), ("duration_s", 0.10001), ("duration_s", 501),
    ("amplitude_v", -1), ("amplitude_v", 1e7), ("noise_std_v", -1),
    ("interference_amplitude_v", -1), ("dc_offset_v", -1e7),
    ("phase_deg", 360001), ("interference_phase_deg", -360001),
    ("frequency_hz", 0), ("frequency_hz", 1000),
    ("interference_frequency_hz", 1000), ("reference_frequency_hz", -1),
    ("lowpass_cutoff_hz", 0), ("lockin_cutoff_hz", 1000),
    ("lockin_cutoff_hz", 1e-100), ("seed", -1), ("seed", 2**32),
    ("seed", 1.5), ("seed", True), ("seed", "42"),
    ("amplitude_v", float("nan")), ("phase_deg", float("inf")),
    ("dc_offset_v", "0.2"), ("amplitude_v", True),
])
def test_bad_configuration_is_rejected(field, value):
    with pytest.raises(ValueError):
        simulate(replace(SimulationConfig(), **{field: value}))


@pytest.mark.parametrize("values", [[], [[1, 2]], [1, np.nan], [1, np.inf], [1 + 2j], ["1"]])
def test_bad_helper_input_is_rejected(values):
    with pytest.raises(ValueError):
        single_sided_spectrum(values, 1000.0)
    with pytest.raises(ValueError):
        causal_lowpass(values, 1000.0, 10.0)


@pytest.mark.parametrize("stages", [0, -1, 17, True, 1.5])
def test_invalid_filter_stage_count(stages):
    with pytest.raises(ValueError):
        causal_lowpass(np.ones(16), 1000.0, 10.0, stages)


def test_all_three_presets_produce_finite_settled_results():
    assert len(PRESETS) == 3
    for config in PRESETS.values():
        validate_config(config)
        result = simulate(config)
        assert result.settled
        for values in (result.input_v, result.filtered_v, result.x_v, result.y_v, result.amplitude_v):
            assert np.all(np.isfinite(values))
        assert result.estimate_phase_deg is not None


@pytest.mark.parametrize("scalar_type", [np.int16, np.float16])
def test_accepted_narrow_scalars_do_not_overflow_sample_count(scalar_type):
    config = replace(PRESETS["Clean reference"],
                     sample_rate_hz=scalar_type(2000), duration_s=scalar_type(40))
    validate_config(config)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = simulate(config)
    assert len(result.time_s) == 80000
    assert result.time_s[-1] == pytest.approx(39.9995)
    assert result.estimate_phase_deg == pytest.approx(30.0, abs=0.001)


def test_accepted_fraction_scalars_use_numeric_arrays():
    config = replace(PRESETS["Clean reference"], sample_rate_hz=Fraction(2000),
                     amplitude_v=Fraction(1, 2), phase_deg=Fraction(30),
                     duration_s=Fraction(4), seed=np.uint32(42))
    validate_config(config)
    result = simulate(config)
    assert result.time_s.dtype == np.float64
    assert result.input_v.dtype == np.float64
    assert result.estimate_amplitude_v == pytest.approx(0.5, abs=3e-5)
    assert result.estimate_phase_deg == pytest.approx(30.0, abs=0.001)
    assert isinstance(result.config.sample_rate_hz, float)
    assert isinstance(result.config.seed, int)
