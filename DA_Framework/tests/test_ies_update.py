import unittest

import numpy as np

import context  # noqa: F401
from da_framework.update import (
    ParameterBounds,
    apply_parameter_bounds,
    halfway_back_to_bounds,
    ies_update,
)


class IESUpdateTests(unittest.TestCase):
    def test_kalman_gain_update_matches_explicit_formula_without_perturbation(self):
        x_forecast = np.array(
            [
                [1.0, 2.0, 4.0, 5.0],
                [0.5, 1.5, 3.0, 3.5],
            ]
        )
        y_forecast = np.array(
            [
                [0.8, 1.4, 2.4, 3.0],
                [2.5, 1.0, 1.5, 0.5],
            ]
        )
        observations = np.array([2.2, 1.4])
        observation_std = np.array([0.25, 0.4])

        result = ies_update(
            x_forecast,
            y_forecast,
            observations,
            observation_std,
            parameter_names=["StayGreen", "LM_min"],
            perturb_observations=False,
        )

        n_ensemble = x_forecast.shape[1]
        x_mean = x_forecast.mean(axis=1)
        y_mean = y_forecast.mean(axis=1)
        x_anomalies = x_forecast - x_mean[:, None]
        y_anomalies = y_forecast - y_mean[:, None]
        cxy = x_anomalies @ y_anomalies.T / (n_ensemble - 1)
        cyy = y_anomalies @ y_anomalies.T / (n_ensemble - 1)
        observation_error = np.diag(observation_std**2)
        expected_gain = cxy @ np.linalg.inv(cyy + observation_error)
        expected_innovations = observations[:, None] - y_forecast
        expected_updated = x_forecast + expected_gain @ expected_innovations

        np.testing.assert_allclose(result.kalman_gain, expected_gain, rtol=1e-12)
        np.testing.assert_allclose(result.innovations, expected_innovations)
        np.testing.assert_allclose(result.updated_parameters, expected_updated)
        np.testing.assert_allclose(result.forecast_mean, x_mean)
        np.testing.assert_allclose(result.simulated_mean, y_mean)
        self.assertEqual(result.updated_parameters.shape, x_forecast.shape)
        self.assertFalse(result.bound_hits.any())

    def test_halfway_back_to_bounds_moves_only_out_of_range_values(self):
        values = np.array([[3.0, -2.0, 12.0, 8.0]])
        forecast_values = np.array([[3.0, 2.0, 6.0, 8.0]])
        bounds = ParameterBounds("thetaS", lower=0.0, upper=10.0)

        bounded, hits = halfway_back_to_bounds(values, forecast_values, bounds)

        expected = np.array([[3.0, 1.0, 8.0, 8.0]])
        expected_hits = np.array([[False, True, True, False]])
        np.testing.assert_allclose(bounded, expected)
        np.testing.assert_array_equal(hits, expected_hits)

    def test_apply_parameter_bounds_uses_parameter_names(self):
        values = np.array(
            [
                [-1.0, 5.0],
                [100.0, -100.0],
            ]
        )
        forecast_values = np.array(
            [
                [3.0, 5.0],
                [10.0, 10.0],
            ]
        )

        bounded, hits = apply_parameter_bounds(
            values,
            forecast_values,
            parameter_names=["bounded", "unbounded"],
            bounds_by_name={"bounded": ParameterBounds("bounded", 0.0, 4.0)},
        )

        expected = np.array(
            [
                [1.5, 4.5],
                [100.0, -100.0],
            ]
        )
        expected_hits = np.array(
            [
                [True, True],
                [False, False],
            ]
        )
        np.testing.assert_allclose(bounded, expected)
        np.testing.assert_array_equal(hits, expected_hits)


if __name__ == "__main__":
    unittest.main()
