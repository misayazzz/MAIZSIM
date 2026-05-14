import inspect
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:  # pragma: no cover - supports direct file execution.
    import context  # noqa: F401
from da_framework.ensemble import (
    check_ensemble_outputs,
    member_name,
    prepare_ensemble,
    prepare_member_directory,
    run_ensemble,
    write_ensemble_parameters,
)


def _write_base_inputs(base_dir):
    (base_dir / "crop.var").write_text(
        "\n".join(
            [
                "header one",
                "header two",
                "header three",
                "1 2 3 4 5 6 7",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (base_dir / "soil.soi").write_text(
        "\n".join(
            [
                "soil header one",
                "soil header two",
                "0.05 0.30 2 0.31 4 1.20 6 7 0.32 9 10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (base_dir / "run.dat").write_text("run file\n", encoding="utf-8")


def _tokens(line):
    return line.split()


class EnsembleTests(unittest.TestCase):
    def test_run_ensemble_defaults_workers_to_twelve(self):
        default_workers = inspect.signature(run_ensemble).parameters[
            "max_workers"
        ].default

        self.assertEqual(default_workers, 12)

    def test_prepare_member_directory_copies_inputs_and_cleans_outputs(self):
        with tempfile.TemporaryDirectory(prefix="codex_prepare_member_") as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "base"
            member_dir = root / "ensemble" / member_name(1)
            base_dir.mkdir()
            _write_base_inputs(base_dir)
            (base_dir / "old.g01").write_text("stale output\n", encoding="utf-8")
            (base_dir / "old.G03").write_text("stale output\n", encoding="utf-8")
            member_dir.mkdir(parents=True)
            (member_dir / "old.G04").write_text("old member\n", encoding="utf-8")
            copied_sources = []

            def copy_recorder(src, dst):
                copied_sources.append(Path(src).name)
                return shutil.copy2(src, dst)

            with patch(
                "da_framework.ensemble._copy_member_file",
                side_effect=copy_recorder,
            ):
                prepared = prepare_member_directory(base_dir, member_dir)

            self.assertEqual(prepared, member_dir)
            self.assertTrue((member_dir / "crop.var").is_file())
            self.assertTrue((member_dir / "soil.soi").is_file())
            self.assertTrue((member_dir / "run.dat").is_file())
            self.assertFalse((member_dir / "old.g01").exists())
            self.assertFalse((member_dir / "old.G03").exists())
            self.assertFalse((member_dir / "old.G04").exists())
            self.assertNotIn("old.g01", copied_sources)
            self.assertNotIn("old.G03", copied_sources)

    def test_prepare_member_directory_falls_back_when_hardlink_fails(self):
        with tempfile.TemporaryDirectory(prefix="codex_hardlink_fallback_") as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "base"
            member_dir = root / "ensemble" / member_name(1)
            base_dir.mkdir()
            _write_base_inputs(base_dir)
            (base_dir / "2dMAIZSIM.exe").write_bytes(b"exe")
            (base_dir / "Maizsim.dll").write_bytes(b"dll")

            with patch(
                "da_framework.ensemble.os.link",
                side_effect=OSError("hardlink unavailable"),
            ) as link_mock:
                prepare_member_directory(base_dir, member_dir)

            linked_names = {Path(call.args[0]).name for call in link_mock.call_args_list}

            self.assertEqual((member_dir / "2dMAIZSIM.exe").read_bytes(), b"exe")
            self.assertEqual((member_dir / "Maizsim.dll").read_bytes(), b"dll")
            self.assertEqual(linked_names, {"2dMAIZSIM.exe", "Maizsim.dll"})
            self.assertTrue((member_dir / "crop.var").is_file())
            self.assertTrue((member_dir / "soil.soi").is_file())
            self.assertTrue((member_dir / "run.dat").is_file())

    def test_prepare_member_directory_minimal_outputs_updates_run_file(self):
        with tempfile.TemporaryDirectory(prefix="codex_minimal_outputs_") as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "base"
            member_dir = root / "ensemble" / member_name(1)
            base_dir.mkdir()
            _write_base_inputs(base_dir)
            (base_dir / "run.dat").write_text(
                "\n".join(
                    [
                        "LOAM2D.wea",
                        "MassBl.dat",
                        "LOAM2D.g01",
                        "LOAM2D.g02",
                        "LOAM2D.G03",
                        "LOAM2D.G04",
                        "LOAM2D.G05",
                        "LOAM2D.G06",
                        "LOAM2D.G07",
                        "MassBl.out",
                        "MassBlRunOff.out",
                        "MassBlMulch.out",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            prepare_member_directory(
                base_dir,
                member_dir,
                minimal_outputs=True,
            )
            lines = (member_dir / "run.dat").read_text(encoding="utf-8").splitlines()

        self.assertEqual(lines[0], "LOAM2D.wea")
        self.assertEqual(lines[1], "MassBl.dat")
        self.assertEqual(lines[2], "LOAM2D.g01")
        self.assertEqual(lines[3], "LOAM2D.g02")
        self.assertEqual(lines[4], "LOAM2D.G03")
        self.assertEqual(lines[5:], ["NONE"] * 7)

    def test_prepare_ensemble_and_write_parameters_per_member(self):
        with tempfile.TemporaryDirectory(prefix="codex_ensemble_") as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "base"
            ensemble_dir = root / "ensemble"
            base_dir.mkdir()
            _write_base_inputs(base_dir)

            member_dirs = prepare_ensemble(base_dir, ensemble_dir, 2)
            parameter_frame = pd.DataFrame(
                [
                    {
                        "StayGreen": 7.0,
                        "LM_min": 0.11,
                        "Rmax_LTAR": 18.0,
                        "thetaS": 0.41,
                        "n": 1.6,
                    },
                    {
                        "StayGreen": 8.0,
                        "LM_min": 0.12,
                        "Rmax_LTAR": 19.0,
                        "thetaS": 0.42,
                        "n": 1.7,
                    },
                ]
            )

            write_ensemble_parameters(
                member_dirs,
                parameter_frame,
                var_file="crop.var",
                soi_file="soil.soi",
            )

            self.assertEqual([path.name for path in member_dirs], ["000001", "000002"])
            first_var = _tokens(
                (member_dirs[0] / "crop.var")
                .read_text(encoding="utf-8")
                .splitlines()[3]
            )
            second_soi = _tokens(
                (member_dirs[1] / "soil.soi")
                .read_text(encoding="utf-8")
                .splitlines()[2]
            )

        self.assertAlmostEqual(float(first_var[2]), 7.0)
        self.assertAlmostEqual(float(first_var[3]), 0.11)
        self.assertAlmostEqual(float(first_var[4]), 18.0)
        self.assertAlmostEqual(float(second_soi[1]), 0.42)
        self.assertAlmostEqual(float(second_soi[5]), 1.7)
        self.assertAlmostEqual(float(second_soi[8]), 0.42)

    def test_check_ensemble_outputs_requires_g01_and_g03_for_each_member(self):
        with tempfile.TemporaryDirectory(prefix="codex_check_outputs_") as tmp_dir:
            root = Path(tmp_dir)
            member_dirs = [root / "000001", root / "000002"]
            for member_dir in member_dirs:
                member_dir.mkdir()
                (member_dir / "member.g01").write_text("Date,LAI\n", encoding="utf-8")
                (member_dir / "member.G03").write_text(
                    "Date,Y,thNew,Area\n",
                    encoding="utf-8",
                )

            check_ensemble_outputs(member_dirs)
            (member_dirs[1] / "member.G03").unlink()

            with self.assertRaises(FileNotFoundError) as exc:
                check_ensemble_outputs(member_dirs)

        self.assertIn("000002", str(exc.exception))
        self.assertIn(".G03", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
