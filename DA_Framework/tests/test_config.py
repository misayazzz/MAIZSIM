import tempfile
import unittest
from pathlib import Path

try:
    from . import context  # noqa: F401
except ImportError:  # pragma: no cover - supports direct file execution.
    import context  # noqa: F401
from da_framework.config import ConfigError, load_config


ALLOWED_PARAMETER_NAMES = (
    "n",
    "thetaS",
    "LM_min",
    "Rmax_LTAR",
    "StayGreen",
)


def _write_config(
    root,
    parameter_names,
    target_fields_by_name=None,
    model_lines=None,
):
    target_fields_by_name = target_fields_by_name or {}
    model_lines = model_lines or []
    (root / "base").mkdir()
    (root / "observations.csv").write_text(
        "date,variable,depth_top_cm,depth_bottom_cm,value,std\n",
        encoding="utf-8",
    )

    lines = [
        "[model]",
        'base_run_dir = "base"',
        *model_lines,
        "[observation]",
        'file = "observations.csv"',
    ]
    for name in parameter_names:
        lines.extend(
            [
                "",
                "[[parameters]]",
                f'name = "{name}"',
                "current = 1.0",
                "lower = 0.0",
                "upper = 2.0",
                "std = 0.1",
            ]
        )
        if name in target_fields_by_name:
            target_fields = ", ".join(
                f'"{field}"' for field in target_fields_by_name[name]
            )
            lines.append(f"target_fields = [{target_fields}]")

    config_path = root / "config.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


class ConfigValidationTests(unittest.TestCase):
    def test_load_config_rejects_rmax_lir_parameter(self):
        parameter_names = (
            "n",
            "thetaS",
            "LM_min",
            "Rmax_LIR",
            "StayGreen",
        )
        with tempfile.TemporaryDirectory(prefix="codex_config_rmax_lir_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), parameter_names)

            with self.assertRaises(ConfigError) as exc:
                load_config(config_path)

        self.assertIn("Rmax_LIR", str(exc.exception))
        self.assertIn("Allowed parameters are exactly", str(exc.exception))

    def test_load_config_rejects_unknown_parameter(self):
        parameter_names = (*ALLOWED_PARAMETER_NAMES, "UnknownParameter")
        with tempfile.TemporaryDirectory(prefix="codex_config_unknown_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), parameter_names)

            with self.assertRaises(ConfigError) as exc:
                load_config(config_path)

        self.assertIn("UnknownParameter", str(exc.exception))
        self.assertIn("Allowed parameters are exactly", str(exc.exception))

    def test_load_config_rejects_missing_allowed_parameter(self):
        parameter_names = (
            "n",
            "thetaS",
            "LM_min",
            "Rmax_LTAR",
        )
        with tempfile.TemporaryDirectory(prefix="codex_config_missing_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), parameter_names)

            with self.assertRaises(ConfigError) as exc:
                load_config(config_path)

        self.assertIn("continuous parameters must include exactly", str(exc.exception))
        self.assertIn("missing: StayGreen", str(exc.exception))

    def test_load_config_rejects_juvenile_leaves_parameter_explicitly(self):
        parameter_names = (
            "n",
            "thetaS",
            "LM_min",
            "Rmax_LTAR",
            "JuvenileLeaves",
        )
        with tempfile.TemporaryDirectory(prefix="codex_config_jl_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), parameter_names)

            with self.assertRaises(ConfigError) as exc:
                load_config(config_path)

        self.assertIn("JuvenileLeaves is discrete", str(exc.exception))

    def test_load_config_rejects_invalid_theta_s_target_fields(self):
        target_fields_by_name = {
            "thetaS": ("ths", "thm", "thk"),
        }
        with tempfile.TemporaryDirectory(prefix="codex_config_theta_s_") as tmp_dir:
            config_path = _write_config(
                Path(tmp_dir),
                ALLOWED_PARAMETER_NAMES,
                target_fields_by_name,
            )

            with self.assertRaises(ConfigError) as exc:
                load_config(config_path)

        self.assertIn("thetaS must be exactly ths, th, thk", str(exc.exception))
        self.assertIn("got: ths, thm, thk", str(exc.exception))

    def test_load_config_defaults_model_workers_to_twelve(self):
        with tempfile.TemporaryDirectory(prefix="codex_config_workers_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), ALLOWED_PARAMETER_NAMES)

            config = load_config(config_path)

        self.assertEqual(config.model.max_workers, 12)

    def test_load_config_defaults_minimal_outputs_to_false(self):
        with tempfile.TemporaryDirectory(prefix="codex_config_minimal_default_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), ALLOWED_PARAMETER_NAMES)

            config = load_config(config_path)

        self.assertFalse(config.model.minimal_outputs)

    def test_load_config_reads_minimal_outputs(self):
        with tempfile.TemporaryDirectory(prefix="codex_config_minimal_") as tmp_dir:
            config_path = _write_config(
                Path(tmp_dir),
                ALLOWED_PARAMETER_NAMES,
                model_lines=["minimal_outputs = true"],
            )

            config = load_config(config_path)

        self.assertTrue(config.model.minimal_outputs)

    def test_load_config_defaults_assimilation_ensemble_to_one_hundred(self):
        with tempfile.TemporaryDirectory(prefix="codex_config_ensemble_") as tmp_dir:
            config_path = _write_config(Path(tmp_dir), ALLOWED_PARAMETER_NAMES)

            config = load_config(config_path)

        self.assertEqual(config.assimilation.n_ensemble, 100)


if __name__ == "__main__":
    unittest.main()
