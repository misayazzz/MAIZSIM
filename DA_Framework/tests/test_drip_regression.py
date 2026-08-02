import tempfile
import unittest
from pathlib import Path

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.drip_regression import DEFAULT_GRIDS
from da_framework.drip_regression import DEFAULT_SCENARIOS
from da_framework.drip_regression import DEFAULT_SOILS
from da_framework.drip_regression import DripScenario
from da_framework.drip_regression import REGRESSION_WATER_DTMX_DAYS
from da_framework.drip_regression import REQUIRED_OUTPUTS
from da_framework.drip_regression import RegressionCase
from da_framework.drip_regression import SoilVariant
from da_framework.drip_regression import build_regression_cases
from da_framework.drip_regression import grid_surface_widths
from da_framework.drip_regression import prepare_regression_case
from da_framework.drip_regression import render_drip_event_line
from da_framework.drip_regression import scale_grid_file
from da_framework.drip_regression import set_water_dtmax
from da_framework.drip_regression import validate_case_output
from da_framework.drip_regression import validate_matrix_outputs
from da_framework.drip_regression import write_soil_file
from da_framework.hydrus_drip_calibration import DRIP_WET_WIDTH_FALLBACK_CM
from da_framework.hydrus_drip_calibration import HYDRUS_SURFACE_DRIP_TARGETS
from da_framework.hydrus_drip_calibration import HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM
from da_framework.hydrus_drip_calibration import calibrated_drip_wet_width_max_cm
from da_framework.hydrus_drip_calibration import hydrus_surface_drip_width_cm
from da_framework.hydrus_drip_calibration import (
    read_hydrus_surface_drip_digitized_targets,
)


class DripRegressionTests(unittest.TestCase):
    def test_build_regression_cases_covers_full_matrix(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_matrix_") as tmp_dir:
            cases = build_regression_cases(Path(tmp_dir))

        self.assertEqual(
            len(cases),
            len(DEFAULT_SOILS) * len(DEFAULT_GRIDS) * (1 + len(DEFAULT_SCENARIOS)),
        )
        self.assertTrue(any(case.scenario is None for case in cases))
        self.assertTrue(any(case.scenario and case.scenario.pressure_reference for case in cases))
        self.assertIn(".G04", REQUIRED_OUTPUTS)

    def test_hydrus_surface_drip_calibration_targets(self):
        self.assertAlmostEqual(
            HYDRUS_SURFACE_DRIP_TARGETS["sandy_loam"].wet_width_max_cm,
            16.3,
        )
        self.assertAlmostEqual(
            HYDRUS_SURFACE_DRIP_TARGETS["loam"].wet_width_max_cm,
            39.7,
        )
        self.assertAlmostEqual(
            calibrated_drip_wet_width_max_cm("clay_loam"),
            DRIP_WET_WIDTH_FALLBACK_CM,
        )

    def test_render_drip_event_line_uses_soil_specific_hydrus_width(self):
        scenario = DEFAULT_SCENARIOS[0]

        sandy_line = render_drip_event_line(scenario, DEFAULT_SOILS[1])
        loam_line = render_drip_event_line(scenario, DEFAULT_SOILS[0])
        clay_line = render_drip_event_line(scenario, DEFAULT_SOILS[2])

        self.assertTrue(sandy_line.endswith("16.3 5 1.0"))
        self.assertTrue(loam_line.endswith("39.7 5 1.0"))
        self.assertTrue(clay_line.endswith("20 5 1.0"))
        self.assertNotIn("{wet_width_max_cm", sandy_line)

    def test_hydrus_surface_drip_width_curve_interpolates(self):
        self.assertAlmostEqual(
            hydrus_surface_drip_width_cm("sandy_loam", 0.3),
            16.3,
        )
        self.assertAlmostEqual(
            hydrus_surface_drip_width_cm("loam", 0.05),
            12.34,
        )
        self.assertGreater(
            hydrus_surface_drip_width_cm("loam", 1.0),
            hydrus_surface_drip_width_cm("loam", 0.3),
        )
        self.assertAlmostEqual(
            hydrus_surface_drip_width_cm(
                "clay_loam",
                0.5,
                wet_width_max_cm=20.0,
            ),
            10.0,
        )

    def test_hydrus_digitized_reference_csv_matches_code_curve(self):
        rows = read_hydrus_surface_drip_digitized_targets()
        grouped = {}
        for row in rows:
            grouped.setdefault(row["soil_name"], []).append(
                (row["elapsed_hours"], row["target_full_wet_width_cm"])
            )

        self.assertEqual(
            set(grouped),
            set(HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM),
        )
        for soil_name, curve in HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM.items():
            self.assertEqual(grouped[soil_name], list(curve))

    def test_write_soil_file_replaces_material_row(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_soil_") as tmp_dir:
            soil_path = Path(tmp_dir) / "test.soi"
            soil = SoilVariant(
                name="test",
                thr=0.050,
                ths=0.400,
                tha=0.050,
                thm=0.400,
                alpha=0.020,
                n=1.400,
                ks=12.0,
                kk=12.0,
                thk=0.400,
                bulk_density=1.300,
                organic_matter=0.001,
                sand=0.20,
                silt=0.40,
            )

            write_soil_file(soil_path, soil)

            text = soil_path.read_text(encoding="utf-8")
        self.assertIn("0.050", text)
        self.assertIn("12.000", text)
        self.assertIn("'m'", text)

    def test_scale_grid_file_updates_surface_widths(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_grid_") as tmp_dir:
            grid_path = Path(tmp_dir) / "mini.grd"
            grid_path.write_text(_mini_grid(), encoding="utf-8")

            original_widths, original_grid_width = grid_surface_widths(grid_path)
            scale_grid_file(grid_path, 1.25)
            scaled_widths, scaled_grid_width = grid_surface_widths(grid_path)

        self.assertAlmostEqual(scaled_widths[1], original_widths[1] * 1.25)
        self.assertAlmostEqual(scaled_widths[3], original_widths[3] * 1.25)
        self.assertAlmostEqual(scaled_grid_width, original_grid_width * 1.25)

    def test_prepare_regression_case_writes_case_inputs(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_prepare_") as tmp_dir:
            root = Path(tmp_dir)
            base = root / "base"
            exe_dir = root / "exe"
            case_dir = root / "case"
            _write_minimal_base_run(base)
            exe_dir.mkdir()
            (exe_dir / "2dMAIZSIM.exe").write_text("exe", encoding="utf-8")
            (exe_dir / "Maizsim.dll").write_text("dll", encoding="utf-8")
            case = RegressionCase(
                name="prepared",
                soil=DEFAULT_SOILS[1],
                grid=DEFAULT_GRIDS[2],
                scenario=DEFAULT_SCENARIOS[0],
                run_dir=case_dir,
            )

            prepare_regression_case(base, exe_dir, case)

            drip_text = (case_dir / "LOAM2D.drp").read_text(encoding="utf-8")
            soil_text = (case_dir / "Loam_200cm.soi").read_text(encoding="utf-8")
            water_values = (
                (case_dir / "WaterMovDefault.dat")
                .read_text(encoding="utf-8")
                .splitlines()[2]
                .split()
            )
            widths, grid_width = grid_surface_widths(case_dir / "LOAM2D.grd")

        self.assertIn("16.3", drip_text)
        self.assertNotIn("{wet_width_max_cm", drip_text)
        self.assertIn(f"{DEFAULT_SOILS[1].ks:.3f}", soil_text)
        self.assertAlmostEqual(float(water_values[5]), REGRESSION_WATER_DTMX_DAYS)
        self.assertGreater(grid_width, 0.0)
        self.assertIn(7, widths)

    def test_set_water_dtmax_updates_parameter_row(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_water_") as tmp_dir:
            water_path = Path(tmp_dir) / "WaterMovDefault.dat"
            water_path.write_text(
                "title\n"
                "MaxIt TolTh TolH hCritA hCritS DtMx htab1 htabN EPSI.Heat EPSI.Solute\n"
                "20 0.01 0.05 -1.0E+5 1.0E-3 0.02 0.001 1000 0.5 0.5\n",
                encoding="utf-8",
            )

            set_water_dtmax(water_path, 0.005)

            values = water_path.read_text(encoding="utf-8").splitlines()[2].split()
        self.assertEqual(values[5], "0.005")

    def test_validate_case_output_checks_drip_accounting(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_metrics_") as tmp_dir:
            root = Path(tmp_dir)
            (root / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
            (root / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1", "7"),
                encoding="utf-8",
            )
            (root / "LOAM2D.G05").write_text(
                _g05_metrics_text(),
                encoding="utf-8",
            )
            case = RegressionCase(
                name="metrics",
                soil=DEFAULT_SOILS[0],
                grid=DEFAULT_GRIDS[0],
                scenario=DEFAULT_SCENARIOS[0],
                run_dir=root,
            )

            metrics = validate_case_output(case)

        self.assertAlmostEqual(metrics.drip_sum_mm, 0.8)
        self.assertAlmostEqual(metrics.final_seas_drip_mm, 0.8)
        self.assertAlmostEqual(metrics.drip_demand_sum_mm, 1.0)
        self.assertAlmostEqual(metrics.drip_pressure_loss_sum_mm, 0.2)
        self.assertAlmostEqual(metrics.drip_hydraulic_excess_sum_mm, 0.1)
        self.assertAlmostEqual(metrics.drip_actual_infil_sum_mm, 0.7)
        self.assertAlmostEqual(metrics.drip_source_input_sum_mm, 0.6)
        self.assertAlmostEqual(metrics.drip_source_loss_sum_mm, 0.2)
        self.assertAlmostEqual(metrics.demand_input_pressure_residual_mm, 0.0)
        self.assertAlmostEqual(metrics.input_source_residual_mm, 0.0)
        self.assertAlmostEqual(metrics.input_acceptance_residual_mm, 0.0)
        self.assertAlmostEqual(metrics.drip_wet_nodes_max, 1.0)
        self.assertAlmostEqual(metrics.drip_wet_width_max_cm, 2.0)
        self.assertAlmostEqual(metrics.drip_pressure_factor_min, 0.8)
        self.assertGreater(metrics.expected_drip_mm, 0.0)

    def test_validate_case_output_requires_drip_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_missing_diag_") as tmp_dir:
            root = Path(tmp_dir)
            (root / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
            (root / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1", "7"),
                encoding="utf-8",
            )
            (root / "LOAM2D.G05").write_text(
                "Date,CumRain,infil,Runoff,Drainage,DripInput,SeasDrip\n"
                "05/01/2007,1.0,0.8,0.0,0.0,0.4,0.4\n",
                encoding="utf-8",
            )
            case = RegressionCase(
                name="missing_diag",
                soil=DEFAULT_SOILS[0],
                grid=DEFAULT_GRIDS[0],
                scenario=DEFAULT_SCENARIOS[0],
                run_dir=root,
            )

            with self.assertRaisesRegex(ValueError, "DripDemand"):
                validate_case_output(case)

    def test_validate_case_output_rejects_inconsistent_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_bad_diag_") as tmp_dir:
            root = Path(tmp_dir)
            (root / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
            (root / "LOAM2D.drp").write_text(
                _drip_text("05/01/2007 0.0 05/02/2007 0.0 0.1 1", "7"),
                encoding="utf-8",
            )
            (root / "LOAM2D.G05").write_text(
                _g05_metrics_text(wet_nodes_mean=2.0, wet_nodes_max=1.0),
                encoding="utf-8",
            )
            case = RegressionCase(
                name="bad_diag",
                soil=DEFAULT_SOILS[0],
                grid=DEFAULT_GRIDS[0],
                scenario=DEFAULT_SCENARIOS[0],
                run_dir=root,
            )

            with self.assertRaisesRegex(ValueError, "DripWetNodesMax"):
                validate_case_output(case)

    def test_validate_matrix_outputs_checks_drip_closure(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_matrix_closure_") as tmp_dir:
            cases = _write_synthetic_matrix(
                Path(tmp_dir),
                overrides={
                    "long_low_single": {
                        "drip_input": 9.0,
                        "seas_drip": 9.0,
                        "cumrain": 109.0,
                        "drip_demand": 12.0,
                        "drip_pressure_loss": 0.0,
                    },
                },
            )

            with self.assertRaisesRegex(AssertionError, "do not close"):
                validate_matrix_outputs(cases)

    def test_validate_matrix_outputs_checks_seas_drip_total(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_matrix_seas_") as tmp_dir:
            cases = _write_synthetic_matrix(
                Path(tmp_dir),
                overrides={
                    "long_low_single": {
                        "seas_drip": 9.0,
                    },
                },
            )

            with self.assertRaisesRegex(AssertionError, "final SeasDrip"):
                validate_matrix_outputs(cases)

    def test_validate_matrix_outputs_checks_pressure_reference(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_matrix_pressure_") as tmp_dir:
            cases = _write_synthetic_matrix(
                Path(tmp_dir),
                overrides={
                    "long_high_single": {
                        "drip_input": 11.5,
                        "seas_drip": 11.5,
                        "cumrain": 111.5,
                    },
                },
            )

            with self.assertRaisesRegex(AssertionError, "exceeds uncorrected"):
                validate_matrix_outputs(cases)


def _mini_grid():
    return "\n".join(
        [
            "***************** GRID GENERATOR INFORMATION **********************************************",
            "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
            "  2       3       0       3     2     1",
            "   n           x          y      MatNum",
            "    1     0       10       1",
            "    7     5       10       1",
            "    3     10      10       1",
            "****************Boundary geometry information**************************************",
            "    n  CodeW  CodeC  CodeH  CodeG  Width",
            "    1 -4    0     -4    -4      1.0",
            "    7 -4    0     -4    -4      2.0",
            "    3  4    0     -4    -4      1.0",
            "Seepage face information",
            "label",
            "0",
            "Drainage boundary information",
            "label",
            "0",
        ]
    ) + "\n"


def _write_minimal_base_run(base):
    base.mkdir()
    (base / "run.dat").write_text("", encoding="utf-8")
    (base / "Loam_200cm.soi").write_text("", encoding="utf-8")
    (base / "WaterMovDefault.dat").write_text(
        "title\n"
        "MaxIt TolTh TolH hCritA hCritS DtMx htab1 htabN EPSI.Heat EPSI.Solute\n"
        "20 0.01 0.05 -1.0E+5 1.0E-3 0.02 0.001 1000 0.5 0.5\n",
        encoding="utf-8",
    )
    (base / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
    (base / "LOAM2D.drp").write_text("", encoding="utf-8")


def _drip_text(event_line, nodes_line):
    return "\n".join(
        [
            "*****Script for Drip application module",
            "Number of Drip irrigations(max=75)",
            "1",
            "StartDate StartHour StopDate StopHour RateCmHr NumNodes",
            event_line,
            "Drip nodes",
            nodes_line,
        ]
    ) + "\n"


def _g05_metrics_text(wet_nodes_mean=1.0, wet_nodes_max=1.0):
    header = (
        "Date,CumRain,infil,Runoff,Drainage,DripInput,SeasDrip,"
        "DripDemand,DripPressureLoss,DripHydraulicExcess,"
        "DripActualInfil,DripSourceInput,DripSourceLoss,"
        "DripWetNodesMean,DripWetNodesMax,DripWetWidthMean,"
        "DripWetWidthMax,DripPressureFactorMean,DripPressureFactorMin"
    )
    rows = [
        (
            "05/01/2007,1.0,0.8,0.0,0.0,0.4,0.4,0.5,0.1,0.05,"
            "0.35,0.3,0.1,"
            f"{wet_nodes_mean},{wet_nodes_max},2.0,2.0,0.8,0.8"
        ),
        (
            "05/02/2007,1.0,0.7,0.0,0.0,0.4,0.8,0.5,0.1,0.05,"
            "0.35,0.3,0.1,"
            f"{wet_nodes_mean},{wet_nodes_max},2.0,2.0,0.8,0.8"
        ),
    ]
    return "\n".join([header, *rows]) + "\n"


def _write_synthetic_matrix(root, overrides=None):
    overrides = overrides or {}
    cases = []
    baseline_dir = root / "synthetic__baseline"
    _write_synthetic_case_outputs(baseline_dir, _baseline_values())
    cases.append(
        RegressionCase(
            name="synthetic__baseline",
            soil=DEFAULT_SOILS[0],
            grid=DEFAULT_GRIDS[0],
            scenario=None,
            run_dir=baseline_dir,
        )
    )
    for scenario in DEFAULT_SCENARIOS:
        case_dir = root / f"synthetic__{scenario.name}"
        values = _drip_values()
        values.update(overrides.get(scenario.name, {}))
        _write_synthetic_case_outputs(case_dir, values)
        case_scenario = DripScenario(
            name=scenario.name,
            event_line="'05/01/2007' 0.0 '05/02/2007' 0.0 0.1 1",
            node_line=" 7",
        )
        cases.append(
            RegressionCase(
                name=f"synthetic__{scenario.name}",
                soil=DEFAULT_SOILS[0],
                grid=DEFAULT_GRIDS[0],
                scenario=case_scenario,
                run_dir=case_dir,
            )
        )
    return cases


def _write_synthetic_case_outputs(case_dir, values):
    case_dir.mkdir()
    (case_dir / "LOAM2D.grd").write_text(_mini_grid(), encoding="utf-8")
    (case_dir / "LOAM2D.drp").write_text(
        _drip_text("'05/01/2007' 0.0 '05/02/2007' 0.0 0.1 1", "7"),
        encoding="utf-8",
    )
    (case_dir / "LOAM2D.G05").write_text(_single_row_g05(values), encoding="utf-8")


def _baseline_values():
    return {
        "cumrain": 100.0,
        "infil": 50.0,
        "runoff": 0.0,
        "drainage": 0.0,
        "drip_input": 0.0,
        "seas_drip": 0.0,
        "drip_demand": 0.0,
        "drip_pressure_loss": 0.0,
        "drip_hydraulic_excess": 0.0,
        "drip_actual_infil": 0.0,
        "drip_source_input": 0.0,
        "drip_source_loss": 0.0,
        "wet_nodes_mean": 0.0,
        "wet_nodes_max": 0.0,
        "wet_width_mean": 0.0,
        "wet_width_max": 0.0,
        "pressure_factor_mean": 0.0,
        "pressure_factor_min": 0.0,
    }


def _drip_values():
    values = _baseline_values()
    values.update(
        {
            "cumrain": 112.0,
            "infil": 55.0,
            "drip_input": 12.0,
            "seas_drip": 12.0,
            "drip_demand": 12.0,
            "drip_actual_infil": 12.0,
            "drip_source_input": 12.0,
            "wet_nodes_mean": 1.0,
            "wet_nodes_max": 1.0,
            "wet_width_mean": 2.0,
            "wet_width_max": 2.0,
            "pressure_factor_mean": 1.0,
            "pressure_factor_min": 1.0,
        }
    )
    return values


def _single_row_g05(values):
    header = (
        "Date,CumRain,infil,Runoff,Drainage,DripInput,SeasDrip,"
        "DripDemand,DripPressureLoss,DripHydraulicExcess,"
        "DripActualInfil,DripSourceInput,DripSourceLoss,"
        "DripWetNodesMean,DripWetNodesMax,DripWetWidthMean,"
        "DripWetWidthMax,DripPressureFactorMean,DripPressureFactorMin"
    )
    row = (
        "05/01/2007,"
        f"{values['cumrain']},{values['infil']},{values['runoff']},"
        f"{values['drainage']},{values['drip_input']},"
        f"{values['seas_drip']},{values['drip_demand']},"
        f"{values['drip_pressure_loss']},{values['drip_hydraulic_excess']},"
        f"{values['drip_actual_infil']},{values['drip_source_input']},"
        f"{values['drip_source_loss']},"
        f"{values['wet_nodes_mean']},{values['wet_nodes_max']},"
        f"{values['wet_width_mean']},{values['wet_width_max']},"
        f"{values['pressure_factor_mean']},{values['pressure_factor_min']}"
    )
    return "\n".join([header, row]) + "\n"


if __name__ == "__main__":
    unittest.main()
