import json
import tempfile
import unittest
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pandas as pd

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_CHECKS
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_FIGURES
from da_framework.drip_journal_readiness import build_readiness_report
from da_framework.drip_validation_dossier import build_validation_dossier
from da_framework.drip_validation_dossier import main
from da_framework.drip_validation_dossier import _reviewer_evidence_matrix


class DripValidationDossierTests(unittest.TestCase):
    def test_dossier_indexes_internal_evidence_and_missing_external_gate(self):
        with tempfile.TemporaryDirectory(prefix="codex_dossier_") as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            readiness = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )
            _write_suite_report(root)

            dossier = build_validation_dossier(
                readiness_report=root
                / "readiness"
                / "journal_readiness_report.json",
                output_dir=root / "dossier",
            )

            markdown = Path(dossier["markdown_path"]).read_text(encoding="utf-8")
            data = json.loads(Path(dossier["json_path"]).read_text(encoding="utf-8"))

        self.assertEqual(readiness["overall_status"], "missing_external_evidence")
        self.assertEqual(data["summary"]["overall_status"], "missing_external_evidence")
        self.assertIn("precision_delta_theta_root_overlay_0601.png", markdown)
        self.assertIn("precision_root_density_0601.png", markdown)
        self.assertIn("precision_spatial_worst_case_delta_root.png", markdown)
        self.assertIn("external_2d_field_comparison_present", markdown)
        self.assertIn("external_validation_metric_panel.png", markdown)
        self.assertIn("Reviewer Evidence Matrix", markdown)
        self.assertIn("Independent external 2D field validation", markdown)
        self.assertIn("Implementation History", markdown)
        self.assertIn("implementation_history", data)
        self.assertIn("reviewer_evidence_matrix", data)
        self.assertEqual(
            data["implementation_history"]["base_commit"],
            "199627a4a68e464dfd7c31d2cc65f1de26b54972",
        )
        matrix = {
            row["criterion"]: row["status"]
            for row in data["reviewer_evidence_matrix"]
        }
        self.assertEqual(matrix["Water accounting"], "pass")
        self.assertEqual(
            matrix["Independent external 2D field validation"],
            "missing_external_evidence",
        )
        self.assertTrue(
            any(
                item["name"] == "precision_spatial_delta_root.csv"
                and item["exists"]
                for item in data["precision_artifacts"]
            )
        )
        self.assertTrue(
            any(
                item["name"] == "external_validation_metric_summary.csv"
                and item["exists"]
                for item in data["suite_artifacts"]
            )
        )

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory(prefix="codex_dossier_") as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            exit_code = main(
                [
                    "--readiness-report",
                    str(root / "readiness" / "journal_readiness_report.json"),
                    "--output-dir",
                    str(root / "dossier"),
                    "--title",
                    "Synthetic drip dossier",
                ]
            )
            markdown_exists = (root / "dossier" / "drip_validation_dossier.md").is_file()
            json_exists = (root / "dossier" / "drip_validation_dossier.json").is_file()

        self.assertEqual(exit_code, 0)
        self.assertTrue(markdown_exists)
        self.assertTrue(json_exists)

    def test_dirty_worktree_marks_implementation_traceability_diagnostic(self):
        checks = pd.DataFrame(
            [
                {
                    "check": "external_2d_field_comparison_present",
                    "value": 0,
                    "status": "missing_external_evidence",
                    "detail": "",
                    "source": "",
                }
            ]
        )
        matrix = _reviewer_evidence_matrix(
            checks,
            {
                "external_comparison_count": 0,
            },
            [],
            [],
            [],
            {
                "status": "available",
                "base_commit": "199627a4a68e464dfd7c31d2cc65f1de26b54972",
                "head_commit": "abc123",
                "commit_count": 2,
                "changed_file_count": 3,
                "changed_files_by_area": [],
                "dirty_worktree_entry_count": 2,
                "dirty_worktree_entries": [" M file_a", "?? file_b"],
            },
        )
        implementation = {
            row["criterion"]: row for row in matrix
        }["Implementation traceability"]

        self.assertEqual(implementation["status"], "diagnostic")
        self.assertIn("uncommitted", implementation["remaining_gap"])


def _precision_dir(root):
    precision_dir = root / "precision"
    precision_dir.mkdir()
    pd.DataFrame(
        [
            {"check": check_name, "value": 1, "status": "pass", "detail": ""}
            for check_name in REQUIRED_PRECISION_CHECKS
        ]
    ).to_csv(precision_dir / "precision_validation_checks.csv", index=False)
    for name in REQUIRED_PRECISION_FIGURES:
        _write_nonblank_png(precision_dir / name)
    spatial_path = precision_dir / "precision_spatial_delta_root.csv"
    _write_root_spatial_csv(spatial_path)
    _write_root_temporal_csv(
        precision_dir / "precision_spatial_temporal_delta_root.csv",
        spatial_path,
    )
    pd.read_csv(spatial_path).head(6).to_csv(
        precision_dir / "precision_spatial_worst_cases.csv",
        index=False,
    )
    return precision_dir


def _write_root_spatial_csv(path):
    soils = ("loam", "sandy_loam", "clay_loam")
    grids = ("narrow_x075", "base_x100", "wide_x125")
    scenarios = (
        "long_low_single",
        "long_multi_node",
        "long_high_single",
        "long_pressure_single",
    )
    pd.DataFrame(
        [
            _root_spatial_row(soil, grid, scenario, 0.012)
            for soil in soils
            for grid in grids
            for scenario in scenarios
        ]
    ).to_csv(path, index=False)


def _root_spatial_row(soil, grid, scenario, root_weighted_delta):
    return {
        "case": f"{soil}__{grid}__{scenario}",
        "soil": soil,
        "grid": grid,
        "scenario": scenario,
        "positive_delta_root_overlap_fraction": 1.0,
        "positive_delta_root_area_fraction": 1.0,
        "positive_delta_storage_cm2": 1.0,
        "negative_delta_storage_cm2": 0.1,
        "net_delta_storage_cm2": 0.9,
        "root_area_cm2": 1.0,
        "positive_delta_root_storage_cm2": 1.0,
        "positive_delta_root_storage_fraction": 1.0,
        "root_weighted_delta_theta": root_weighted_delta,
    }


def _write_root_temporal_csv(path, spatial_path):
    rows = []
    for row in pd.read_csv(spatial_path).to_dict("records"):
        for date in pd.date_range("2007-05-20", periods=8, freq="D"):
            temporal = dict(row)
            temporal["date"] = date.strftime("%m/%d/%Y")
            temporal["positive_delta_storage_cm2"] = 1.0 + 0.1 * len(rows)
            temporal["positive_delta_root_storage_fraction"] = 1.0
            rows.append(temporal)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_nonblank_png(path):
    image = np.zeros((480, 720, 3), dtype=float)
    image[:, :, 0] = np.linspace(0.0, 1.0, 720)
    image[:, :, 1] = np.linspace(1.0, 0.0, 480)[:, None]
    mpimg.imsave(path, image)


def _write_suite_report(root):
    cases_csv = root / "external_validation_cases.csv"
    summary_csv = root / "external_validation_metric_summary.csv"
    figure_path = root / "external_validation_metric_panel.png"
    pd.DataFrame([{"case": "synthetic", "status": "pass"}]).to_csv(
        cases_csv,
        index=False,
    )
    pd.DataFrame([{"metric": "theta_rmse", "case_count": 1}]).to_csv(
        summary_csv,
        index=False,
    )
    _write_nonblank_png(figure_path)
    (root / "external_validation_suite_report.json").write_text(
        json.dumps(
            {
                "suite_manifest": str(root / "suite.json"),
                "cases_csv": str(cases_csv),
                "metric_summary_csv": str(summary_csv),
                "metric_panel_figure": str(figure_path),
                "journal_readiness_report": str(
                    root / "readiness" / "journal_readiness_report.json"
                ),
            }
        ),
        encoding="utf-8",
    )

if __name__ == "__main__":
    unittest.main()
