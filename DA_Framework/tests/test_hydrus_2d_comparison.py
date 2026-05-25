import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.hydrus_2d_comparison import (
    compare_theta_fields,
    main,
    read_hydrus_theta_csv,
    read_maizsim_g03_theta,
)


class Hydrus2DComparisonTests(unittest.TestCase):
    def test_read_hydrus_theta_csv_accepts_common_column_names(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_csv_") as tmp_dir:
            path = Path(tmp_dir) / "hydrus.csv"
            path.write_text(
                "\n".join(
                    [
                        "X,Depth,theta_hydrus,area_cm2",
                        "0,0,0.20,2",
                        "10,0,0.21,2",
                        "0,10,0.24,3",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            frame = read_hydrus_theta_csv(path)

        self.assertEqual(list(frame.columns), ["x_cm", "depth_cm", "theta", "area_cm2"])
        np.testing.assert_allclose(frame["theta"].to_numpy(), [0.20, 0.21, 0.24])
        np.testing.assert_allclose(frame["area_cm2"].to_numpy(), [2.0, 2.0, 3.0])

    def test_read_maizsim_g03_theta_selects_nearest_date_and_converts_depth(self):
        with tempfile.TemporaryDirectory(prefix="codex_maizsim_g03_") as tmp_dir:
            path = Path(tmp_dir) / "LOAM2D.G03"
            path.write_text(
                "\n".join(
                    [
                        "Date,X,Y,thNew,Area",
                        "2024-06-01,0,100,0.10,1",
                        "2024-06-01,10,90,0.20,1",
                        "2024-06-03,0,100,0.30,1",
                        "2024-06-03,10,90,0.40,1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            frame = read_maizsim_g03_theta(path, "2024-06-02")

        np.testing.assert_allclose(frame["theta"].to_numpy(), [0.10, 0.20])
        np.testing.assert_allclose(frame["depth_cm"].to_numpy(), [0.0, 10.0])

    def test_compare_theta_fields_reports_field_and_wet_shape_metrics(self):
        hydrus = _field(
            theta=[0.20, 0.20, 0.30, 0.20],
            area=[2.0, 2.0, 2.0, 2.0],
        )
        maizsim = _field(theta=[0.20, 0.20, 0.28, 0.22])
        baseline = _field(theta=[0.20, 0.20, 0.20, 0.20])

        comparison = compare_theta_fields(
            maizsim,
            hydrus,
            maizsim_baseline=baseline,
            hydrus_baseline=baseline,
            wet_delta_threshold=0.05,
        )

        self.assertEqual(comparison.metrics["point_count"], 4.0)
        self.assertAlmostEqual(comparison.metrics["theta_mae"], 0.01)
        self.assertAlmostEqual(
            comparison.metrics["theta_rmse"],
            float(np.sqrt((0.02**2 + 0.02**2) / 4.0)),
        )
        self.assertAlmostEqual(comparison.metrics["wet_iou"], 1.0)
        self.assertAlmostEqual(comparison.metrics["hydrus_wet_area_cm2"], 2.0)
        self.assertAlmostEqual(comparison.metrics["maizsim_wet_area_cm2"], 2.0)
        self.assertAlmostEqual(comparison.metrics["peak_delta_distance_cm"], 0.0)

    def test_cli_writes_summary_points_and_figure(self):
        with tempfile.TemporaryDirectory(prefix="codex_hydrus_cli_") as tmp_dir:
            root = Path(tmp_dir)
            hydrus_path = root / "hydrus.csv"
            hydrus_base_path = root / "hydrus_base.csv"
            maizsim_path = root / "LOAM2D.G03"
            maizsim_base_path = root / "baseline.G03"
            output_dir = root / "out"
            _write_hydrus_csv(hydrus_path, [0.20, 0.20, 0.30, 0.20])
            _write_hydrus_csv(hydrus_base_path, [0.20, 0.20, 0.20, 0.20])
            _write_g03(maizsim_path, [0.20, 0.20, 0.28, 0.22])
            _write_g03(maizsim_base_path, [0.20, 0.20, 0.20, 0.20])

            exit_code = main(
                [
                    "--maizsim-g03",
                    str(maizsim_path),
                    "--hydrus-csv",
                    str(hydrus_path),
                    "--date",
                    "2024-06-01",
                    "--maizsim-baseline-g03",
                    str(maizsim_base_path),
                    "--hydrus-baseline-csv",
                    str(hydrus_base_path),
                    "--output-dir",
                    str(output_dir),
                    "--wet-delta-threshold",
                    "0.05",
                ]
            )

            summary = pd.read_csv(output_dir / "hydrus_2d_comparison_summary.csv")
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "hydrus_2d_comparison_points.csv").exists())
            self.assertTrue((output_dir / "hydrus_2d_comparison_fields.png").exists())
            self.assertAlmostEqual(float(summary.loc[0, "wet_iou"]), 1.0)


def _field(theta, area=None):
    if area is None:
        area = [1.0, 1.0, 1.0, 1.0]
    return pd.DataFrame(
        {
            "x_cm": [0.0, 10.0, 0.0, 10.0],
            "depth_cm": [0.0, 0.0, 10.0, 10.0],
            "theta": theta,
            "area_cm2": area,
        }
    )


def _write_hydrus_csv(path, theta):
    frame = _field(theta)
    frame.to_csv(path, index=False)


def _write_g03(path, theta):
    rows = [
        ("2024-06-01", 0.0, 100.0, theta[0], 1.0),
        ("2024-06-01", 10.0, 100.0, theta[1], 1.0),
        ("2024-06-01", 0.0, 90.0, theta[2], 1.0),
        ("2024-06-01", 10.0, 90.0, theta[3], 1.0),
    ]
    pd.DataFrame(rows, columns=["Date", "X", "Y", "thNew", "Area"]).to_csv(
        path,
        index=False,
    )


if __name__ == "__main__":
    unittest.main()
