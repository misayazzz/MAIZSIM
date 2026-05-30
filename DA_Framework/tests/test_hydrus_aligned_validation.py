import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.hydrus_aligned_validation import (
    HydrusBoundary,
    _g05_drip_diagnostics,
    read_hydrus_boundary_text,
    write_threshold_sensitivity_outputs,
    write_maizsim_drip_file,
    write_maizsim_grid_from_hydrus,
    write_zero_weather_header_file,
    write_zero_weather_file,
)
from da_framework.hydrus_official_export import (
    HydrusDimensions,
    HydrusMesh,
    HydrusOfficialProject,
    HydrusThetaOutput,
)


class HydrusAlignedValidationTests(unittest.TestCase):
    def test_read_hydrus_boundary_text_joins_mesh_and_roles(self):
        mesh = _project().mesh
        boundary = read_hydrus_boundary_text(
            "\n".join(
                [
                    "Node Number Array",
                    " 1 2 3",
                    "Width Array",
                    " 0.5 4.0 2.5",
                    "Length of soil surface associated with transpiration",
                ]
            ),
            mesh,
        )

        self.assertEqual(list(boundary.nodes["node"]), [1, 2, 3])
        np.testing.assert_allclose(boundary.nodes["width"], [0.5, 4.0, 2.5])
        self.assertEqual(
            list(boundary.nodes["boundary_role"]),
            ["surface", "bottom", "surface"],
        )

    def test_write_maizsim_grid_from_hydrus_preserves_axisym_widths(self):
        project = _project()
        boundary = HydrusBoundary(
            nodes=pd.DataFrame(
                {
                    "node": [1, 2, 3],
                    "width": [0.5, 4.0, 2.5],
                    "x_cm": [0.0, 0.0, 10.0],
                    "z_cm": [10.0, 0.0, 10.0],
                    "depth_cm": [0.0, 10.0, 0.0],
                    "boundary_role": ["surface", "bottom", "surface"],
                }
            )
        )
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_aligned_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.grd"

            write_maizsim_grid_from_hydrus(project, boundary, path)

            text = path.read_text(encoding="utf-8")

        self.assertIn("  1     3     1     3     10     1", text)
        self.assertIn("    1   -4", text)
        self.assertIn("    2   -2", text)
        self.assertIn("NSeep\n 1\nNSP(1)\n 1", text)
        self.assertIn("0.5", text)
        self.assertIn("2.5", text)

    def test_write_maizsim_drip_file_uses_precision_mode_and_source_node(self):
        source = pd.Series({"node": 7})
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_drip_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.drp"

            write_maizsim_drip_file(
                path,
                source,
                123.45,
                21.9,
                drip_spread_mode=1,
            )

            text = path.read_text(encoding="utf-8")

        self.assertIn("DripSpreadMode", text)
        self.assertIn("123.45", text)
        self.assertIn(" 0 0 1 0 0 ", text)
        self.assertIn("21.9 1", text)
        self.assertTrue(text.rstrip().endswith("7"))

    def test_write_maizsim_drip_file_can_request_direct_split(self):
        source = pd.Series({"node": 7})
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_drip_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.drp"

            write_maizsim_drip_file(
                path,
                source,
                123.45,
                28.0,
                drip_source_depth_cm=18.5,
                drip_mode=3,
                drip_spread_mode=1,
            )

            text = path.read_text(encoding="utf-8")

        self.assertIn("123.45 1 3 0 1 0 18.5 28", text)

    def test_write_maizsim_drip_file_can_request_pressure_spread_mode(self):
        source = pd.Series({"node": 7})
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_drip_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.drp"

            write_maizsim_drip_file(
                path,
                source,
                123.45,
                0.0,
                drip_spread_mode=2,
            )

            text = path.read_text(encoding="utf-8")

        self.assertIn("123.45 1 0 0 1 0 0 0 2", text)

    def test_write_maizsim_drip_file_can_request_point_source_mode(self):
        source = pd.Series({"node": 7})
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_drip_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.drp"

            write_maizsim_drip_file(
                path,
                source,
                123.45,
                0.0,
                drip_spread_mode=4,
                drip_source_width_cm=2.5,
            )

            text = path.read_text(encoding="utf-8")

        self.assertIn("DripSourceWidth", text)
        self.assertIn("123.45 1 0 0 1 0 0 0 4 2.5", text)

    def test_write_maizsim_drip_file_rejects_point_source_without_width(self):
        source = pd.Series({"node": 7})
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_drip_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.drp"

            with self.assertRaisesRegex(ValueError, "drip_source_width_cm"):
                write_maizsim_drip_file(
                    path,
                    source,
                    123.45,
                    0.0,
                    drip_spread_mode=4,
                )

    def test_write_zero_weather_file_uses_saturated_air_for_no_evaporation(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_weather_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.wea"

            write_zero_weather_file(path)

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertIn("RH", lines[1])
        self.assertTrue(all(line.split()[-2] == "100" for line in lines[2:]))

    def test_write_zero_weather_header_file_disables_rh_cap(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_weather_") as tmp_dir:
            path = Path(tmp_dir) / "WyeClimate.dat"

            write_zero_weather_header_file(path)

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertIn("Rel_humid", lines[3])
        self.assertEqual(lines[4].split()[5], "0")

    def test_write_threshold_sensitivity_outputs_writes_csv_and_png(self):
        hydrus = _theta_field([0.20, 0.20, 0.30, 0.20])
        maizsim = _theta_field([0.20, 0.20, 0.28, 0.22])
        baseline = _theta_field([0.20, 0.20, 0.20, 0.20])
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_threshold_") as tmp_dir:
            outputs = write_threshold_sensitivity_outputs(
                maizsim,
                hydrus,
                baseline,
                baseline,
                tmp_dir,
                prefix="case",
                manifest={
                    "drip_x_cm": 0.0,
                    "drip_source_left_cm": -1.0,
                    "drip_source_right_cm": 1.0,
                },
                thresholds=(0.05, 0.10),
            )

            summary = pd.read_csv(outputs["summary_csv"])
            figure = Path(outputs["figure"])
            figure_exists = figure.exists()
            figure_size = figure.stat().st_size if figure_exists else 0

        self.assertEqual(list(summary["wet_delta_threshold"]), [0.05, 0.10])
        self.assertIn("source_wet_iou", summary.columns)
        self.assertTrue(figure_exists)
        self.assertGreater(figure_size, 0)

    def test_g05_drip_diagnostics_returns_drip_minus_baseline_sums(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_g05_diag_") as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline.G05"
            drip = root / "drip.G05"
            header = (
                "Date_time,Date,CumRain,infil,DripInput,DripDemand,"
                "DripPressureLoss,DripHydraulicExcess,DripActualInfil,"
                "DripSourceInput,DripSourceLoss\n"
            )
            baseline.write_text(
                header + "1.0,04/28/2007,0,0,0,0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            drip.write_text(
                header
                + "\n".join(
                    [
                        "1.0,04/28/2007,0,0,1.9,2.0,0.1,0.2,1.7,1.7,0.2",
                        "2.0,04/28/2007,0,0,3.0,3.0,0.0,0.1,2.9,2.8,0.2",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            metrics = _g05_drip_diagnostics(baseline, drip)

        self.assertAlmostEqual(metrics["g05_drip_demand_mm_sum"], 5.0)
        self.assertAlmostEqual(metrics["g05_drip_input_mm_sum"], 4.9)
        self.assertAlmostEqual(metrics["g05_drip_pressure_loss_mm_sum"], 0.1)
        self.assertAlmostEqual(metrics["g05_drip_hydraulic_excess_mm_sum"], 0.3)
        self.assertAlmostEqual(metrics["g05_drip_actual_infil_mm_sum"], 4.6)
        self.assertAlmostEqual(metrics["g05_drip_source_input_mm_sum"], 4.5)
        self.assertAlmostEqual(metrics["g05_drip_source_loss_mm_sum"], 0.4)
        self.assertAlmostEqual(metrics["g05_source_closure_residual_mm"], 0.1)
        self.assertAlmostEqual(metrics["g05_boundary_input_closure_residual_mm"], 0.0)
        self.assertAlmostEqual(metrics["g05_boundary_acceptance_residual_mm"], 0.0)


def _project():
    nodes = pd.DataFrame(
        {
            "node": [1, 2, 3],
            "x_cm": [0.0, 0.0, 10.0],
            "z_cm": [10.0, 0.0, 10.0],
            "depth_cm": [0.0, 10.0, 0.0],
            "area_cm2": [5.0, 5.0, 5.0],
        }
    )
    elements = pd.DataFrame(
        {
            "element": [1],
            "node1": [1],
            "node2": [2],
            "node3": [3],
        }
    )
    return HydrusOfficialProject(
        dimensions=HydrusDimensions(3, 1, 3, 1, 0),
        mesh=HydrusMesh(nodes=nodes, elements=elements),
        theta_output=HydrusThetaOutput(
            times_h=np.asarray([0.0]),
            theta=np.asarray([[0.2, 0.2, 0.2]]),
        ),
        selector_metadata={"kat": 1, "project_name": "mini"},
    )


def _theta_field(theta):
    return pd.DataFrame(
        {
            "x_cm": [0.0, 10.0, 0.0, 10.0],
            "depth_cm": [0.0, 0.0, 10.0, 10.0],
            "theta": theta,
            "area_cm2": [1.0, 1.0, 1.0, 1.0],
        }
    )


if __name__ == "__main__":
    unittest.main()
