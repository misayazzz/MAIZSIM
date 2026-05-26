import tempfile
import unittest
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.hydrus_goal3_acceptance import (
    Goal3Thresholds,
    evaluate_summary,
    main,
)


class HydrusGoal3AcceptanceTests(unittest.TestCase):
    def test_evaluate_summary_passes_complete_goal3_case(self):
        with tempfile.TemporaryDirectory(prefix="codex_goal3_accept_") as tmp_dir:
            root = Path(tmp_dir)
            summary = root / "case_aligned_validation_summary.csv"
            figure = root / "case_aligned_fields.png"
            _write_summary(summary)
            _write_figure(figure, red_marker=True)

            checks = evaluate_summary(summary)

        self.assertFalse(checks.empty)
        self.assertEqual(set(checks["status"]), {"pass"})
        self.assertIn("aligned_fields_png_drip_marker", set(checks["check"]))

    def test_evaluate_summary_fails_current_like_storage_and_peak_errors(self):
        with tempfile.TemporaryDirectory(prefix="codex_goal3_accept_") as tmp_dir:
            root = Path(tmp_dir)
            summary = root / "case_aligned_validation_summary.csv"
            figure = root / "case_aligned_fields.png"
            _write_summary(
                summary,
                {
                    "delta_storage_residual_l": 1.379,
                    "peak_delta_distance_cm": 17.575,
                    "delta_theta_volume_rmse": 0.0095,
                },
            )
            _write_figure(figure, red_marker=True)

            checks = evaluate_summary(summary)

        failed = set(checks.loc[checks["status"] == "fail", "check"])
        self.assertIn("delta_storage_abs_residual_l", failed)
        self.assertIn("peak_delta_distance_cm", failed)
        self.assertIn("delta_theta_volume_rmse", failed)

    def test_evaluate_summary_fails_missing_red_drip_marker(self):
        with tempfile.TemporaryDirectory(prefix="codex_goal3_accept_") as tmp_dir:
            root = Path(tmp_dir)
            summary = root / "case_aligned_validation_summary.csv"
            figure = root / "case_aligned_fields.png"
            _write_summary(summary)
            _write_figure(figure, red_marker=False)

            checks = evaluate_summary(summary)

        marker = checks.loc[checks["check"] == "aligned_fields_png_drip_marker"].iloc[0]
        self.assertEqual(marker["status"], "fail")

    def test_main_returns_nonzero_when_any_check_fails(self):
        with tempfile.TemporaryDirectory(prefix="codex_goal3_accept_") as tmp_dir:
            root = Path(tmp_dir)
            summary = root / "case_aligned_validation_summary.csv"
            figure = root / "case_aligned_fields.png"
            output = root / "checks.csv"
            _write_summary(summary, {"wet_iou": 0.5})
            _write_figure(figure, red_marker=True)

            exit_code = main(
                [
                    "--summary",
                    str(summary),
                    "--figure",
                    str(figure),
                    "--output-csv",
                    str(output),
                ]
            )

        self.assertEqual(exit_code, 1)

    def test_custom_thresholds_can_relax_peak_distance(self):
        with tempfile.TemporaryDirectory(prefix="codex_goal3_accept_") as tmp_dir:
            root = Path(tmp_dir)
            summary = root / "case_aligned_validation_summary.csv"
            figure = root / "case_aligned_fields.png"
            _write_summary(summary, {"peak_delta_distance_cm": 1.5})
            _write_figure(figure, red_marker=True)

            checks = evaluate_summary(
                summary,
                thresholds=Goal3Thresholds(max_peak_delta_distance_cm=2.0),
            )

        peak = checks.loc[checks["check"] == "peak_delta_distance_cm"].iloc[0]
        self.assertEqual(peak["status"], "pass")


def _write_summary(path, overrides=None):
    values = {
        "hydrus_project": "SyntheticGoal3",
        "wet_iou": 0.96,
        "source_wet_iou": 0.95,
        "hydrus_wet_width_cm": 28.0,
        "maizsim_wet_width_cm": 28.4,
        "hydrus_wet_depth_cm": 18.0,
        "maizsim_wet_depth_cm": 19.0,
        "delta_storage_residual_l": 0.2,
        "peak_delta_distance_cm": 0.8,
        "delta_theta_volume_rmse": 0.004,
        "g05_boundary_input_closure_residual_mm": 0.0,
        "g05_boundary_acceptance_residual_mm": 0.0,
    }
    if overrides:
        values.update(overrides)
    pd.DataFrame([values]).to_csv(path, index=False)


def _write_figure(path, red_marker):
    image = np.full((24, 24, 3), 0.65, dtype=float)
    image[6:18, 6:18, :] = 0.35
    if red_marker:
        image[2:8, 2:8, 0] = 1.0
        image[2:8, 2:8, 1] = 0.0
        image[2:8, 2:8, 2] = 0.0
    plt.imsave(path, image)


if __name__ == "__main__":
    unittest.main()
