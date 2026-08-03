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


def _write_grid_file(path, kat=2):
    path.write_text(
        "\n".join(
            [
                "***************** GRID GENERATOR INFORMATION **********************************************",
                "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
                f"  {kat}       4       0       4     2     1",
                "   n           x          y      MatNum",
                "    1     0       10       1",
                "    2     5       10       1",
                "    3     10      10       1",
                "    4     5        0       1",
                "****************Boundary geometry information**************************************",
                "    n  CodeW  CodeC  CodeH  CodeG  Width",
                "    1 -4    0     -4    -4      2.5",
                "    2 -4    0     -4    -4      5.0",
                "    3  4    0     -4    -4      2.5",
                "    4 -2    0      1     1      5.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _drip_record(**updates):
    record = {
        "__row_number__": 2,
        "id": "TEST",
        "date": date(2024, 5, 1),
        "starttime": 8,
        "stoptime": 10,
        "emitterflowlph": 1.6,
        "emitterspacingcm": 30.0,
        "contactwidthcm": 2.0,
    }
    record.update(updates)
    return record


class MaizsimDripInputTests(unittest.TestCase):
    def test_zero_drip_writes_supported_format(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_zero_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            result = write_run_drip_file(
                {"id": "TEST", "drip_records": [], "drip_node_records": []},
                {"id": "TEST", "run_dir": run_dir, "grid_file": run_dir / "TEST.grd"},
            )
            self.assertEqual(result["event_count"], 0)
            self.assertEqual(
                (run_dir / "TEST.drp").read_text(encoding="utf-8"),
                "\n".join(NO_DRIP_LINES) + "\n",
            )

    def test_writer_uses_flow_spacing_contact_and_auto_x_zero_node(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_line_source_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)
            write_run_drip_file(
                {"id": "TEST", "drip_records": [_drip_record()], "drip_node_records": []},
                {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
            )
            lines = (run_dir / "TEST.drp").read_text(encoding="utf-8").splitlines()
            self.assertIn("EmitterFlowLph EmitterSpacingCm ContactWidthCm", lines[3])
            self.assertEqual(lines[4], "5/1/2024 8 5/1/2024 10 1.6 30 2 1")
            self.assertEqual(lines[-1].strip(), "1")

    def test_explicit_node_must_be_the_x_zero_surface_node(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_bad_axis_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)
            with self.assertRaisesRegex(ConfigError, "x=0"):
                write_run_drip_file(
                    {
                        "id": "TEST",
                        "drip_records": [_drip_record()],
                        "drip_node_records": [
                            {"__row_number__": 2, "id": "TEST", "nodes": "3"}
                        ],
                    },
                    {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
                )

    def test_cartesian_grid_is_required(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_bad_kat_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file, kat=1)
            with self.assertRaisesRegex(ConfigError, "KAT=2"):
                write_run_drip_file(
                    {"id": "TEST", "drip_records": [_drip_record()], "drip_node_records": []},
                    {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
                )

    def test_required_physical_fields_are_positive(self):
        for field in ("emitterflowlph", "emitterspacingcm", "contactwidthcm"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ConfigError, "必须大于 0"):
                    validate_drip_records_for_run("TEST", [_drip_record(**{field: 0})], [])

    def test_removed_mode_fields_are_rejected(self):
        for field, value in (
            ("ratecmhr", 0.25),
            ("dripmode", 1),
            ("dripspreadmode", 6),
            ("dripsourcewidth", 2.0),
            ("dripwetwidthmax", 20.0),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ConfigError, "已删除"):
                    validate_drip_records_for_run(
                        "TEST", [_drip_record(**{field: value})], []
                    )

    def test_spacing_contact_and_event_windows_are_fixed(self):
        with tempfile.TemporaryDirectory(prefix="codex_drp_fixed_contract_") as tmp_dir:
            run_dir = Path(tmp_dir)
            _write_run_file(run_dir)
            grid_file = run_dir / "TEST.grd"
            _write_grid_file(grid_file)
            cases = [
                ([_drip_record(), _drip_record(starttime=10, stoptime=12, emitterspacingcm=40)], "EmitterSpacingCm"),
                ([_drip_record(), _drip_record(starttime=10, stoptime=12, contactwidthcm=3)], "ContactWidthCm"),
                ([_drip_record(), _drip_record(starttime=9, stoptime=11)], "不能相互重叠"),
            ]
            for records, pattern in cases:
                with self.subTest(pattern=pattern):
                    with self.assertRaisesRegex(ConfigError, pattern):
                        write_run_drip_file(
                            {"id": "TEST", "drip_records": records, "drip_node_records": []},
                            {"id": "TEST", "run_dir": run_dir, "grid_file": grid_file},
                        )


if __name__ == "__main__":
    unittest.main()
