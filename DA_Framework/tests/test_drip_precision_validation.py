import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework import drip_precision_validation as precision


class DripPrecisionValidationTests(unittest.TestCase):
    def test_parse_args_requires_explicit_workspaces(self):
        args = precision._parse_args(
            [
                "--regression-root",
                "regression",
                "--short-root",
                "short",
                "--output-dir",
                "out",
                "--executable-dir",
                "exe",
                "--figures-only",
            ]
        )

        self.assertEqual(args.regression_root, "regression")
        self.assertEqual(args.short_root, "short")
        self.assertEqual(args.output_dir, "out")
        self.assertEqual(args.executable_dir, "exe")
        self.assertTrue(args.figures_only)

    def test_case_matrix_reports_drip_accounting_residuals(self):
        original_root = precision.REGRESSION_ROOT
        with tempfile.TemporaryDirectory(prefix="codex_precision_matrix_") as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "loam__base_x100__baseline"
            drip = root / "loam__base_x100__long_high_single"
            baseline.mkdir()
            drip.mkdir()
            (baseline / "LOAM2D.G05").write_text(_g05_text(), encoding="utf-8")
            (drip / "LOAM2D.G05").write_text(
                _g05_text(
                    drip_input=10.0,
                    drip_demand=11.0,
                    pressure_loss=0.75,
                    hydraulic_excess=0.5,
                    actual_infil=8.0,
                    source_input=9.0,
                    source_loss=0.5,
                    width=20.0,
                ),
                encoding="utf-8",
            )
            (drip / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1 3 0 1 0 0 20 2"),
                encoding="utf-8",
            )
            try:
                precision.REGRESSION_ROOT = root

                matrix = precision._build_case_matrix()
            finally:
                precision.REGRESSION_ROOT = original_root

        row = matrix.loc[matrix["scenario"] == "long_high_single"].iloc[0]
        self.assertAlmostEqual(row["demand_input_loss_residual_mm"], 0.25)
        self.assertAlmostEqual(row["input_source_residual_mm"], 0.5)
        self.assertAlmostEqual(row["input_acceptance_residual_mm"], 1.5)
        self.assertEqual(row["active_output_rows"], 1)
        self.assertEqual(row["spread_modes"], "2")

    def test_g05_roundoff_tolerance_scales_with_output_rows(self):
        frame = pd.DataFrame({"active_output_rows": [46]})

        tolerance = precision._g05_sum_roundoff_tolerance(frame)

        self.assertAlmostEqual(tolerance, 0.046)
        self.assertAlmostEqual(
            precision._g05_sum_roundoff_tolerance(pd.DataFrame()),
            0.01,
        )

    def test_scale_grid_around_node_expands_domain_without_moving_dripper(self):
        with tempfile.TemporaryDirectory(prefix="codex_precision_grid_") as tmp_dir:
            grid_path = Path(tmp_dir) / "mini.grd"
            grid_path.write_text(_mini_grid(), encoding="utf-8")

            precision._scale_grid_around_node(grid_path, center_node=7, x_scale=2.5)

            center_x, _ = precision._grid_node_xy(grid_path, 7)
            widths, _ = precision.grid_surface_widths(grid_path)
            coverage = precision._partial_coverage_at_target(
                grid_path,
                center_node=7,
                target_width=20.0,
            )

        self.assertAlmostEqual(center_x, 5.0)
        self.assertAlmostEqual(widths[7], 5.0)
        self.assertAlmostEqual(coverage["domain_clip_loss_cm"], 0.0)

    def test_refine_grid_fixed_domain_rewrites_grid_and_nodal_file(self):
        repo = Path(__file__).resolve().parents[2]
        base = repo / "DA_Framework" / "base_runs" / "SingleLayerLoam2D"
        with tempfile.TemporaryDirectory(prefix="codex_precision_refine_") as tmp_dir:
            run_dir = Path(tmp_dir)
            shutil.copy2(base / "LOAM2D.grd", run_dir / "LOAM2D.grd")
            shutil.copy2(base / "LOAM2D.nod", run_dir / "LOAM2D.nod")

            info = precision._refine_grid_fixed_domain(
                run_dir / "LOAM2D.grd",
                refinement_factor=2,
                center_node=7,
                x_scale=1.0,
            )

            widths, grid_width = precision.grid_surface_widths(
                run_dir / "LOAM2D.grd"
            )
            nod_rows = [
                line
                for line in (run_dir / "LOAM2D.nod").read_text(
                    encoding="utf-8"
                ).splitlines()[2:]
                if line.strip()
            ]

        self.assertEqual(info["x_node_count"], 19)
        self.assertEqual(info["node_count"], 646)
        self.assertEqual(info["element_count"], 594)
        self.assertEqual(info["boundary_count"], 38)
        self.assertEqual(info["solver_bandwidth"], 20)
        self.assertEqual(info["drip_node"], 13)
        self.assertAlmostEqual(info["drip_node_x_cm"], 12.24)
        self.assertAlmostEqual(info["reference_source_width_cm"], 4.84)
        self.assertAlmostEqual(grid_width, 38.1)
        self.assertAlmostEqual(widths[13], 2.42)
        self.assertEqual(len(nod_rows), info["node_count"])

    def test_timestep_errors_are_relative_to_finest_step(self):
        frame = pd.DataFrame(
            [
                _timestep_row("loam", 0.01, 8.0),
                _timestep_row("loam", 0.005, 9.0),
                _timestep_row("loam", 0.0025, 10.0),
            ]
        )

        errors = precision._timestep_errors_against_reference(frame)
        accepted = errors[errors["dtmx_days"] == 0.005].iloc[0]

        self.assertAlmostEqual(accepted["drip_actual_infil_mm_error"], -1.0)
        self.assertAlmostEqual(accepted["drip_actual_infil_mm_rel_error"], 0.1)

    def test_spatial_diagnostics_cover_every_active_case(self):
        original_root = precision.REGRESSION_ROOT
        with tempfile.TemporaryDirectory(prefix="codex_precision_spatial_") as tmp_dir:
            root = Path(tmp_dir)
            _write_spatial_case(root, "loam", "base_x100", "baseline", 0.20)
            _write_spatial_case(root, "loam", "base_x100", "long_low_single", 0.28)
            _write_spatial_case(root, "loam", "wide_x125", "baseline", 0.20)
            _write_spatial_case(root, "loam", "wide_x125", "long_high_single", 0.30)
            try:
                precision.REGRESSION_ROOT = root

                spatial = precision._build_spatial_diagnostics()
                temporal = precision._build_spatial_temporal_diagnostics()
            finally:
                precision.REGRESSION_ROOT = original_root

        self.assertEqual(len(spatial), 2)
        self.assertEqual(len(temporal), 2)
        self.assertEqual(
            set(spatial["case"]),
            {
                "loam__base_x100__long_low_single",
                "loam__wide_x125__long_high_single",
            },
        )
        self.assertTrue((spatial["delta_theta_max"] > 0.005).all())
        self.assertTrue((spatial["root_weighted_delta_theta"] > 0.0).all())
        self.assertTrue((spatial["positive_delta_storage_cm2"] > 0.1).all())
        self.assertTrue(
            (spatial["positive_delta_root_storage_fraction"] == 1.0).all()
        )
        self.assertTrue((spatial["root_area_cm2"] > 0.0).all())
        self.assertEqual(set(temporal["date"]), {"06/01/2007"})
        self.assertTrue((temporal["positive_delta_storage_cm2"] > 0.1).all())

    def test_select_timeline_dates_spans_available_period(self):
        dates = pd.date_range("2007-05-20", periods=7, freq="D").strftime(
            "%m/%d/%Y"
        )

        selected = precision._select_timeline_dates(dates, max_dates=4)

        self.assertEqual(
            selected,
            ("05/20/2007", "05/22/2007", "05/24/2007", "05/26/2007"),
        )

    def test_select_spatial_worst_cases_exposes_distinct_weak_cases(self):
        frame = pd.DataFrame(
            [
                _spatial_summary_row("case_root_storage", root_storage=0.2),
                _spatial_summary_row("case_root_weighted", root_weighted=-0.03),
                _spatial_summary_row("case_net_storage", net_storage=-6.0),
                _spatial_summary_row("case_positive_storage", positive_storage=0.05),
                _spatial_summary_row("case_negative_storage", negative_storage=8.0),
                _spatial_summary_row("case_depth_width", depth_width=4.0),
                _spatial_summary_row("case_background"),
            ]
        )

        selected = precision._select_spatial_worst_cases(frame, max_cases=6)

        self.assertEqual(len(selected), 6)
        self.assertEqual(set(selected["case"]), set(frame["case"].iloc[:6]))
        self.assertIn("selection_reason", selected.columns)
        self.assertTrue((selected["selection_metric_count"] >= 1).all())

    def test_direct_source_bypass_cases_flags_journal_unsafe_mode(self):
        original_root = precision.REGRESSION_ROOT
        with tempfile.TemporaryDirectory(prefix="codex_precision_bypass_") as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "loam__base_x100__baseline"
            bypass = root / "loam__base_x100__long_low_single"
            coupled = root / "loam__base_x100__long_high_single"
            baseline.mkdir()
            bypass.mkdir()
            coupled.mkdir()
            (bypass / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1 3 0 1 0 0 20 1"),
                encoding="utf-8",
            )
            (coupled / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1 3 0 1 0 0 20 2"),
                encoding="utf-8",
            )
            try:
                precision.REGRESSION_ROOT = root

                cases = precision._direct_source_bypass_cases()
            finally:
                precision.REGRESSION_ROOT = original_root

        self.assertEqual(cases, ["loam__base_x100__long_low_single"])


def _g05_text(
    drip_input=0.0,
    drip_demand=0.0,
    pressure_loss=0.0,
    hydraulic_excess=0.0,
    actual_infil=0.0,
    source_input=0.0,
    source_loss=0.0,
    width=0.0,
):
    return "\n".join(
        [
            (
                "Date,CumRain,infil,Runoff,Drainage,DripInput,DripDemand,"
                "DripPressureLoss,DripHydraulicExcess,DripActualInfil,"
                "DripSourceInput,DripSourceLoss,DripWetNodesMax,"
                "DripWetWidthMean,DripWetWidthMax"
            ),
            (
                f"05/01/2007,0,0,0,0,{drip_input},{drip_demand},"
                f"{pressure_loss},{hydraulic_excess},{actual_infil},"
                f"{source_input},{source_loss},1,{width},{width}"
            ),
        ]
    ) + "\n"


def _drip_text(event_line):
    return "\n".join(
        [
            "*****Script for Drip application module",
            "Number of Drip irrigations(max=75)",
            "1",
            "StartDate StartHour StopDate StopHour RateCmHr NumNodes",
            event_line,
            "Drip nodes",
            "7",
        ]
    ) + "\n"


def _spatial_summary_row(
    case,
    *,
    root_storage=1.0,
    root_weighted=0.02,
    net_storage=4.0,
    positive_storage=3.0,
    negative_storage=0.2,
    depth_width=1.0,
):
    return {
        "case": case,
        "soil": "loam",
        "grid": "base_x100",
        "scenario": "long_high_single",
        "date": "06/01/2007",
        "positive_delta_root_storage_fraction": root_storage,
        "root_weighted_delta_theta": root_weighted,
        "net_delta_storage_cm2": net_storage,
        "positive_delta_storage_cm2": positive_storage,
        "negative_delta_storage_cm2": negative_storage,
        "positive_delta_depth_width_ratio": depth_width,
    }


def _mini_grid():
    return "\n".join(
        [
            "Header",
            "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
            "  2       3       0       3     2     1",
            "   n           x          y      MatNum",
            "    1     0       10       1",
            "    7     5       10       1",
            "    3     10      10       1",
            "****************Boundary geometry information**************************************",
            "    n  CodeW  CodeC  CodeH  CodeG  Width",
            "    1 -4    0     -4    -4      2.0",
            "    7 -4    0     -4    -4      2.0",
            "    3  4    0     -4    -4      2.0",
            "Seepage face information",
            "label",
            "0",
            "Drainage boundary information",
            "label",
            "0",
        ]
    ) + "\n"


def _timestep_row(soil, dtmx_days, actual_infil):
    return {
        "soil": soil,
        "grid": "base_x100",
        "scenario": "long_high_single",
        "dtmx_days": dtmx_days,
        "dtmx_minutes": dtmx_days * 24.0 * 60.0,
        "drip_input_mm": 12.0,
        "drip_actual_infil_mm": actual_infil,
        "drip_hydraulic_excess_mm": 12.0 - actual_infil,
        "drip_wet_width_max_cm": 20.0,
    }


def _write_spatial_case(root, soil, grid, scenario, theta):
    case_dir = root / f"{soil}__{grid}__{scenario}"
    case_dir.mkdir()
    (case_dir / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
    (case_dir / "LOAM2D.G03").write_text(_g03_text(theta), encoding="utf-8")
    if scenario != "baseline":
        (case_dir / "LOAM2D.G04").write_text(_g04_text(), encoding="utf-8")


def _g03_text(theta):
    rows = [
        ("1", "06/01/2007", 0.0, 100.0, 0.20, 1.0),
        ("1", "06/01/2007", 5.0, 100.0, theta, 1.0),
        ("1", "06/01/2007", 10.0, 100.0, 0.20, 1.0),
        ("1", "06/01/2007", 5.0, 90.0, theta - 0.01, 1.0),
    ]
    lines = ["Date_time,Date,X,Y,thNew,Area"]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"


def _g04_text():
    rows = [
        ("1", "06/01/2007", 0.0, 100.0, 0.1, 0.0, 1.0),
        ("1", "06/01/2007", 5.0, 100.0, 0.2, 0.0, 1.0),
        ("1", "06/01/2007", 10.0, 100.0, 0.1, 0.0, 1.0),
        ("1", "06/01/2007", 5.0, 90.0, 0.2, 0.0, 1.0),
    ]
    lines = ["Date_time,Date,X,Y,RDenM,RDenY,Area"]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    unittest.main()
