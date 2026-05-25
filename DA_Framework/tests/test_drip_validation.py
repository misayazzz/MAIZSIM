import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.drip_validation import (
    build_public_comparison_report_skeleton,
    g05_delta_by_date,
    parse_drip_file,
    read_g05_surface_water,
)


class DripValidationTests(unittest.TestCase):
    def test_parse_single_node_event_and_expected_water_amount(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_single_") as tmp_dir:
            drip_path = Path(tmp_dir) / "single.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 6.0 05/20/2007 8.0 2.0 1",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        self.assertEqual(schedule.event_count, 1)
        self.assertEqual(schedule.events[0].nodes, (7,))
        self.assertEqual(schedule.events[0].duration_hours, 2.0)
        self.assertEqual(schedule.events[0].applied_depth_cm, 4.0)
        self.assertEqual(schedule.total_event_node_depth_cm, 4.0)
        self.assertAlmostEqual(
            schedule.expected_grid_depth_mm({7: 15.0}, grid_width_cm=120.0),
            5.0,
        )

    def test_parse_optional_pressure_fields(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_pressure_") as tmp_dir:
            drip_path = Path(tmp_dir) / "pressure.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 6.0 05/20/2007 8.0 2.0 1 2 100 0.5 50 150 20",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        event = schedule.events[0]
        self.assertEqual(event.pressure_mode, 2)
        self.assertEqual(event.pressure_head_cm, 100.0)
        self.assertEqual(event.pressure_exponent, 0.5)
        self.assertEqual(event.pressure_pc_min_cm, 50.0)
        self.assertEqual(event.pressure_pc_max_cm, 150.0)
        self.assertEqual(event.wet_width_max_cm, 20.0)
        self.assertEqual(event.spread_mode, 0)

    def test_parse_precision_spread_mode(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_spread_") as tmp_dir:
            drip_path = Path(tmp_dir) / "spread.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 6.0 05/20/2007 8.0 2.0 1 0 0 1 0 0 16.3 1",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        event = schedule.events[0]
        self.assertEqual(event.pressure_mode, 0)
        self.assertAlmostEqual(event.wet_width_max_cm, 16.3)
        self.assertEqual(event.spread_mode, 1)

    def test_parse_optional_wet_width_without_pressure_fields(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_wet_width_") as tmp_dir:
            drip_path = Path(tmp_dir) / "wet_width.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 6.0 05/20/2007 8.0 2.0 1 0 0 1 0 0 18",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        event = schedule.events[0]
        self.assertEqual(event.pressure_mode, 0)
        self.assertEqual(event.wet_width_max_cm, 18.0)

    def test_parse_multi_node_multi_event_cross_day_schedule(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_multi_") as tmp_dir:
            drip_path = Path(tmp_dir) / "multi.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 23.5 05/21/2007 1.0 1.5 2",
                        "7 8",
                        "05/22/2007 5.0 05/22/2007 6.0 0.5 1",
                        "9",
                    ],
                    event_count=2,
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        self.assertEqual(schedule.event_count, 2)
        self.assertEqual(schedule.events[0].duration_hours, 1.5)
        self.assertEqual(schedule.events[1].duration_hours, 1.0)
        self.assertAlmostEqual(schedule.total_event_node_depth_cm, 5.0)
        self.assertAlmostEqual(
            schedule.expected_grid_depth_mm(
                {7: 10.0, 8: 20.0, 9: 10.0},
                grid_width_cm=100.0,
            ),
            7.25,
        )

    def test_parse_long_period_schedule_keeps_water_amount_finite(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_long_") as tmp_dir:
            drip_path = Path(tmp_dir) / "long.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/01/2007 0.0 05/31/2007 0.0 0.1 1",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )

            schedule = parse_drip_file(drip_path)

        self.assertEqual(schedule.events[0].duration_hours, 720.0)
        self.assertAlmostEqual(schedule.total_event_node_depth_cm, 72.0)
        self.assertTrue(
            np.isfinite(
                schedule.expected_grid_depth_mm(
                    {7: 15.0},
                    grid_width_cm=150.0,
                )
            )
        )

    def test_parse_drip_file_rejects_invalid_inputs(self):
        cases = {
            "negative_count": "\n".join(["header", "count", "-1"]) + "\n",
            "stop_before_start": _drip_text(
                [
                    "05/20/2007 8.0 05/20/2007 6.0 2.0 1",
                    "7",
                ]
            ),
            "negative_rate": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 -2.0 1",
                    "7",
                ]
            ),
            "invalid_pressure_mode": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 1 3 100 1 0 0",
                    "7",
                ]
            ),
            "negative_wet_width": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 1 0 0 1 0 0 -1",
                    "7",
                ]
            ),
            "invalid_spread_mode": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 1 0 0 1 0 0 10 2",
                    "7",
                ]
            ),
            "missing_pressure_head": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 1 1 0 1 0 0",
                    "7",
                ]
            ),
            "node_count_mismatch": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 2",
                    "7",
                ]
            ),
            "invalid_node": _drip_text(
                [
                    "05/20/2007 6.0 05/20/2007 8.0 2.0 1",
                    "0",
                ]
            ),
        }

        with tempfile.TemporaryDirectory(prefix="codex_drip_invalid_") as tmp_dir:
            for name, text in cases.items():
                with self.subTest(name=name):
                    drip_path = Path(tmp_dir) / f"{name}.drp"
                    drip_path.write_text(text, encoding="utf-8")

                    with self.assertRaises(ValueError):
                        parse_drip_file(drip_path)

    def test_read_g05_surface_water_accepts_old_column_order(self):
        with tempfile.TemporaryDirectory(prefix="codex_g05_old_") as tmp_dir:
            g05_path = Path(tmp_dir) / "old_order.G05"
            g05_path.write_text(
                "\n".join(
                    [
                        " Date , Date_time , infil , CumRain , Drainage , Runoff ",
                        "05/20/2007,120.0,0.5,0.6,0.1,0.0",
                        "05/21/2007,121.0,5.4,5.5,0.2,0.1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            frame = read_g05_surface_water(g05_path)

        self.assertEqual(
            [date.strftime("%Y-%m-%d") for date in frame["date"]],
            ["2007-05-20", "2007-05-21"],
        )
        np.testing.assert_allclose(frame["cumrain_mm"].to_numpy(), [0.6, 5.5])
        np.testing.assert_allclose(frame["infil_mm"].to_numpy(), [0.5, 5.4])

    def test_read_g05_surface_water_accepts_drip_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="codex_g05_diag_") as tmp_dir:
            g05_path = Path(tmp_dir) / "diagnostics.G05"
            g05_path.write_text(
                "\n".join(
                    [
                        (
                            "Date,Date_time,DripWetWidthMax,"
                            "DripPressureFactorMin,CumRain,infil,"
                            "DripDemand,DripPressureLoss,"
                            "DripHydraulicExcess,DripSourceInput,"
                            "DripSourceLoss,DripWetNodesMean,"
                            "DripWetNodesMax,DripWetWidthMean,"
                            "DripPressureFactorMean"
                        ),
                        "05/21/2007,121.0,45.0,0.75,5.5,5.4,5.0,0.2,0.1,4.8,0.2,2.0,3.0,30.0,0.88",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            frame = read_g05_surface_water(g05_path)

        self.assertAlmostEqual(frame["drip_demand_mm"].iloc[0], 5.0)
        self.assertAlmostEqual(frame["drip_pressure_loss_mm"].iloc[0], 0.2)
        self.assertAlmostEqual(frame["drip_hydraulic_excess_mm"].iloc[0], 0.1)
        self.assertAlmostEqual(frame["drip_source_input_mm"].iloc[0], 4.8)
        self.assertAlmostEqual(frame["drip_source_loss_mm"].iloc[0], 0.2)
        self.assertAlmostEqual(frame["drip_wet_nodes_mean"].iloc[0], 2.0)
        self.assertAlmostEqual(frame["drip_wet_nodes_max"].iloc[0], 3.0)
        self.assertAlmostEqual(frame["drip_wet_width_mean_cm"].iloc[0], 30.0)
        self.assertAlmostEqual(frame["drip_wet_width_max_cm"].iloc[0], 45.0)
        self.assertAlmostEqual(frame["drip_pressure_factor_mean"].iloc[0], 0.88)
        self.assertAlmostEqual(frame["drip_pressure_factor_min"].iloc[0], 0.75)

    def test_g05_delta_by_date_returns_drip_minus_baseline(self):
        with tempfile.TemporaryDirectory(prefix="codex_g05_delta_") as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline.G05"
            drip = root / "drip.G05"
            baseline.write_text(
                _g05_text(
                    cumrain=0.60,
                    infil=0.48,
                    runoff=0.01,
                    drip_demand=0.0,
                    drip_hydraulic_excess=0.0,
                    drip_pressure_factor_mean=0.0,
                ),
                encoding="utf-8",
            )
            drip.write_text(
                _g05_text(
                    cumrain=5.49,
                    infil=5.37,
                    runoff=0.02,
                    drip_demand=4.89,
                    drip_hydraulic_excess=0.1,
                    drip_pressure_factor_mean=1.0,
                ),
                encoding="utf-8",
            )

            delta = g05_delta_by_date(baseline, drip, "2007-05-21")

        self.assertAlmostEqual(delta["cumrain_mm"], 4.89)
        self.assertAlmostEqual(delta["infil_mm"], 4.89)
        self.assertAlmostEqual(delta["runoff_mm"], 0.01)
        self.assertAlmostEqual(delta["drip_demand_mm"], 4.89)
        self.assertAlmostEqual(delta["drip_hydraulic_excess_mm"], 0.1)
        self.assertAlmostEqual(delta["drip_pressure_factor_mean"], 1.0)

    def test_public_comparison_report_skeleton_lists_literature_indicators(self):
        with tempfile.TemporaryDirectory(prefix="codex_drip_report_") as tmp_dir:
            drip_path = Path(tmp_dir) / "single.drp"
            drip_path.write_text(
                _drip_text(
                    [
                        "05/20/2007 6.0 05/20/2007 8.0 2.0 1",
                        "7",
                    ]
                ),
                encoding="utf-8",
            )
            schedule = parse_drip_file(drip_path)

        report = build_public_comparison_report_skeleton(
            schedule,
            expected_grid_depth_mm=4.89,
            simulated_delta={"cumrain_mm": 4.89, "infil_mm": 4.89},
        )

        self.assertIn("surface point-source Neumann flux", report)
        self.assertIn("bounded dynamic wetted-radius expansion", report)
        self.assertIn("Pressure correction", report)
        self.assertIn("G05 DripInput", report)
        self.assertIn("Skaggs et al. 2004", report)
        self.assertIn("4.89 mm", report)


def _drip_text(event_lines, event_count=1):
    lines = [
        "*****Script for Drip application module",
        "Number of Drip irrigations(max=75)",
        str(event_count),
        "StartDate StartHour StopDate StopHour RateCmHr NumNodes",
    ]
    for index in range(0, len(event_lines), 2):
        lines.append(event_lines[index])
        lines.append("Drip nodes")
        lines.append(event_lines[index + 1])
    return "\n".join(lines) + "\n"


def _g05_text(
    cumrain,
    infil,
    runoff,
    drip_demand=4.89,
    drip_hydraulic_excess=0.1,
    drip_pressure_factor_mean=1.0,
):
    return (
        "Date_time,Date,PSoilEvap,ASoilEVap,CumRain,infil,Drainage,Runoff,"
        "DripDemand,DripHydraulicExcess,DripPressureFactorMean\n"
        f"120.0,05/21/2007,0,0,{cumrain},{infil},0.2,{runoff},"
        f"{drip_demand},{drip_hydraulic_excess},{drip_pressure_factor_mean}\n"
    )


if __name__ == "__main__":
    unittest.main()
