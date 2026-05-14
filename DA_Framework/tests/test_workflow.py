import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    from . import context  # noqa: F401
except ImportError:  # pragma: no cover - supports direct file execution.
    import context  # noqa: F401
from da_framework.config import (
    AssimilationConfig,
    FrameworkConfig,
    ModelConfig,
    ObservationConfig,
    OutputConfig,
    ParameterConfig,
)
from da_framework.workflow import (
    ObservationData,
    _run_forecast_with_standard_modules,
)


def _parameter_configs():
    return (
        ParameterConfig("n", 1.0, 0.0, 2.0, 0.1),
        ParameterConfig("thetaS", 1.0, 0.0, 2.0, 0.1),
        ParameterConfig("LM_min", 1.0, 0.0, 2.0, 0.1),
        ParameterConfig("Rmax_LTAR", 1.0, 0.0, 2.0, 0.1),
        ParameterConfig("StayGreen", 1.0, 0.0, 2.0, 0.1),
    )


def _framework_config(root, minimal_outputs=False):
    base_dir = root / "base"
    base_dir.mkdir()
    return FrameworkConfig(
        model=ModelConfig(
            base_run_dir=base_dir,
            var_file="crop.var",
            soi_file="soil.soi",
            minimal_outputs=minimal_outputs,
        ),
        observation=ObservationConfig(file=root / "observations.csv"),
        parameters=_parameter_configs(),
        assimilation=AssimilationConfig(
            n_ensemble=2,
            n_iter=1,
            random_seed=1,
        ),
        output=OutputConfig(run_root=root / "runs"),
    )


def _lai_observations():
    rows = (
        {
            "date": "2024-06-01",
            "variable": "LAI",
            "depth_top_cm": "",
            "depth_bottom_cm": "",
            "value": "0.0",
            "std": "1.0",
            "observation_id": "lai_1",
        },
        {
            "date": "2024-06-02",
            "variable": "LAI",
            "depth_top_cm": "",
            "depth_bottom_cm": "",
            "value": "0.0",
            "std": "1.0",
            "observation_id": "lai_2",
        },
    )
    return ObservationData(
        rows=rows,
        values=(0.0, 0.0),
        std=(1.0, 1.0),
        ids=("lai_1", "lai_2"),
    )


def _fake_ensemble_module(calls=None):
    def prepare_ensemble(
        _base_run_dir,
        ensemble_dir,
        _n_ensemble,
        minimal_outputs=False,
        run_file="run.dat",
    ):
        if calls is not None:
            calls.append(
                {
                    "minimal_outputs": minimal_outputs,
                    "run_file": run_file,
                }
            )
        member_dirs = [ensemble_dir / "000001", ensemble_dir / "000002"]
        member_outputs = ((1.0, 2.0), (10.0, 20.0))
        for member_dir, values in zip(member_dirs, member_outputs):
            member_dir.mkdir(parents=True)
            (member_dir / "member.g01").write_text(
                "\n".join(
                    [
                        "Date,LAI",
                        f"2024-06-01,{values[0]}",
                        f"2024-06-02,{values[1]}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        return member_dirs

    def write_ensemble_parameters(
        _member_dirs,
        _parameter_sets,
        _var_file,
        _soi_file,
    ):
        return None

    return SimpleNamespace(
        prepare_ensemble=prepare_ensemble,
        write_ensemble_parameters=write_ensemble_parameters,
    )


class WorkflowForecastTests(unittest.TestCase):
    def test_standard_forecast_keeps_square_member_vectors_transposed(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_workflow_square_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            config = _framework_config(root, minimal_outputs=True)
            parameter_sets = [{"n": 1.0}, {"n": 2.0}]
            calls = []

            with patch("da_framework.workflow._run_member_models"):
                matrix = _run_forecast_with_standard_modules(
                    config,
                    parameter_sets,
                    _lai_observations(),
                    iteration=0,
                    experiment_dir=root / "experiment",
                    juvenile_leaves=None,
                    ensemble_module=_fake_ensemble_module(calls),
                )

        self.assertEqual(matrix, [[1.0, 10.0], [2.0, 20.0]])
        self.assertEqual(
            calls,
            [
                {
                    "minimal_outputs": True,
                    "run_file": "run.dat",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
