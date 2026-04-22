import pytest

np = pytest.importorskip("numpy")

from core.wave_utils import compute_image_levels, compute_pressure_matrix


def test_compute_pressure_matrix_constant_pressure():
    gamma = 1.4
    pressure = 101325.0
    rho = 1.2
    u = 0.0
    energy = pressure / (gamma - 1.0) / rho + 0.5 * u**2
    state = np.array([[rho, rho * u, rho * energy]])

    history = [state, state]
    matrix = compute_pressure_matrix(history, gamma)

    assert matrix.shape == (2, 1)
    np.testing.assert_allclose(matrix[:, 0], pressure)


def test_compute_image_levels_gradient():
    matrix = np.arange(100.0)
    lower, upper = compute_image_levels(matrix)

    expected_lower, expected_upper = np.percentile(matrix, [5.0, 95.0])
    padding = 0.05 * (expected_upper - expected_lower)
    np.testing.assert_allclose(lower, expected_lower - padding)
    np.testing.assert_allclose(upper, expected_upper + padding)


def test_compute_image_levels_constant():
    matrix = np.ones((4, 4)) * 50000.0
    lower, upper = compute_image_levels(matrix)

    # Degenerate spread should expand to a small symmetric window
    assert upper - lower > 0.0
    assert lower < 50000.0 < upper
