import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

try:
    from . import context
except ImportError:  # pragma: no cover - supports direct file execution.
    import context


TOOLS_DIR = context.REPO_ROOT / "示例输入" / "ExcelInterface-master" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from maizsim_inputs.drip import NO_DRIP_LINES  # noqa: E402
from maizsim_inputs.drip import validate_drip_records_for_run  # noqa: E402
from maizsim_inputs.drip import write_run_drip_file  # noqa: E402
from maizsim_inputs.errors import ConfigError  # noqa: E402


def _write_run_file(run_dir, drip_name="TEST.drp"):
    lines = [
        "TEST.wea",
        "TEST.tim",
        "BiologyDefault.bio",
        "Climate.dat",
        "TEST.nit",
        "NitrogenDefault.sol",
        "GasID.gas.gas",
        "Soil.soi",
        "MulchGeo1.mul",
        "TEST.man",
        "TEST.irr",
        drip_name,
        "WaterMovDefault.dat",
    ]
    (run_dir / "run.dat").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_grid_file(path):
    path.write_text(
        "\n".join(
            [
                "***************** GRID GENERATOR INFORMATION **********************************************",
                "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
                "  2       4       0       4     2     1",
                "   n           x          y      MatNum",
                "    1     0       10       1",
                "    2     5       10       1",
                "    3     10      10       1",
                "    4     5        0       1",
                "****************Boundary geometry information**************************************",
                "    n  CodeW  CodeC  CodeH  CodeG  Width",
                "    1 -4    0     -4    -4      1.0",
                "    2  1    0     -4    -4      1.0",
                "    3  4    0     -4    -4      1.0",
                "    4 -2    0      1     1      1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _drip_record(distance=8.6):
    return {
        "__row_number__": 2,
        "id": "TEST",
        "date": date(2024, 5, 1),
        "ratecmhr": 0.25,
        "starttime": 8,
        "stoptime": 10,
        "distance": distance,
    }


class MaizsimDripInputTests(unittest.TestCase):
    def test_zero_drip_writes_legacy_compatible_format(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_zero_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"

            result = write_run_drip_file(
                {"id": "TEST", "drip_records": [], "drip_node_records": []},
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )

            self.assertEqual(result["event_count"], 0)
            self.assertEqual((run_dir / "TEST.drp").read_text(encoding="utf-8"), "\n".join(NO_DRIP_LINES) + "\n")

    def test_distance_maps_to_nearest_surface_water_boundary_node(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_distance_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)

            write_run_drip_file(
                {"id": "TEST", "drip_records": [_drip_record()], "drip_node_records": []},
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )

            lines = (run_dir / "TEST.drp").read_text(encoding="utf-8").splitlines()
            self.assertIn("5/1/2024 8 5/1/2024 10 0.25 1", lines)
            self.assertEqual(lines[-1].strip(), "3")

    def test_optional_pressure_fields_are_written_when_enabled(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_pressure_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)
            record = _drip_record()
            record.update(
                {
                    "dripmode": 2,
                    "driphin": 100,
                    "dripexp": 0.5,
                    "drippcmin": 50,
                    "drippcmax": 150,
                }
            )

            write_run_drip_file(
                {
                    "id": "TEST",
                    "drip_records": [record],
                    "drip_node_records": [],
                },
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )

            lines = (run_dir / "TEST.drp").read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "5/1/2024 8 5/1/2024 10 0.25 1 2 100 0.5 50 150",
                lines,
            )

    def test_optional_wet_width_limit_is_written_without_pressure(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_wet_width_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)
            record = _drip_record()
            record["dripwetwidthmax"] = 18

            write_run_drip_file(
                {
                    "id": "TEST",
                    "drip_records": [record],
                    "drip_node_records": [],
                },
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )

            lines = (run_dir / "TEST.drp").read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "5/1/2024 8 5/1/2024 10 0.25 1 0 0 1 0 0 18",
                lines,
            )

    def test_explicit_drip_nodes_take_priority_over_distance(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_nodes_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)

            write_run_drip_file(
                {
                    "id": "TEST",
                    "drip_records": [_drip_record(distance=10)],
                    "drip_node_records": [{"__row_number__": 2, "id": "TEST", "nodes": "1, 3"}],
                },
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )

            lines = (run_dir / "TEST.drp").read_text(encoding="utf-8").splitlines()
            self.assertIn("5/1/2024 8 5/1/2024 10 0.25 2", lines)
            self.assertEqual(lines[-1].strip(), "1 3")

    def test_explicit_drip_nodes_must_be_surface_water_boundary_nodes(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_bad_node_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)

            with self.assertRaisesRegex(ConfigError, "不是 abs\\(CodeW\\)==4"):
                write_run_drip_file(
                    {
                        "id": "TEST",
                        "drip_records": [_drip_record()],
                        "drip_node_records": [{"__row_number__": 2, "id": "TEST", "nodes": "2"}],
                    },
                    {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
                )

    def test_distance_is_required_without_explicit_nodes(self):
        record = _drip_record()
        record["distance"] = ""

        with self.assertRaisesRegex(ConfigError, "Distance"):
            validate_drip_records_for_run("TEST", [record], [])

    def test_pressure_mode_requires_positive_head(self):
        record = _drip_record()
        record["dripmode"] = 1
        record["driphin"] = 0

        with self.assertRaisesRegex(ConfigError, "DripHIn"):
            validate_drip_records_for_run("TEST", [record], [])

    def test_wet_width_limit_cannot_be_negative(self):
        record = _drip_record()
        record["dripwetwidthmax"] = -1

        with self.assertRaisesRegex(ConfigError, "DripWetWidthMax"):
            validate_drip_records_for_run("TEST", [record], [])


if __name__ == "__main__":
    unittest.main()
