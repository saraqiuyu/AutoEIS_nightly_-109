import numpy as np
import numpyro
import pandas as pd
import pytest
from autoeis import core, io, utils


def test_compute_ohmic_resistance():
    circuit_string = "R1-[P2,P3-R4]"
    circuit_fn = utils.generate_circuit_fn_impedance_backend(circuit_string)
    R1 = 250
    parameters = np.array([R1, 1e-3, 0.1, 5e-5, 0.8, 10])
    freq = np.logspace(-3, 3, 1000)
    Z = circuit_fn(freq, parameters)
    R = core.compute_ohmic_resistance(freq, Z)
    np.testing.assert_allclose(R, R1, rtol=0.15)


def test_compute_ohmic_resistance_missing_high_freq():
    circuit_string = "R1-[P2,P3-R4]"
    circuit_fn = utils.generate_circuit_fn_impedance_backend(circuit_string)
    R1 = 250
    parameters = np.array([R1, 1e-3, 0.1, 5e-5, 0.8, 10])
    freq = np.logspace(-3, 0, 1000)
    Z = circuit_fn(freq, parameters)
    R = core.compute_ohmic_resistance(freq, Z)
    # When high frequency measurements are missing, Re(Z) @ max(freq) is good approximation
    Zreal_at_high_freq = Z.real[np.argmax(freq)]
    np.testing.assert_allclose(R, Zreal_at_high_freq)


def test_preprocess_impedance_data():
    freq, Z = io.load_test_dataset()
    # Test various tolerances for linKK validation
    freq_prep, Z_prep = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-2)
    assert len(Z_prep) == len(freq_prep)
    assert len(Z_prep) == 60
    freq_prep, Z_prep = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-3)
    assert len(Z_prep) == len(freq_prep)
    assert len(Z_prep) == 50
    # Test return_aux=True
    _, _, aux = core.preprocess_impedance_data(freq, Z, return_aux=True)
    assert list(aux.keys()) == ["res", "rmse"]
    assert list(aux["res"].keys()) == ["real", "imag"]


def test_gep():
    def test_gep_serial():
        freq, Z = io.load_test_dataset()
        freq, Z = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-2)
        kwargs = {
            "iters": 2,
            "complexity": 2,
            "population_size": 5,
            "generations": 2,
            "tol": 1e10,
            "parallel": False,
        }
        circuits = core.generate_equivalent_circuits(freq, Z, **kwargs)
        assert len(circuits) == kwargs["iters"]
        assert isinstance(circuits, pd.DataFrame)

    def test_gep_parallel():
        freq, Z = io.load_test_dataset()
        freq, Z = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-2)
        kwargs = {
            "iters": 2,
            "complexity": 2,
            "population_size": 5,
            "generations": 2,
            "tol": 1e10,
            "parallel": True,
        }
        circuits = core.generate_equivalent_circuits(freq, Z, **kwargs)
        assert len(circuits) == kwargs["iters"]
        assert isinstance(circuits, pd.DataFrame)

    test_gep_serial()
    test_gep_parallel()


def test_filter_implausible_circuits():
    circuits_unfiltered = io.load_test_circuits()
    N1 = len(circuits_unfiltered)
    circuits = core.filter_implausible_circuits(circuits_unfiltered)
    N2 = len(circuits)
    assert N2 < N1


def test_bayesian_inference_single():
    freq, Z = io.load_test_dataset()
    freq, Z = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-2)
    circuits = io.load_test_circuits(filtered=True)
    circuit = circuits.iloc[0].circuitstring
    p0 = circuits.iloc[0].Parameters
    kwargs_mcmc = {"num_warmup": 25, "num_samples": 10, "progress_bar": False}
    results = core.perform_bayesian_inference(circuit, freq, Z, p0, **kwargs_mcmc)
    mcmc, exit_code = results[0]
    assert exit_code in [-1, 0]
    assert isinstance(mcmc, numpyro.infer.mcmc.MCMC)


def test_bayesian_inference_batch():
    freq, Z = io.load_test_dataset()
    freq, Z = core.preprocess_impedance_data(freq, Z, tol_linKK=5e-2)
    # Test the first two circuits to save CI time
    circuits = io.load_test_circuits(filtered=True).iloc[:2]
    kwargs_mcmc = {"num_warmup": 25, "num_samples": 10, "progress_bar": False}
    results = core.perform_bayesian_inference(circuits, freq, Z, **kwargs_mcmc)
    assert len(results) == len(circuits)
    for mcmc, exit_code in results:
        assert exit_code == 0  # Ensure convergence
        assert isinstance(mcmc, numpyro.infer.mcmc.MCMC)  # Ensure correct type


# TODO: Use a simple circuit to generate test data so this test doesn't take too long
@pytest.mark.skip(reason="This test is too slow!")
def test_perform_full_analysis():
    freq, Z = io.load_test_dataset()
    results = core.perform_full_analysis(freq, Z)
    required_columns = ["circuitstring", "Parameters", "MCMC", "success", "divergences"]
    assert all(col in results.columns for col in required_columns)
