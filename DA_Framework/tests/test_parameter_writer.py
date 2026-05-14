import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401
from da_framework.parameter_writer import (
    write_member_parameters,
    write_soi_parameters,
    write_var_parameters,
)


def _tokens(line):
    return line.replace(",", " ").split()


def _write_synthetic_var(path):
    path.write_text(
        "\n".join(
            [
                "header one",
                "header two",
                "header three",
                "1, 2, 3, 4, 5, 6, 7",
                "tail",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_synthetic_soi(path):
    path.write_text(
        "\n".join(
            [
                "soil header one",
                "soil header two",
                "0.05 0.30 2 0.31 4 1.20 6 7 0.32 9 10",
                "0.06 0.33 2 0.34 4 1.30 6 7 0.35 9 10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class ParameterWriterTests(unittest.TestCase):
    def test_write_var_parameters_updates_expected_crop_columns(self):
        with tempfile.TemporaryDirectory(prefix="codex_var_") as tmp_dir:
            var_path = Path(tmp_dir) / "crop.var"
            _write_synthetic_var(var_path)

            write_var_parameters(
                var_path,
                {
                    "StayGreen": 9.5,
                    "LM_min": 0.125,
                    "Rmax_LTAR": 22.25,
                },
            )

            data_tokens = _tokens(var_path.read_text(encoding="utf-8").splitlines()[3])

        self.assertEqual(data_tokens[0], "1")
        self.assertEqual(data_tokens[1], "2")
        self.assertAlmostEqual(float(data_tokens[2]), 9.5)
        self.assertAlmostEqual(float(data_tokens[3]), 0.125)
        self.assertAlmostEqual(float(data_tokens[4]), 22.25)
        self.assertEqual(data_tokens[5:], ["6", "7"])

    def test_write_soi_parameters_updates_expected_soil_columns(self):
        with tempfile.TemporaryDirectory(prefix="codex_soi_") as tmp_dir:
            soi_path = Path(tmp_dir) / "soil.soi"
            _write_synthetic_soi(soi_path)

            write_soi_parameters(
                soi_path,
                {
                    "thetaS": 0.43,
                    "n": 1.71,
                },
            )

            data_tokens = _tokens(soi_path.read_text(encoding="utf-8").splitlines()[2])

        self.assertEqual(data_tokens[0], "0.05")
        self.assertAlmostEqual(float(data_tokens[1]), 0.43)
        self.assertEqual(data_tokens[2], "2")
        self.assertAlmostEqual(float(data_tokens[3]), 0.43)
        self.assertEqual(data_tokens[4], "4")
        self.assertAlmostEqual(float(data_tokens[5]), 1.71)
        self.assertEqual(data_tokens[6], "6")
        self.assertEqual(data_tokens[7], "7")
        self.assertAlmostEqual(float(data_tokens[8]), 0.43)
        self.assertEqual(data_tokens[9:], ["9", "10"])

    def test_write_member_parameters_updates_var_and_soi_in_member_directory(self):
        with tempfile.TemporaryDirectory(prefix="codex_member_params_") as tmp_dir:
            run_dir = Path(tmp_dir)
            var_path = run_dir / "crop.var"
            soi_path = run_dir / "soil.soi"
            _write_synthetic_var(var_path)
            _write_synthetic_soi(soi_path)

            write_member_parameters(
                run_dir,
                {
                    "StayGreen": 8.0,
                    "LM_min": 0.2,
                    "Rmax_LTAR": 18.0,
                    "thetaS": 0.45,
                    "n": 1.8,
                },
                "crop.var",
                "soil.soi",
            )

            var_tokens = _tokens(var_path.read_text(encoding="utf-8").splitlines()[3])
            soi_tokens = _tokens(soi_path.read_text(encoding="utf-8").splitlines()[2])

        self.assertAlmostEqual(float(var_tokens[2]), 8.0)
        self.assertAlmostEqual(float(var_tokens[3]), 0.2)
        self.assertAlmostEqual(float(var_tokens[4]), 18.0)
        self.assertAlmostEqual(float(soi_tokens[1]), 0.45)
        self.assertAlmostEqual(float(soi_tokens[3]), 0.45)
        self.assertAlmostEqual(float(soi_tokens[5]), 1.8)
        self.assertAlmostEqual(float(soi_tokens[8]), 0.45)


if __name__ == "__main__":
    unittest.main()
