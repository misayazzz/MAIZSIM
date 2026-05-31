import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.drip_point_source_validation import (
    BASE_RUN,
    ENHANCED_SCENARIOS,
    DEFAULT_EMITTER_SPACING_M,
    DripScenario,
    _active_application_width_mean,
    _delta_shape_metrics,
    _excel_serial,
    _emitter_flow_l_h,
    _equivalent_local_flux_cm_h,
    _frame_at_elapsed,
    _g03_storage_delta_mm,
    _g05_through_elapsed,
    _grid_case_info,
    _grid_input_mm,
    _line_source_flux_l_h_m,
    _rate_for_grid_input,
    _rate_for_emitter_flow,
    _refine_grid_fixed_domain,
    _safe_fraction,
    DRIP_START,
)


class DripPointSourceValidationTests(unittest.TestCase):
    def test_frame_at_elapsed_uses_strict_selected_time_match(self):
        target = _excel_serial(DRIP_START.date()) + 1.0
        frame = pd.DataFrame(
            {
                "date_time": [target, target, target + 0.2],
                "x": [0.0, 1.0, 99.0],
                "y": [0.0, 0.0, 0.0],
                "theta": [0.20, 0.21, 0.99],
            }
        )

        selected = _frame_at_elapsed(frame, 24)

        self.assertEqual(list(selected["x"]), [0.0, 1.0])

    def test_scenario_uses_stop_and_final_dates_from_elapsed_hours(self):
        scenario = DripScenario(
            "redistribution",
            drip_duration_h=24.0,
            final_elapsed_h=72.0,
        )

        self.assertEqual(scenario.drip_stop.date().isoformat(), "2007-05-21")
        self.assertEqual(scenario.final_date.isoformat(), "2007-05-23")
        self.assertAlmostEqual(scenario.local_applied_depth_cm, 12.0)

    def test_rate_for_grid_input_converts_target_mm_to_local_flux(self):
        rate = _rate_for_grid_input(1.2, source_width_cm=0.38, duration_h=24.0)

        self.assertAlmostEqual(rate, 0.5013157894736842)
        self.assertAlmostEqual(_grid_input_mm(rate, 0.38, 24.0), 1.2)

    def test_line_source_and_emitter_flow_conversions_use_symmetry_factor(self):
        half_line_flux = _line_source_flux_l_h_m(0.5, 0.38, mirrored=False)
        mirrored_line_flux = _line_source_flux_l_h_m(0.5, 0.38, mirrored=True)
        emitter_flow = _emitter_flow_l_h(
            0.5,
            0.38,
            DEFAULT_EMITTER_SPACING_M,
            mirrored=True,
        )

        self.assertAlmostEqual(half_line_flux, 0.019)
        self.assertAlmostEqual(mirrored_line_flux, 0.038)
        self.assertAlmostEqual(emitter_flow, 0.0114)
        self.assertAlmostEqual(
            _rate_for_emitter_flow(2.0, 0.3, 0.38, mirrored=True),
            87.71929824561404,
        )

    def test_equivalent_local_flux_inverts_grid_depth(self):
        local_flux = _equivalent_local_flux_cm_h(
            1.2,
            source_width_cm=0.38,
            duration_h=24.0,
            grid_width_cm=38.1,
        )

        self.assertAlmostEqual(local_flux, 0.5013157894736842)

    def test_active_application_width_mean_ignores_zero_input_rows(self):
        g05 = pd.DataFrame(
            {
                "drip_input_mm": [0.0, 0.1, 0.2, 0.0],
                "drip_surface_application_width_mean_cm": [0.0, 5.0, 7.0, 0.0],
            }
        )

        self.assertAlmostEqual(_active_application_width_mean(g05), 6.0)

    def test_enhanced_scenarios_cover_high_total_width_and_redistribution(self):
        names = {scenario.name for scenario in ENHANCED_SCENARIOS}

        self.assertIn("total10mm_width10cm_24h", names)
        self.assertIn("total40mm_width0p38cm_24h", names)
        self.assertIn("redistribution_total10mm_width5cm_72h", names)
        self.assertEqual(len(ENHANCED_SCENARIOS), 13)
        redistribution = [
            scenario
            for scenario in ENHANCED_SCENARIOS
            if scenario.scenario_group == "redistribution"
        ]
        self.assertTrue(all(scenario.final_elapsed_h == 72.0 for scenario in redistribution))
        self.assertTrue(
            all(scenario.figure_elapsed_hours == (24.0, 48.0, 72.0) for scenario in redistribution)
        )

    def test_g03_storage_delta_integrates_area_weighted_theta_difference(self):
        date_time = _excel_serial(DRIP_START.date()) + 1.0
        baseline = pd.DataFrame(
            {
                "date_time": [date_time, date_time],
                "x": [0.0, 1.0],
                "y": [10.0, 10.0],
                "theta": [0.20, 0.30],
                "area": [10.0, 20.0],
            }
        )
        drip = baseline.copy()
        drip["theta"] = [0.30, 0.40]

        storage_delta = _g03_storage_delta_mm(baseline, drip, grid_width_cm=30.0)

        self.assertAlmostEqual(storage_delta, 1.0)

    def test_g05_through_elapsed_uses_selected_elapsed_window(self):
        start = _excel_serial(DRIP_START.date())
        g05 = pd.DataFrame(
            {
                "date_time": [start + 0.25, start + 1.0, start + 2.0],
                "drip_input_mm": [0.1, 0.2, 0.3],
            }
        )

        selected = _g05_through_elapsed(g05, 24.0)

        self.assertEqual(list(selected["drip_input_mm"]), [0.1, 0.2])

    def test_safe_fraction_handles_zero_denominator(self):
        self.assertEqual(_safe_fraction(1.0, 0.0), 0.0)
        self.assertAlmostEqual(_safe_fraction(1.0, 4.0), 0.25)

    def test_delta_shape_metrics_reports_interpolated_depth_and_boundary_touch(self):
        date_time = _excel_serial(DRIP_START.date()) + 1.0
        baseline = pd.DataFrame(
            {
                "date_time": [date_time] * 4,
                "x": [0.0, 10.0, 0.0, 10.0],
                "y": [10.0, 10.0, 0.0, 0.0],
                "depth_cm": [0.0, 0.0, 10.0, 10.0],
                "theta": [0.20, 0.20, 0.20, 0.20],
                "area": [1.0, 1.0, 1.0, 1.0],
            }
        )
        drip = baseline.copy()
        drip["theta"] = [0.30, 0.30, 0.20, 0.20]

        metrics = _delta_shape_metrics(
            baseline,
            drip,
            elapsed_h=24.0,
            threshold=0.05,
            mirror=True,
            grid_width_cm=10.0,
        )

        self.assertAlmostEqual(metrics["wet_depth_cm"], 0.0)
        self.assertAlmostEqual(metrics["wet_depth_interpolated_cm"], 5.0)
        self.assertAlmostEqual(metrics["wet_width_interpolated_cm"], 20.0)
        self.assertTrue(metrics["touches_lateral_boundary"])

    def test_delta_shape_metrics_separates_node_and_interpolated_width(self):
        date_time = _excel_serial(DRIP_START.date()) + 1.0
        baseline = pd.DataFrame(
            {
                "date_time": [date_time] * 4,
                "x": [0.0, 10.0, 0.0, 10.0],
                "y": [10.0, 10.0, 0.0, 0.0],
                "depth_cm": [0.0, 0.0, 10.0, 10.0],
                "theta": [0.20, 0.20, 0.20, 0.20],
                "area": [1.0, 1.0, 1.0, 1.0],
            }
        )
        drip = baseline.copy()
        drip["theta"] = [0.30, 0.20, 0.20, 0.20]

        metrics = _delta_shape_metrics(
            baseline,
            drip,
            elapsed_h=24.0,
            threshold=0.05,
            mirror=True,
            grid_width_cm=10.0,
        )

        self.assertAlmostEqual(metrics["wet_width_cm"], 0.0)
        self.assertAlmostEqual(metrics["wet_width_interpolated_cm"], 10.0)
        self.assertFalse(metrics["touches_lateral_boundary"])

    def test_refine_grid_fixed_domain_updates_grid_and_nod_counts(self):
        with tempfile.TemporaryDirectory(prefix="codex_grid_refine_") as tmp_dir:
            root = Path(tmp_dir)
            grid_path = root / "LOAM2D.grd"
            nod_path = root / "LOAM2D.nod"
            shutil.copy2(BASE_RUN / "LOAM2D.grd", grid_path)
            shutil.copy2(BASE_RUN / "LOAM2D.nod", nod_path)

            _refine_grid_fixed_domain(grid_path, 2)
            info = _grid_case_info(grid_path)
            nod_records = [line for line in nod_path.read_text(encoding="utf-8").splitlines()[2:] if line.strip()]

        self.assertEqual(info["grid_x_node_count"], 19)
        self.assertEqual(info["grid_y_node_count"], 34)
        self.assertEqual(info["grid_node_count"], 646)
        self.assertEqual(len(nod_records), 646)
        self.assertAlmostEqual(info["grid_width_cm"], 38.1)
        self.assertAlmostEqual(info["first_surface_width_cm"], 0.1875)


if __name__ == "__main__":
    unittest.main()
