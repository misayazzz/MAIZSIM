import hashlib
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
from da_framework.drip_journal_readiness import build_readiness_report, main
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_CHECKS
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_FIGURES


class DripJournalReadinessTests(unittest.TestCase):
    def test_internal_precision_without_external_field_is_not_journal_ready(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            output_dir = root / "readiness"

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=output_dir,
            )

            checks = pd.read_csv(report["checks_csv"])

        self.assertEqual(report["overall_status"], "missing_external_evidence")
        self.assertIn("missing_external_evidence", report["status_counts"])
        external = checks[
            checks["check"] == "external_2d_field_comparison_present"
        ].iloc[0]
        self.assertEqual(external["status"], "missing_external_evidence")

    def test_missing_root_zone_spatial_evidence_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root, write_root_spatial=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            root_check = checks[
                checks["check"] == "root_zone_spatial_delta_root_present"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(root_check["status"], "fail")

    def test_blank_precision_figure_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            _write_blank_png(
                precision_dir / "precision_root_density_0601.png",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            figure_check = checks[
                checks["check"] == "precision_figure_precision_root_density_0601"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(figure_check["status"], "fail")

    def test_sparse_root_zone_grid_coverage_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            spatial_path = precision_dir / "precision_spatial_delta_root.csv"
            spatial = pd.read_csv(spatial_path)
            spatial["grid"] = "base_x100"
            spatial.to_csv(spatial_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            grid_check = checks[
                checks["check"] == "root_zone_spatial_grid_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(grid_check["status"], "fail")

    def test_sparse_root_zone_scenario_coverage_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            spatial_path = precision_dir / "precision_spatial_delta_root.csv"
            spatial = pd.read_csv(spatial_path)
            spatial["scenario"] = "long_low_single"
            spatial.to_csv(spatial_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            scenario_check = checks[
                checks["check"] == "root_zone_spatial_scenario_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(scenario_check["status"], "fail")

    def test_low_root_zone_storage_overlap_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            spatial_path = precision_dir / "precision_spatial_delta_root.csv"
            spatial = pd.read_csv(spatial_path)
            spatial.loc[0, "positive_delta_root_storage_fraction"] = 0.1
            spatial.to_csv(spatial_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            storage_check = checks[
                checks["check"]
                == "root_zone_positive_delta_root_storage_fraction_min"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(storage_check["status"], "fail")

    def test_low_positive_delta_storage_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            spatial_path = precision_dir / "precision_spatial_delta_root.csv"
            spatial = pd.read_csv(spatial_path)
            spatial.loc[0, "positive_delta_storage_cm2"] = 0.0
            spatial.to_csv(spatial_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            storage_check = checks[
                checks["check"] == "root_zone_positive_delta_storage_cm2_min"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(storage_check["status"], "fail")

    def test_missing_temporal_root_zone_evidence_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root, write_root_temporal=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            temporal_check = checks[
                checks["check"]
                == "root_zone_spatial_temporal_delta_root_present"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(temporal_check["status"], "fail")

    def test_sparse_temporal_date_coverage_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            temporal_path = (
                precision_dir / "precision_spatial_temporal_delta_root.csv"
            )
            temporal = pd.read_csv(temporal_path)
            temporal = temporal[temporal["date"] == temporal["date"].iloc[0]]
            temporal.to_csv(temporal_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            temporal_check = checks[
                checks["check"]
                == "root_zone_spatial_temporal_date_count_min"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(temporal_check["status"], "fail")

    def test_low_temporal_root_storage_overlap_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            temporal_path = (
                precision_dir / "precision_spatial_temporal_delta_root.csv"
            )
            temporal = pd.read_csv(temporal_path)
            temporal.loc[0, "positive_delta_root_storage_fraction"] = 0.1
            temporal.to_csv(temporal_path, index=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
            )

            checks = pd.read_csv(report["checks_csv"])
            temporal_check = checks[
                checks["check"]
                == "root_zone_spatial_temporal_root_storage_fraction_min"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(temporal_check["status"], "fail")

    def test_diverse_external_field_comparisons_pass_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = _diverse_external_dirs(root)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

        self.assertEqual(report["overall_status"], "pass")
        self.assertNotIn("fail", report["status_counts"])

    def test_single_external_case_fails_default_multi_case_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
            )

            checks = pd.read_csv(report["checks_csv"])
            case_count = checks[
                checks["check"] == "external_2d_field_comparison_case_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(case_count["status"], "fail")

    def test_relaxed_external_evidence_thresholds_fail_policy_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            policy = checks[checks["check"] == "journal_threshold_policy"].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(policy["status"], "fail")
        self.assertIn("external_case_count_min", policy["detail"])

    def test_repeated_external_conditions_fail_default_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(root, name=f"hydrus_compare_{index}")
                for index in range(3)
            ]

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            soil_count = checks[
                checks["check"] == "external_soil_parameter_set_count"
            ].iloc[0]
            event_count = checks[
                checks["check"] == "external_irrigation_event_setting_count"
            ].iloc[0]
            output_time_count = checks[
                checks["check"] == "external_output_time_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(soil_count["status"], "fail")
        self.assertEqual(event_count["status"], "fail")
        self.assertEqual(output_time_count["status"], "fail")

    def test_diverse_external_conditions_pass_default_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(
                    root,
                    name="loam_compare",
                    soil_scale=1.0,
                    emitter_rate_l_h=2.0,
                ),
                _external_dir(
                    root,
                    name="sand_compare",
                    soil_scale=4.0,
                    emitter_rate_l_h=1.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="clay_compare",
                    soil_scale=0.2,
                    emitter_rate_l_h=2.0,
                    event_duration_h=4.0,
                    output_time="2024-06-01T04:00:00",
                    event_relative_time_h=4.0,
                ),
            ]

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

        self.assertEqual(report["overall_status"], "pass")
        self.assertNotIn("fail", report["status_counts"])

    def test_tiny_soil_parameter_perturbations_fail_substantive_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(
                    root,
                    name="loam_compare",
                    soil_scale=1.0,
                    emitter_rate_l_h=2.0,
                    event_duration_h=2.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="loam_near_compare",
                    soil_scale=1.02,
                    emitter_rate_l_h=1.0,
                    event_duration_h=2.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="loam_near_long_compare",
                    soil_scale=1.04,
                    emitter_rate_l_h=2.0,
                    event_duration_h=4.0,
                    output_time="2024-06-01T04:00:00",
                    event_relative_time_h=4.0,
                ),
            ]

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            ks_ratio = checks[
                checks["check"] == "external_soil_ks_ratio"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(ks_ratio["status"], "fail")
        self.assertLess(float(ks_ratio["value"]), 5.0)

    def test_narrow_event_and_time_spans_fail_substantive_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(
                    root,
                    name="loam_compare",
                    soil_scale=1.0,
                    emitter_rate_l_h=2.0,
                    event_duration_h=2.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="sand_compare",
                    soil_scale=4.0,
                    emitter_rate_l_h=2.2,
                    event_duration_h=2.5,
                    output_time="2024-06-01T02:30:00",
                    event_relative_time_h=2.5,
                ),
                _external_dir(
                    root,
                    name="clay_compare",
                    soil_scale=0.2,
                    emitter_rate_l_h=2.3,
                    event_duration_h=3.0,
                    output_time="2024-06-01T03:00:00",
                    event_relative_time_h=3.0,
                ),
            ]

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            emitter_ratio = checks[
                checks["check"] == "external_emitter_rate_ratio"
            ].iloc[0]
            duration_span = checks[
                checks["check"] == "external_event_duration_span_h"
            ].iloc[0]
            output_span = checks[
                checks["check"] == "external_output_time_span_h"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(emitter_ratio["status"], "fail")
        self.assertEqual(duration_span["status"], "fail")
        self.assertEqual(output_span["status"], "fail")

    def test_duplicate_reference_case_id_fails_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(
                    root,
                    name="loam_compare",
                    soil_scale=1.0,
                    emitter_rate_l_h=2.0,
                ),
                _external_dir(
                    root,
                    name="sand_compare",
                    soil_scale=4.0,
                    emitter_rate_l_h=1.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="clay_compare",
                    soil_scale=0.2,
                    emitter_rate_l_h=2.0,
                    event_duration_h=4.0,
                    output_time="2024-06-01T04:00:00",
                    event_relative_time_h=4.0,
                ),
            ]
            manifest_path = external_dirs[1] / "case_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["reference_identity"]["reference_case_id"] = (
                "loam_compare_t2h"
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            audit_path = external_dirs[1] / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            manifest_audit = _file_audit(manifest_path)
            audit["inputs"]["comparison_manifest"] = manifest_audit
            audit["artifacts"]["comparison_manifest_json"] = manifest_audit
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            reference_check = checks[
                checks["check"] == "external_reference_case_id_unique_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(reference_check["status"], "fail")

    def test_repeated_external_relative_time_fails_default_diversity_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = [
                _external_dir(
                    root,
                    name="loam_compare",
                    soil_scale=1.0,
                    emitter_rate_l_h=2.0,
                    output_time="2024-06-01T02:00:00",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="sand_compare",
                    soil_scale=4.0,
                    emitter_rate_l_h=1.0,
                    output_time="120 min after event start",
                    event_relative_time_h=2.0,
                ),
                _external_dir(
                    root,
                    name="clay_compare",
                    soil_scale=0.2,
                    emitter_rate_l_h=2.0,
                    event_duration_h=4.0,
                    output_time="2 h after event start",
                    event_relative_time_h=2.0,
                ),
            ]

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            soil_count = checks[
                checks["check"] == "external_soil_parameter_set_count"
            ].iloc[0]
            event_count = checks[
                checks["check"] == "external_irrigation_event_setting_count"
            ].iloc[0]
            output_time_count = checks[
                checks["check"] == "external_output_time_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(soil_count["status"], "pass")
        self.assertEqual(event_count["status"], "pass")
        self.assertEqual(output_time_count["status"], "fail")

    def test_bad_external_field_metric_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, theta_rmse=0.08)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            theta_check = checks[
                checks["check"] == f"external_theta_rmse::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(theta_check["status"], "fail")

    def test_relaxed_quality_threshold_fails_journal_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            thresholds = _single_case_thresholds()
            thresholds["theta_rmse_max"] = 0.50

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=thresholds,
            )

            checks = pd.read_csv(report["checks_csv"])
            policy_check = checks[
                checks["check"] == "journal_threshold_policy"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(policy_check["status"], "fail")
        self.assertIn("theta_rmse_max", policy_check["detail"])

    def test_bad_uncertainty_envelope_metric_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, uncertainty_fraction=0.25)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            uncertainty_check = checks[
                checks["check"]
                == (
                    "external_theta_abs_residual_le_2sd_fraction::"
                    f"{external_dir.name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(uncertainty_check["status"], "fail")

    def test_missing_uncertainty_metrics_fail_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, uncertainty_fraction=None)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            uncertainty_check = checks[
                checks["check"]
                == (
                    "external_observation_uncertainty_metrics_present::"
                    f"{external_dir.name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(uncertainty_check["status"], "fail")

    def test_missing_source_wet_metrics_fail_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, include_source_wet=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            source_check = checks[
                checks["check"]
                == f"external_source_wet_iou_present::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(source_check["status"], "fail")

    def test_missing_storage_metrics_fail_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, include_storage=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            storage_check = checks[
                checks["check"]
                == f"external_storage_metrics_present::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(storage_check["status"], "fail")

    def test_points_count_mismatch_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, point_rows=24)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            count_check = checks[
                checks["check"]
                == f"external_points_count_matches_summary::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(count_check["status"], "fail")

    def test_multirow_external_summary_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, duplicate_summary=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            summary_check = checks[
                checks["check"]
                == f"external_summary_single_row::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(summary_check["status"], "fail")

    def test_point_residual_identity_mismatch_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, corrupt_theta_residual=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            identity_check = checks[
                checks["check"]
                == f"external_points_theta_residual_identity::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(identity_check["status"], "fail")

    def test_summary_metric_mismatch_with_points_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            summary_path = external_dir / "case_summary.csv"
            summary = pd.read_csv(summary_path)
            summary.loc[0, "theta_rmse"] = 0.021
            summary.to_csv(summary_path, index=False)
            audit = json.loads((external_dir / "case_audit.json").read_text())
            audit["artifacts"]["summary_csv"] = _file_audit(summary_path)
            (external_dir / "case_audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            recompute_check = checks[
                checks["check"]
                == (
                    "external_summary_matches_points_theta_rmse::"
                    f"{external_dir.name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(recompute_check["status"], "fail")

    def test_coverage_metric_mismatch_with_reference_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            summary_path = external_dir / "case_summary.csv"
            summary = pd.read_csv(summary_path)
            summary.loc[0, "comparison_point_fraction"] = 0.99
            summary.to_csv(summary_path, index=False)
            audit = json.loads((external_dir / "case_audit.json").read_text())
            audit["artifacts"]["summary_csv"] = _file_audit(summary_path)
            (external_dir / "case_audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            recompute_check = checks[
                checks["check"]
                == (
                    "external_summary_matches_reference_"
                    f"comparison_point_fraction::{external_dir.name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(recompute_check["status"], "fail")

    def test_point_delta_mismatch_with_reference_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            points_path = external_dir / "case_points.csv"
            points = pd.read_csv(points_path)
            points.loc[0, "hydrus_delta_theta"] += 0.01
            points.loc[0, "maizsim_delta_theta"] += 0.01
            points.to_csv(points_path, index=False)
            audit = json.loads((external_dir / "case_audit.json").read_text())
            audit["artifacts"]["points_csv"] = _file_audit(points_path)
            (external_dir / "case_audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            reference_check = checks[
                checks["check"]
                == (
                    "external_points_match_reference_hydrus_delta_theta::"
                    f"{external_dir.name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(reference_check["status"], "fail")

    def test_low_resolution_external_figure_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            figure_path = external_dir / "case_fields.png"
            _write_low_resolution_png(figure_path)
            audit = json.loads((external_dir / "case_audit.json").read_text())
            audit["artifacts"]["figure"] = {
                **_file_audit(figure_path),
                "nonblank": True,
                "pixel_width": 8,
                "pixel_height": 8,
                "pixel_range": 1.0,
            }
            (external_dir / "case_audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            figure_check = checks[
                checks["check"] == f"external_figure_nonblank::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(figure_check["status"], "fail")
        self.assertIn("resolution", figure_check["detail"])

    def test_nonpositive_point_area_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            points_path = external_dir / "case_points.csv"
            points = pd.read_csv(points_path)
            points.loc[0, "area_cm2"] = -1.0
            points.to_csv(points_path, index=False)
            audit = json.loads((external_dir / "case_audit.json").read_text())
            audit["artifacts"]["points_csv"] = _file_audit(points_path)
            (external_dir / "case_audit.json").write_text(
                json.dumps(audit),
                encoding="utf-8",
            )

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            area_check = checks[
                checks["check"]
                == f"external_points_area_cm2_positive::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(area_check["status"], "fail")

    def test_theta_outside_soil_bounds_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            points_path = external_dir / "case_points.csv"
            points = pd.read_csv(points_path)
            points["hydrus_theta"] = 0.80
            points["maizsim_theta"] = 0.82
            points["theta_residual"] = 0.02
            points.to_csv(points_path, index=False)
            summary_path = external_dir / "case_summary.csv"
            summary = pd.read_csv(summary_path)
            summary.loc[0, "hydrus_theta_min"] = 0.80
            summary.loc[0, "hydrus_theta_max"] = 0.80
            summary.loc[0, "maizsim_theta_min"] = 0.82
            summary.loc[0, "maizsim_theta_max"] = 0.82
            summary.to_csv(summary_path, index=False)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["artifacts"]["points_csv"] = _file_audit(points_path)
            audit["artifacts"]["summary_csv"] = _file_audit(summary_path)
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            bounds_check = checks[
                checks["check"]
                == f"external_points_theta_physical_bounds::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(bounds_check["status"], "fail")
        self.assertIn("theta_s=0.4", bounds_check["detail"])

    def test_audit_hash_mismatch_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, corrupt_audit=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")

    def test_empty_audit_inputs_fail_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, empty_audit_inputs=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("Input audit problems", audit_check["detail"])

    def test_missing_raw_reference_audit_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit.pop("raw_reference_files")
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("Raw reference audit problems", audit_check["detail"])

    def test_missing_baseline_raw_reference_role_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["raw_reference_files"] = [
                item
                for item in audit["raw_reference_files"]
                if "baseline" not in item["role"]
            ]
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("baseline", audit_check["detail"])

    def test_uri_only_raw_reference_file_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["raw_reference_files"][0][
                "path_or_uri"
            ] = "doi:10.0000/example-hydrus-event"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("local file is required", audit_check["detail"])

    def test_audit_selected_time_mismatch_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["selected_times"]["hydrus"]["selected_time_h"] = 4.0
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("Time audit problems", audit_check["detail"])

    def test_missing_baseline_selected_time_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root)
            audit_path = external_dir / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["selected_times"]["hydrus_baseline"].pop("selected_time_h")
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            audit_check = checks[
                checks["check"] == f"external_audit_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(audit_check["status"], "fail")
        self.assertIn("hydrus_baseline selected_time_h is missing", audit_check["detail"])

    def test_missing_point_uncertainty_columns_fail_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, points_include_uncertainty=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            points_check = checks[
                checks["check"]
                == f"external_points_uncertainty_columns_present::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(points_check["status"], "fail")

    def test_low_spatial_overlap_coverage_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, comparison_area_fraction=0.70)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            coverage_check = checks[
                checks["check"]
                == f"external_comparison_area_fraction::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(coverage_check["status"], "fail")

    def test_missing_external_manifest_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, write_manifest=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

        self.assertEqual(report["overall_status"], "fail")
        self.assertIn("fail", report["status_counts"])

    def test_placeholder_external_manifest_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, placeholder_manifest=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            manifest_check = checks[
                checks["check"] == f"external_manifest_valid::{external_dir.name}"
            ].iloc[0]
            output_time_count = checks[
                checks["check"] == "external_output_time_count"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(manifest_check["status"], "fail")
        self.assertEqual(output_time_count["status"], "fail")
        self.assertEqual(float(output_time_count["value"]), 0.0)

    def test_calibration_external_manifest_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, calibration_data_used=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            manifest_check = checks[
                checks["check"] == f"external_manifest_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(manifest_check["status"], "fail")

    def test_unit_test_external_manifest_fails_journal_evidence_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = _diverse_external_dirs(root)
            manifest_path = external_dirs[0] / "case_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["reference_data_provenance"][
                "source_system"
            ] = "unit-test fixture writer"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            audit_path = external_dirs[0] / "case_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["inputs"]["comparison_manifest"] = _file_audit(manifest_path)
            audit["artifacts"]["comparison_manifest_json"] = _file_audit(manifest_path)
            audit_path.write_text(json.dumps(audit), encoding="utf-8")

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=external_dirs,
            )

            checks = pd.read_csv(report["checks_csv"])
            evidence_check = checks[
                checks["check"]
                == (
                    "external_manifest_journal_evidence::"
                    f"{external_dirs[0].name}"
                )
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(evidence_check["status"], "fail")
        self.assertIn("unit-test", evidence_check["detail"])

    def test_missing_external_points_file_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, write_points=False)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            points_check = checks[
                checks["check"] == f"external_points_present::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(points_check["status"], "fail")

    def test_outputs_index_mismatch_fails_readiness_gate(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dir = _external_dir(root, corrupt_outputs_index=True)

            report = build_readiness_report(
                precision_dir=precision_dir,
                output_dir=root / "readiness",
                external_comparison_dirs=[external_dir],
                thresholds=_single_case_thresholds(),
            )

            checks = pd.read_csv(report["checks_csv"])
            outputs_check = checks[
                checks["check"]
                == f"external_outputs_index_valid::{external_dir.name}"
            ].iloc[0]

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(outputs_check["status"], "fail")
        self.assertIn("points_csv", outputs_check["detail"])

    def test_cli_writes_outputs_and_returns_zero_for_passing_case(self):
        with tempfile.TemporaryDirectory(
            prefix="codex_journal_readiness_",
        ) as tmp_dir:
            root = Path(tmp_dir)
            precision_dir = _precision_dir(root)
            external_dirs = _diverse_external_dirs(root)
            output_dir = root / "readiness"
            arguments = [
                "--precision-dir",
                str(precision_dir),
                "--output-dir",
                str(output_dir),
            ]
            for external_dir in external_dirs:
                arguments.extend(["--external-comparison-dir", str(external_dir)])

            exit_code = main(arguments)
            report = json.loads(
                (output_dir / "journal_readiness_report.json").read_text(
                    encoding="utf-8",
                )
            )
            checks_exist = (
                output_dir / "journal_readiness_checks.csv"
            ).is_file()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["overall_status"], "pass")
        self.assertTrue(checks_exist)


def _precision_dir(root, *, write_root_spatial=True, write_root_temporal=True):
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
    if write_root_spatial:
        _write_root_spatial_csv(precision_dir / "precision_spatial_delta_root.csv")
    if write_root_temporal and write_root_spatial:
        _write_root_temporal_csv(
            precision_dir / "precision_spatial_temporal_delta_root.csv",
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


def _write_root_temporal_csv(path):
    rows = []
    for row in pd.read_csv(path.parent / "precision_spatial_delta_root.csv").to_dict(
        "records"
    ):
        for date in pd.date_range("2007-05-20", periods=8, freq="D"):
            temporal = dict(row)
            temporal["date"] = date.strftime("%m/%d/%Y")
            temporal["positive_delta_storage_cm2"] = 1.0 + 0.1 * len(rows)
            temporal["positive_delta_root_storage_fraction"] = 1.0
            rows.append(temporal)
    pd.DataFrame(rows).to_csv(path, index=False)


def _external_dir(
    root,
    *,
    name="hydrus_compare",
    theta_rmse=0.02,
    write_manifest=True,
    placeholder_manifest=False,
    write_points=True,
    soil_scale=1.0,
    emitter_rate_l_h=2.0,
    event_duration_h=2.0,
    output_time="2024-06-01T00:00:00",
    event_relative_time_h=2.0,
    calibration_data_used=False,
    uncertainty_fraction=1.0,
    comparison_point_fraction=1.0,
    comparison_area_fraction=1.0,
    include_source_wet=True,
    include_storage=True,
    point_rows=25,
    points_include_uncertainty=True,
    duplicate_summary=False,
    corrupt_theta_residual=False,
    corrupt_audit=False,
    empty_audit_inputs=False,
    corrupt_outputs_index=False,
):
    external_dir = root / name
    external_dir.mkdir()
    points = None
    if write_points:
        points = _external_points_frame(
            point_rows,
            theta_residual=theta_rmse,
            delta_residual=0.015,
            include_source_wet=include_source_wet,
            include_storage=include_storage,
            include_uncertainty=points_include_uncertainty,
            corrupt_theta_residual=corrupt_theta_residual,
        )
    summary = {
        "point_count": 25,
        "hydrus_reference_point_count": float(point_rows),
        "comparison_point_count": float(point_rows),
        "dropped_reference_point_count": 0.0,
        "theta_rmse": theta_rmse,
        "theta_mae": theta_rmse,
        "theta_bias": theta_rmse,
        "theta_corr": 0.0,
        "hydrus_theta_min": 0.38,
        "hydrus_theta_max": 0.38,
        "maizsim_theta_min": 0.38 + theta_rmse,
        "maizsim_theta_max": 0.38 + theta_rmse,
        "delta_theta_rmse": 0.015,
        "delta_theta_mae": 0.015,
        "delta_theta_bias": 0.015,
        "hydrus_wet_area_cm2": float(point_rows),
        "maizsim_wet_area_cm2": float(point_rows),
        "wet_intersection_area_cm2": float(point_rows),
        "wet_union_area_cm2": float(point_rows),
        "wet_iou": 1.0,
        "peak_delta_distance_cm": 0.0,
        "maizsim_wet_width_cm": 24.0,
        "hydrus_wet_width_cm": 24.0,
        "maizsim_wet_depth_cm": 24.0,
        "hydrus_wet_depth_cm": 24.0,
        "hydrus_reference_area_cm2": float(point_rows),
        "comparison_area_cm2": float(point_rows),
        "dropped_reference_area_cm2": 0.0,
        "comparison_point_fraction": comparison_point_fraction,
        "comparison_area_fraction": comparison_area_fraction,
        "hydrus_x_span_cm": 24.0,
        "hydrus_depth_span_cm": 24.0,
        "comparison_x_span_cm": 24.0,
        "comparison_depth_span_cm": 24.0,
    }
    if include_source_wet:
        summary["source_wet_iou"] = 1.0
        summary["hydrus_source_wet_area_cm2"] = float(point_rows)
        summary["maizsim_source_wet_area_cm2"] = float(point_rows)
        summary["source_wet_intersection_area_cm2"] = float(point_rows)
        summary["source_wet_union_area_cm2"] = float(point_rows)
        summary["hydrus_source_wet_width_cm"] = 24.0
        summary["maizsim_source_wet_width_cm"] = 24.0
        summary["hydrus_source_wet_depth_cm"] = 24.0
        summary["maizsim_source_wet_depth_cm"] = 24.0
    if include_storage:
        summary["hydrus_delta_storage_cm3"] = 0.20 * float(point_rows)
        summary["maizsim_delta_storage_cm3"] = 0.215 * float(point_rows)
        summary["delta_storage_residual_cm3"] = 0.015 * float(point_rows)
        summary["delta_storage_residual_l"] = 0.015 * float(point_rows) / 1000.0
        summary["hydrus_delta_storage_l"] = 0.20 * float(point_rows) / 1000.0
        summary["maizsim_delta_storage_l"] = 0.215 * float(point_rows) / 1000.0
        summary["delta_theta_volume_rmse"] = 0.015
    if uncertainty_fraction is not None:
        if points_include_uncertainty:
            summary["theta_uncertainty_point_count"] = float(point_rows)
            summary["theta_normalized_rmse"] = theta_rmse / 0.02
            summary["delta_theta_uncertainty_point_count"] = float(point_rows)
            summary["delta_theta_normalized_rmse"] = 0.015 / (np.sqrt(2.0) * 0.02)
        summary["theta_abs_residual_le_2sd_fraction"] = uncertainty_fraction
        summary["delta_theta_abs_residual_le_2sd_fraction"] = uncertainty_fraction
    summary_rows = [summary, dict(summary)] if duplicate_summary else [summary]
    pd.DataFrame(summary_rows).to_csv(external_dir / "case_summary.csv", index=False)
    if points is not None:
        points.to_csv(external_dir / "case_points.csv", index=False)
    _write_nonblank_png(external_dir / "case_fields.png")
    if write_manifest:
        manifest = {"case": "synthetic_same_condition"}
        if not placeholder_manifest:
            manifest = _comparison_manifest(
                case_id=name,
                soil_scale=soil_scale,
                emitter_rate_l_h=emitter_rate_l_h,
                event_duration_h=event_duration_h,
                output_time=output_time,
                event_relative_time_h=event_relative_time_h,
                calibration_data_used=calibration_data_used,
            )
        (external_dir / "case_manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
    _write_external_input_files(
        external_dir,
        point_rows=point_rows,
        event_relative_time_h=event_relative_time_h,
    )
    audit = _external_audit(
        external_dir,
        event_relative_time_h=event_relative_time_h,
    )
    if empty_audit_inputs:
        audit["inputs"] = {}
    if corrupt_audit:
        audit["artifacts"]["summary_csv"]["sha256"] = "0" * 64
    (external_dir / "case_audit.json").write_text(
        json.dumps(audit),
        encoding="utf-8",
    )
    outputs = {
        "summary_csv": str(external_dir / "case_summary.csv"),
        "points_csv": str(external_dir / "case_points.csv"),
        "figure": str(external_dir / "case_fields.png"),
        "comparison_manifest_json": str(external_dir / "case_manifest.json"),
        "audit_json": str(external_dir / "case_audit.json"),
    }
    if corrupt_outputs_index:
        other_points = external_dir / "other_points.csv"
        if (external_dir / "case_points.csv").is_file():
            other_points.write_text(
                (external_dir / "case_points.csv").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            other_points.write_text("x_cm,depth_cm\n0,0\n", encoding="utf-8")
        outputs["points_csv"] = str(other_points)
    (external_dir / "case_outputs.json").write_text(
        json.dumps(outputs),
        encoding="utf-8",
    )
    return external_dir


def _external_audit(external_dir, event_relative_time_h=2.0):
    return {
        "case_id": "synthetic_same_condition",
        "inputs": {
            "maizsim_g03": _file_audit(external_dir / "case_maizsim_g03.csv"),
            "hydrus_csv": _file_audit(external_dir / "case_hydrus.csv"),
            "maizsim_baseline_g03": _file_audit(
                external_dir / "case_maizsim_baseline_g03.csv"
            ),
            "hydrus_baseline_csv": _file_audit(
                external_dir / "case_hydrus_baseline.csv"
            ),
            "comparison_manifest": _file_audit(external_dir / "case_manifest.json"),
        },
        "raw_reference_files": [
            _raw_reference_file_record(
                external_dir / "case_hydrus.csv",
                "hydrus_event_theta_csv",
            ),
            _raw_reference_file_record(
                external_dir / "case_hydrus_baseline.csv",
                "hydrus_baseline_theta_csv",
            ),
        ],
        "selected_times": {
            "hydrus": {"selected_time_h": float(event_relative_time_h)},
            "hydrus_baseline": {"selected_time_h": 0.0},
            "maizsim": {},
            "maizsim_baseline": {},
        },
        "comparison": {"interpolation": "matplotlib.tri.LinearTriInterpolator"},
        "artifacts": {
            "summary_csv": _file_audit(external_dir / "case_summary.csv"),
            "points_csv": _file_audit(external_dir / "case_points.csv"),
            "figure": {
                **_file_audit(external_dir / "case_fields.png"),
                "nonblank": True,
                "pixel_width": 720,
                "pixel_height": 480,
                "pixel_range": 1.0,
            },
            "comparison_manifest_json": _file_audit(
                external_dir / "case_manifest.json"
            ),
        },
    }


def _write_external_input_files(external_dir, point_rows, event_relative_time_h=2.0):
    x_values = np.linspace(0.0, 24.0, point_rows)
    depth_values = np.linspace(0.0, 24.0, point_rows)
    for name, theta, time_h in (
        ("case_maizsim_g03.csv", 0.22, None),
        ("case_hydrus.csv", 0.38, event_relative_time_h),
        ("case_maizsim_baseline_g03.csv", 0.18, None),
        ("case_hydrus_baseline.csv", 0.18, 0.0),
    ):
        frame = pd.DataFrame(
            {
                "x_cm": x_values,
                "depth_cm": depth_values,
                "theta": np.full(point_rows, theta),
                "area_cm2": np.ones(point_rows),
                "axisym_volume_cm3": np.ones(point_rows),
                "theta_sd": np.full(point_rows, 0.02),
            }
        )
        if time_h is not None:
            frame["time_h"] = float(time_h)
        frame.to_csv(external_dir / name, index=False)


def _file_audit(path):
    file_path = Path(path)
    if not file_path.is_file():
        return {"path": str(file_path), "size_bytes": 0, "sha256": ""}
    return {
        "path": str(file_path),
        "size_bytes": int(file_path.stat().st_size),
        "sha256": _sha256(file_path),
    }


def _raw_reference_file_record(path, role):
    audit = _file_audit(path)
    return {
        "role": role,
        "path_or_uri": audit["path"],
        "size_bytes": audit["size_bytes"],
        "sha256": audit["sha256"],
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _external_points_frame(
    rows,
    *,
    theta_residual=0.02,
    delta_residual=0.015,
    include_source_wet=True,
    include_storage=True,
    include_uncertainty=True,
    corrupt_theta_residual=False,
):
    frame = pd.DataFrame(
        {
            "x_cm": np.linspace(0.0, 24.0, rows),
            "depth_cm": np.linspace(0.0, 24.0, rows),
            "area_cm2": np.ones(rows),
            "hydrus_theta": np.full(rows, 0.38),
            "maizsim_theta": np.full(rows, 0.38 + float(theta_residual)),
            "theta_residual": np.full(rows, float(theta_residual)),
        }
    )
    if corrupt_theta_residual and rows > 0:
        frame.loc[0, "theta_residual"] = 0.1
    frame["hydrus_wet"] = [True] * rows
    frame["maizsim_wet"] = [True] * rows
    if include_source_wet:
        frame["hydrus_source_wet"] = [True] * rows
        frame["maizsim_source_wet"] = [True] * rows
    if include_storage:
        frame["axisym_volume_cm3"] = np.ones(rows)
        frame["hydrus_delta_theta"] = np.full(rows, 0.20)
        frame["maizsim_delta_theta"] = np.full(rows, 0.20 + float(delta_residual))
        frame["delta_theta_residual"] = np.full(rows, float(delta_residual))
    if include_uncertainty:
        frame["hydrus_theta_sd"] = np.full(rows, 0.02)
        frame["hydrus_delta_theta_sd"] = np.full(rows, np.sqrt(2.0) * 0.02)
    return frame


def _single_case_thresholds():
    return {
        "external_case_count_min": 1,
        "external_soil_parameter_set_count_min": 1,
        "external_irrigation_event_setting_count_min": 1,
        "external_output_time_count_min": 1,
    }


def _diverse_external_dirs(root):
    return [
        _external_dir(
            root,
            name="loam_compare",
            soil_scale=1.0,
            emitter_rate_l_h=2.0,
        ),
        _external_dir(
            root,
            name="sand_compare",
            soil_scale=4.0,
            emitter_rate_l_h=1.0,
            output_time="2024-06-01T02:00:00",
            event_relative_time_h=2.0,
        ),
        _external_dir(
            root,
            name="clay_compare",
            soil_scale=0.2,
            emitter_rate_l_h=2.0,
            event_duration_h=4.0,
            output_time="2024-06-01T04:00:00",
            event_relative_time_h=4.0,
        ),
    ]


def _write_nonblank_png(path):
    image = np.zeros((480, 720, 3), dtype=float)
    image[:, :, 0] = np.linspace(0.0, 1.0, 720)
    image[:, :, 1] = np.linspace(1.0, 0.0, 480)[:, None]
    mpimg.imsave(path, image)


def _write_low_resolution_png(path):
    image = np.zeros((8, 8, 3), dtype=float)
    image[:, :, 0] = np.linspace(0.0, 1.0, 8)
    image[:, :, 1] = np.linspace(1.0, 0.0, 8)[:, None]
    mpimg.imsave(path, image)


def _write_blank_png(path):
    image = np.ones((480, 720, 3), dtype=float) * 0.5
    mpimg.imsave(path, image)


def _comparison_manifest(
    *,
    case_id="synthetic_same_condition",
    soil_scale=1.0,
    emitter_rate_l_h=2.0,
    event_duration_h=2.0,
    output_time="2024-06-01T00:00:00",
    event_relative_time_h=2.0,
    calibration_data_used=False,
):
    return {
        "hydrus_project": "surface_drip_reference",
        "maizsim_run": "maizsim_surface_drip_validation",
        "soil_hydraulic_parameters": {
            "theta_r": 0.05,
            "theta_s": 0.40,
            "alpha_cm_inv": 0.02,
            "n": 1.4,
            "ks_cm_h": 2.0 * soil_scale,
        },
        "initial_condition": "uniform theta=0.20",
        "emitter_rate_l_h": emitter_rate_l_h,
        "applied_volume_l": emitter_rate_l_h * event_duration_h,
        "event_duration_h": event_duration_h,
        "output_time": output_time,
        "event_relative_time_h": event_relative_time_h,
        "domain_width_cm": 10.0,
        "domain_depth_cm": 10.0,
        "drip_x_cm": 0.0,
        "drip_source_left_cm": -2.0,
        "drip_source_right_cm": 2.0,
        "drip_source_formulation": "partial-width surface flux boundary",
        "water_solver_coupling": "richards_surface_flux_boundary",
        "boundary_conditions": "closed side/free drainage bottom",
        "baseline_definition": "same setup without drip irrigation",
        "hydrus_version": "HYDRUS-2D 4.17 reference run",
        "hydrus_mesh": {
            "node_count": 25,
            "element_count": 32,
            "source": "exported HYDRUS reference mesh",
        },
        "hydrus_time_step_control": {
            "max_step_h": 0.1,
            "output_time_h": event_relative_time_h,
        },
        "maizsim_version": "MAIZSIM drip validation build",
        "maizsim_grid": {
            "node_count": 25,
            "element_count": 32,
            "source": "exported MAIZSIM validation grid",
        },
        "maizsim_time_step_control": {"water_dtmax_d": 0.005},
        "theta_units": "cm3 cm-3",
        "observation_source": "reference theta field with theta_sd columns",
        "reference_data_type": "hydrus_2d_simulation",
        "reference_identity": {
            "reference_case_id": f"{case_id}_t{event_relative_time_h:g}h",
            "dataset_title": "HYDRUS theta reference benchmark",
            "dataset_version": "validation-v1",
            "originating_institution": "MAIZSIM validation workflow",
            "data_freeze_timestamp_utc": "2026-05-27T00:00:00Z",
        },
        "reference_data_provenance": {
            "source_system": "HYDRUS-2D reference export workflow",
            "project_or_dataset_id": "surface_drip_reference",
            "export_tool_or_protocol": "versioned CSV export",
            "exported_variable": "theta water content",
            "spatial_support": "reference nodes with area_cm2 weights",
            "time_selection": "event-relative time 2.0 h",
            "preprocessing_steps": "direct reference export without calibration fitting",
        },
        "hydrus_reference_run": {
            "domain_mode": "cartesian_2d",
            "soil_model": "van Genuchten-Mualem",
            "solver_tolerances": {"water_content_tolerance": 1.0e-5},
            "mass_balance_error_percent": 0.01,
            "output_record_time_h": event_relative_time_h,
            "export_command": (
                f"hydrus-export --time {event_relative_time_h:g}h --variable theta"
            ),
        },
        "raw_reference_files": [
            {
                "role": "hydrus_event_theta_fixture",
                "path_or_uri": "memory://synthetic_surface_drip/hydrus.csv",
                "size_bytes": 128,
                "sha256": "a" * 64,
            },
            {
                "role": "hydrus_baseline_theta_fixture",
                "path_or_uri": "memory://synthetic_surface_drip/hydrus_base.csv",
                "size_bytes": 128,
                "sha256": "c" * 64,
            },
        ],
        "independence_proof": {
            "parameter_freeze_commit": "199627a4a68e464dfd7c31d2cc65f1de26b54972",
            "parameter_freeze_timestamp_utc": "2026-05-26T00:00:00Z",
            "freeze_record_sha256": "b" * 64,
            "calibration_dataset_ids": ["internal_parameter_calibration"],
            "validation_dataset_id": f"{case_id}_t{event_relative_time_h:g}h",
            "excluded_from_calibration": True,
            "case_selection_protocol": "validation case selected before comparison",
        },
        "uncertainty_basis": {
            "theta_sd_source": "reference theta_sd column",
            "uncertainty_units": "cm3 cm-3",
            "coverage_level": "one standard deviation",
        },
        "comparison_coordinate_system": "x_cm horizontal, depth_cm positive downward",
        "validation_role": "independent_validation",
        "calibration_data_used": calibration_data_used,
        "model_parameters_frozen": True,
        "calibration_note": (
            "Validation case; parameters are fixed before comparison."
        ),
    }
