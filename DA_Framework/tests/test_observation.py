import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import context  # noqa: F401
from da_framework.observation import read_observations_csv


class ObservationCsvTests(unittest.TestCase):
    def test_read_observations_csv_sorts_and_drops_invalid_rows(self):
        rows = [
            {
                "date": "2024-06-02",
                "variable": "swc",
                "depth_top_cm": 20,
                "depth_bottom_cm": 40,
                "value": 0.31,
                "std": 0.03,
            },
            {
                "date": "2024-06-01",
                "variable": "theta",
                "depth_top_cm": 0,
                "depth_bottom_cm": 20,
                "value": 0.25,
                "std": 0.02,
            },
            {
                "date": "2024-06-01",
                "variable": "LAI",
                "depth_top_cm": "",
                "depth_bottom_cm": "",
                "value": 2.5,
                "std": 0.2,
            },
            {
                "date": "2024-06-03",
                "variable": "LAI",
                "depth_top_cm": "",
                "depth_bottom_cm": "",
                "value": "",
                "std": 0.2,
            },
            {
                "date": "2024-06-04",
                "variable": "theta",
                "depth_top_cm": 0,
                "depth_bottom_cm": 20,
                "value": 0.28,
                "std": 0,
            },
            {
                "date": "2024-06-05",
                "variable": "theta",
                "depth_top_cm": 0,
                "depth_bottom_cm": 20,
                "value": 0.29,
                "std": "bad",
            },
        ]

        with tempfile.TemporaryDirectory(prefix="codex_observation_") as tmp_dir:
            csv_path = Path(tmp_dir) / "observations.csv"
            pd.DataFrame(rows).to_csv(csv_path, index=False)

            data = read_observations_csv(csv_path)

        self.assertEqual(
            [(spec.date.strftime("%Y-%m-%d"), spec.variable) for spec in data.specs],
            [
                ("2024-06-01", "LAI"),
                ("2024-06-01", "theta"),
                ("2024-06-02", "theta"),
            ],
        )
        self.assertIsNone(data.specs[0].depth_top_cm)
        self.assertIsNone(data.specs[0].depth_bottom_cm)
        self.assertEqual(data.specs[1].depth_top_cm, 0.0)
        self.assertEqual(data.specs[1].depth_bottom_cm, 20.0)
        np.testing.assert_allclose(data.values, [2.5, 0.25, 0.31])
        np.testing.assert_allclose(data.std, [0.2, 0.02, 0.03])
        self.assertEqual(data.frame["variable"].tolist(), ["LAI", "theta", "theta"])
        self.assertEqual(len(data.dropped_rows), 3)
        self.assertEqual(
            data.dropped_rows["drop_reason"].tolist(),
            [
                "value_missing_or_invalid",
                "std_missing_or_non_positive",
                "std_missing_or_non_positive",
            ],
        )

    def test_example_observations_use_ten_windows_and_three_variables(self):
        csv_path = (
            context.REPO_ROOT
            / "DA_Framework"
            / "examples"
            / "synthetic_observations.csv"
        )

        data = read_observations_csv(csv_path)

        dates = data.frame["date"].dt.strftime("%Y-%m-%d")
        unique_dates = dates.drop_duplicates().tolist()
        intervals = [
            (pd.Timestamp(end) - pd.Timestamp(start)).days
            for start, end in zip(unique_dates, unique_dates[1:])
        ]
        keys = [
            (
                spec.date,
                spec.variable,
                spec.depth_top_cm,
                spec.depth_bottom_cm,
            )
            for spec in data.specs
        ]

        self.assertTrue(data.dropped_rows.empty)
        self.assertEqual(
            unique_dates,
            [
                "2007-05-20",
                "2007-05-25",
                "2007-05-30",
                "2007-06-04",
                "2007-06-09",
                "2007-06-14",
                "2007-06-19",
                "2007-06-24",
                "2007-06-29",
                "2007-07-04",
            ],
        )
        self.assertEqual(intervals, [5] * 9)
        self.assertEqual(len(data.values), 30)
        self.assertEqual(len(set(keys)), len(keys))
        for date in unique_dates:
            date_frame = data.frame.loc[dates == date]
            self.assertEqual(date_frame["variable"].tolist(), ["LAI", "theta", "theta"])
            np.testing.assert_allclose(
                date_frame["depth_top_cm"].to_numpy(dtype=float),
                [np.nan, 10.0, 30.0],
                equal_nan=True,
            )
            np.testing.assert_allclose(
                date_frame["depth_bottom_cm"].to_numpy(dtype=float),
                [np.nan, 10.0, 30.0],
                equal_nan=True,
            )
            np.testing.assert_allclose(
                date_frame["std"].to_numpy(dtype=float),
                [0.5, 0.05, 0.05],
            )


if __name__ == "__main__":
    unittest.main()
