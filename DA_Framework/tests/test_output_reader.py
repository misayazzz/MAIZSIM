import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.output_reader import (
    build_simulation_vector,
    read_g01_daily_lai,
    read_g03_daily_theta,
)


class OutputReaderTests(unittest.TestCase):
    def test_read_g01_daily_lai_returns_daily_mean(self):
        with tempfile.TemporaryDirectory(prefix="codex_g01_") as tmp_dir:
            g01_path = Path(tmp_dir) / "synthetic.g01"
            g01_path.write_text(
                "\n".join(
                    [
                        "Date,LAI",
                        "2024-06-01 00:00,1.0",
                        "2024-06-01 12:00,3.0",
                        "2024-06-02 00:00,4.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            daily = read_g01_daily_lai(g01_path)

        self.assertEqual(
            [date.strftime("%Y-%m-%d") for date in daily.index],
            ["2024-06-01", "2024-06-02"],
        )
        np.testing.assert_allclose(daily.to_numpy(), [2.0, 4.0])

    def test_read_g03_daily_theta_uses_area_weighted_depth_average(self):
        with tempfile.TemporaryDirectory(prefix="codex_g03_") as tmp_dir:
            g03_path = Path(tmp_dir) / "synthetic.G03"
            g03_path.write_text(
                "\n".join(
                    [
                        "Date,Y,thNew,Area",
                        "2024-06-01,30,0.10,1.0",
                        "2024-06-01,20,0.20,3.0",
                        "2024-06-01,0,0.90,10.0",
                        "2024-06-02,30,0.30,2.0",
                        "2024-06-02,10,0.50,2.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            daily = read_g03_daily_theta(g03_path, 0, 20)

        self.assertEqual(
            [date.strftime("%Y-%m-%d") for date in daily.index],
            ["2024-06-01", "2024-06-02"],
        )
        np.testing.assert_allclose(daily.to_numpy(), [0.175, 0.4])

    def test_read_g03_daily_theta_converts_y_to_depth_from_surface(self):
        with tempfile.TemporaryDirectory(prefix="codex_g03_depth_") as tmp_dir:
            g03_path = Path(tmp_dir) / "synthetic.G03"
            g03_path.write_text(
                "\n".join(
                    [
                        "Date,Y,thNew,Area",
                        "2024-06-01,200,0.10,1.0",
                        "2024-06-01,190,0.20,3.0",
                        "2024-06-01,170,0.90,100.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            daily = read_g03_daily_theta(g03_path, 0, 20)

        np.testing.assert_allclose(daily.to_numpy(), [0.175])

    def test_read_g03_daily_theta_interpolates_point_depth(self):
        with tempfile.TemporaryDirectory(prefix="codex_g03_point_") as tmp_dir:
            g03_path = Path(tmp_dir) / "synthetic.G03"
            g03_path.write_text(
                "\n".join(
                    [
                        "Date,Y,thNew,Area",
                        "2024-06-01,100,0.10,1.0",
                        "2024-06-01,80,0.30,1.0",
                        "2024-06-01,60,0.50,1.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            theta_10 = read_g03_daily_theta(g03_path, 10, 10)
            theta_30 = read_g03_daily_theta(g03_path, 30, 30)

        np.testing.assert_allclose(theta_10.to_numpy(), [0.20])
        np.testing.assert_allclose(theta_30.to_numpy(), [0.40])

    def test_build_simulation_vector_matches_observation_spec_order(self):
        with tempfile.TemporaryDirectory(prefix="codex_sim_vector_") as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "member.g01").write_text(
                "\n".join(
                    [
                        "Date,LAI",
                        "2024-06-01 00:00,1.0",
                        "2024-06-01 12:00,3.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "member.G03").write_text(
                "\n".join(
                    [
                        "Date,Y,thNew,Area",
                        "2024-06-01,100,0.10,1.0",
                        "2024-06-01,80,0.30,1.0",
                        "2024-06-01,60,0.50,1.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            values = build_simulation_vector(
                run_dir,
                [
                    {
                        "date": "2024-06-01",
                        "variable": "theta",
                        "depth_top_cm": 30,
                        "depth_bottom_cm": 30,
                    },
                    {
                        "date": "2024-06-01",
                        "variable": "LAI",
                        "depth_top_cm": None,
                        "depth_bottom_cm": None,
                    },
                    {
                        "date": "2024-06-01",
                        "variable": "theta",
                        "depth_top_cm": 10,
                        "depth_bottom_cm": 10,
                    },
                    {
                        "date": "2024-06-01",
                        "variable": "LAI",
                        "depth_top_cm": None,
                        "depth_bottom_cm": None,
                    },
                ],
            )

        np.testing.assert_allclose(values, [0.40, 2.0, 0.20, 2.0])

    def test_build_simulation_vector_reads_g03_once_for_two_theta_depths(self):
        with tempfile.TemporaryDirectory(prefix="codex_sim_vector_g03_") as tmp_dir:
            run_dir = Path(tmp_dir)
            (run_dir / "member.G03").write_text(
                "\n".join(
                    [
                        " Date , y , thnew , AREA , Ignored",
                        "2024-06-01,100,0.10,1.0,skip",
                        "2024-06-01,80,0.30,1.0,skip",
                        "2024-06-01,60,0.50,1.0,skip",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch(
                "da_framework.output_reader.pd.read_csv",
                wraps=pd.read_csv,
            ) as read_csv:
                values = build_simulation_vector(
                    run_dir,
                    [
                        {
                            "date": "2024-06-01",
                            "variable": "theta",
                            "depth_top_cm": 30,
                            "depth_bottom_cm": 30,
                        },
                        {
                            "date": "2024-06-01",
                            "variable": "soil_water_content",
                            "depth_top_cm": 10,
                            "depth_bottom_cm": 10,
                        },
                    ],
                )

        self.assertEqual(read_csv.call_count, 1)
        self.assertIn("usecols", read_csv.call_args.kwargs)
        np.testing.assert_allclose(values, [0.40, 0.20])


if __name__ == "__main__":
    unittest.main()
