import importlib
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import context
from da_framework.model_runner import run_model
from da_framework.observation import read_observations_csv
from da_framework.output_reader import build_simulation_vector
from da_framework.update import ParameterBounds, ies_update


class SyntheticIntegrationTests(unittest.TestCase):
    def test_small_synthetic_observations_complete_one_ies_update(self):
        with tempfile.TemporaryDirectory(prefix="codex_synthetic_ies_") as tmp_dir:
            observation_path = Path(tmp_dir) / "observations.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2024-06-01",
                        "variable": "LAI",
                        "depth_top_cm": "",
                        "depth_bottom_cm": "",
                        "value": 2.6,
                        "std": 0.2,
                    },
                    {
                        "date": "2024-06-01",
                        "variable": "theta",
                        "depth_top_cm": 0,
                        "depth_bottom_cm": 20,
                        "value": 1.4,
                        "std": 0.15,
                    },
                ]
            ).to_csv(observation_path, index=False)

            observations = read_observations_csv(observation_path)

        x_forecast = np.array(
            [
                [1.0, 2.0, 3.0, 4.0],
                [3.0, 1.0, 2.0, 0.5],
            ]
        )
        y_forecast = x_forecast.copy()
        forecast_distance = np.linalg.norm(
            y_forecast.mean(axis=1) - observations.values
        )

        result = ies_update(
            x_forecast,
            y_forecast,
            observations.values,
            observations.std,
            parameter_names=["StayGreen", "thetaS"],
            bounds_by_name={
                "StayGreen": ParameterBounds("StayGreen", 0.1, 10.0),
                "thetaS": ParameterBounds("thetaS", 0.1, 5.0),
            },
            perturb_observations=False,
        )

        updated_simulation = result.updated_parameters
        updated_distance = np.linalg.norm(
            updated_simulation.mean(axis=1) - observations.values
        )
        self.assertEqual(result.updated_parameters.shape, x_forecast.shape)
        self.assertLess(updated_distance, forecast_distance)
        self.assertFalse(result.bound_hits.any())

    def test_load_config_if_framework_config_module_is_available(self):
        try:
            config_module = importlib.import_module("da_framework.config")
        except ModuleNotFoundError as exc:
            self.skipTest(f"da_framework.config is not available: {exc}")

        load_config = getattr(config_module, "load_config", None)
        if load_config is None:
            self.skipTest("da_framework.config.load_config is not available")

        with tempfile.TemporaryDirectory(prefix="codex_config_") as tmp_dir:
            root = Path(tmp_dir)
            (root / "base").mkdir()
            (root / "observations.csv").write_text(
                "date,variable,depth_top_cm,depth_bottom_cm,value,std\n",
                encoding="utf-8",
            )
            config_path = root / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[model]",
                        'base_run_dir = "base"',
                        'var_file = "crop.var"',
                        'soi_file = "soil.soi"',
                        "[observation]",
                        'file = "observations.csv"',
                        "[assimilation]",
                        "n_ensemble = 2",
                        "n_iter = 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            loaded = load_config(config_path)

        self.assertEqual(loaded.assimilation.n_ensemble, 2)
        self.assertEqual(loaded.assimilation.n_iter, 1)
        self.assertEqual(loaded.model.var_file, "crop.var")


class OptionalLocalForecastTests(unittest.TestCase):
    def test_optional_single_layer_loam_base_forecast(self):
        base_dir = (
            context.REPO_ROOT
            / "DA_Framework"
            / "base_runs"
            / "SingleLayerLoam2D"
        )
        required_files = [
            base_dir / "run.dat",
            base_dir / "2dMAIZSIM.exe",
        ]
        var_files = list(base_dir.glob("*.var")) + list(base_dir.glob("*.VAR"))
        soi_files = list(base_dir.glob("*.soi")) + list(base_dir.glob("*.SOI"))
        missing = [
            str(path.relative_to(context.REPO_ROOT))
            for path in required_files
            if not path.is_file()
        ]
        if not var_files:
            missing.append(str(base_dir.relative_to(context.REPO_ROOT) / "*.var"))
        if not soi_files:
            missing.append(str(base_dir.relative_to(context.REPO_ROOT) / "*.soi"))
        if missing:
            self.skipTest(
                "Skipping optional local MAIZSIM base forecast; missing required "
                f"input(s): {', '.join(missing)}"
            )

        with tempfile.TemporaryDirectory(prefix="codex_maizsim_forecast_") as tmp_dir:
            run_dir = Path(tmp_dir) / "forecast"
            shutil.copytree(base_dir, run_dir)
            result = run_model(run_dir, timeout_seconds=60)

            self.assertTrue(result.success, result.message)
            observations = read_observations_csv(
                context.REPO_ROOT
                / "DA_Framework"
                / "examples"
                / "synthetic_observations.csv"
            )
            simulation_vector = build_simulation_vector(
                run_dir,
                observations.specs,
            )
            self.assertEqual(len(simulation_vector), len(observations.values))
            self.assertTrue(np.isfinite(simulation_vector).all())


if __name__ == "__main__":
    unittest.main()
