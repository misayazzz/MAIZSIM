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
from da_framework.drip_external_validation_suite import (
    main,
    run_external_validation_suite,
)
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_CHECKS
from da_framework.drip_journal_readiness import REQUIRED_PRECISION_FIGURES


class DripExternalValidationSuiteTests(unittest.TestCase):
    def test_suite_runs_comparison_and_readiness_gate(self):
        with tempfile.TemporaryDirectory(prefix="codex_external_suite_") as tmp_dir:
            root = Path(tmp_dir)
            suite_path = _write_suite(root)
            output_dir = root / "out"

            report = run_external_validation_suite(
                suite_manifest=suite_path,
                output_dir=output_dir,
            )

            cases = pd.read_csv(report["cases_csv"])
            readiness_report = json.loads(
                Path(report["journal_readiness_report"]).read_text(
                    encoding="utf-8",
                )
            )
            figure_exists = Path(cases.loc[0, "figure"]).is_file()
            audit = json.loads(
                (
                    Path(cases.loc[0, "output_dir"])
                    / "loam_2lh_synthetic_audit.json"
                ).read_text(encoding="utf-8")
            )
            metric_summary_exists = Path(report["metric_summary_csv"]).is_file()
            metric_panel_exists = Path(report["metric_panel_figure"]).is_file()
            metric_summary = pd.read_csv(report["metric_summary_csv"])

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["journal_readiness_status"], "pass")
        self.assertEqual(readiness_report["overall_status"], "pass")
        self.assertEqual(cases.loc[0, "status"], "pass")
        self.assertTrue(figure_exists)
        self.assertTrue(metric_summary_exists)
        self.assertTrue(metric_panel_exists)
        self.assertIn("delta_theta_rmse", set(metric_summary["metric"]))
        self.assertIn("comparison_area_fraction", set(metric_summary["metric"]))
        self.assertIn("wet_width_abs_error_cm", cases.columns)
        self.assertIn("comparison_area_fraction", cases.columns)
        self.assertTrue(
            all(item["actual_verified"] for item in audit["raw_reference_files"])
        )
        self.assertEqual(
            {item["role"] for item in audit["raw_reference_files"]},
            {"hydrus_event_theta_csv", "hydrus_baseline_theta_csv"},
        )
        self.assertAlmostEqual(
            float(audit["selected_times"]["hydrus"]["selected_time_h"]),
            2.0,
        )

    def test_suite_records_case_failure_when_manifest_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="codex_external_suite_") as tmp_dir:
            root = Path(tmp_dir)
            suite_path = _write_suite(root, include_manifest=False)
            output_dir = root / "out"

            report = run_external_validation_suite(
                suite_manifest=suite_path,
                output_dir=output_dir,
            )

            cases = pd.read_csv(report["cases_csv"])
            readiness_report = json.loads(
                Path(report["journal_readiness_report"]).read_text(
                    encoding="utf-8",
                )
            )

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(report["journal_readiness_status"], "missing_external_evidence")
        self.assertEqual(readiness_report["overall_status"], "missing_external_evidence")
        self.assertEqual(cases.loc[0, "status"], "fail")
        self.assertIn("missing", str(cases.loc[0, "error"]))

    def test_suite_records_case_failure_when_measured_reference_lacks_theta_sd(self):
        with tempfile.TemporaryDirectory(prefix="codex_external_suite_") as tmp_dir:
            root = Path(tmp_dir)
            suite_path = _write_suite(
                root,
                reference_data_type="measured_2d_theta_field",
                include_theta_sd=False,
            )
            output_dir = root / "out"

            report = run_external_validation_suite(
                suite_manifest=suite_path,
                output_dir=output_dir,
            )

            cases = pd.read_csv(report["cases_csv"])
            readiness_report = json.loads(
                Path(report["journal_readiness_report"]).read_text(
                    encoding="utf-8",
                )
            )

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(readiness_report["overall_status"], "missing_external_evidence")
        self.assertEqual(cases.loc[0, "status"], "fail")
        self.assertIn("theta_sd", str(cases.loc[0, "error"]))

    def test_suite_single_case_fails_default_readiness_gate_without_overrides(self):
        with tempfile.TemporaryDirectory(prefix="codex_external_suite_") as tmp_dir:
            root = Path(tmp_dir)
            suite_path = _write_suite(root, include_readiness_thresholds=False)
            output_dir = root / "out"

            report = run_external_validation_suite(
                suite_manifest=suite_path,
                output_dir=output_dir,
            )

            cases = pd.read_csv(report["cases_csv"])
            readiness_report = json.loads(
                Path(report["journal_readiness_report"]).read_text(
                    encoding="utf-8",
                )
            )

        self.assertEqual(report["overall_status"], "fail")
        self.assertEqual(report["journal_readiness_status"], "fail")
        self.assertEqual(readiness_report["overall_status"], "fail")
        self.assertEqual(cases.loc[0, "status"], "pass")

    def test_cli_writes_suite_report_and_returns_zero_for_passing_suite(self):
        with tempfile.TemporaryDirectory(prefix="codex_external_suite_") as tmp_dir:
            root = Path(tmp_dir)
            suite_path = _write_suite(root)
            output_dir = root / "out"

            exit_code = main(
                [
                    "--suite-manifest",
                    str(suite_path),
                    "--output-dir",
                    str(output_dir),
                ]
            )
            report = json.loads(
                (output_dir / "external_validation_suite_report.json").read_text(
                    encoding="utf-8",
                )
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["overall_status"], "pass")


def _write_suite(
    root,
    *,
    include_manifest=True,
    include_readiness_thresholds=True,
    reference_data_type="hydrus_2d_simulation",
    include_theta_sd=True,
):
    precision_dir = _precision_dir(root)
    data_dir = root / "data"
    data_dir.mkdir()
    case_specs = _suite_case_specs()
    if not include_readiness_thresholds:
        case_specs = case_specs[:1]
    comparisons = []
    for spec in case_specs:
        case_dir = data_dir / spec["name"]
        case_dir.mkdir()
        hydrus_path = case_dir / "hydrus.csv"
        hydrus_base_path = case_dir / "hydrus_base.csv"
        maizsim_path = case_dir / "maizsim.G03"
        maizsim_base_path = case_dir / "maizsim_base.G03"
        manifest_path = case_dir / "comparison_manifest.json"
        _write_hydrus_csv(
            hydrus_path,
            0.30,
            time_h=spec["event_relative_time_h"],
            include_theta_sd=include_theta_sd,
        )
        _write_hydrus_csv(
            hydrus_base_path,
            0.20,
            time_h=0.0,
            include_theta_sd=include_theta_sd,
        )
        _write_g03(maizsim_path, 0.295)
        _write_g03(maizsim_base_path, 0.20)
        if include_manifest:
            manifest = _comparison_manifest(
                hydrus_path,
                hydrus_base_path,
                case_id=spec["name"],
                soil_scale=spec["soil_scale"],
                emitter_rate_l_h=spec["emitter_rate_l_h"],
                event_duration_h=spec["event_duration_h"],
                output_time=spec["output_time"],
                event_relative_time_h=spec["event_relative_time_h"],
            )
            if reference_data_type == "measured_2d_theta_field":
                manifest["reference_data_type"] = "measured_2d_theta_field"
                manifest.pop("hydrus_reference_run")
                manifest["measured_reference_metadata"] = _measured_reference_metadata()
            elif reference_data_type != "hydrus_2d_simulation":
                manifest["reference_data_type"] = reference_data_type
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
        comparisons.append(
            {
                "name": spec["name"],
                "maizsim_g03": f"data/{spec['name']}/maizsim.G03",
                "hydrus_csv": f"data/{spec['name']}/hydrus.csv",
                "maizsim_baseline_g03": f"data/{spec['name']}/maizsim_base.G03",
                "hydrus_baseline_csv": f"data/{spec['name']}/hydrus_base.csv",
                "comparison_manifest": (
                    f"data/{spec['name']}/comparison_manifest.json"
                    if include_manifest
                    else ""
                ),
                "date": "2024-06-01",
                "wet_delta_threshold": 0.05,
            }
        )
    suite_path = root / "suite.json"
    suite = {
        "suite_name": "synthetic_external_suite",
        "precision_dir": "precision",
        "comparisons": comparisons,
    }
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    return suite_path


def _suite_case_specs():
    return [
        {
            "name": "loam_2lh_synthetic",
            "soil_scale": 1.0,
            "emitter_rate_l_h": 2.0,
            "event_duration_h": 2.0,
            "output_time": "2024-06-01T02:00:00",
            "event_relative_time_h": 2.0,
        },
        {
            "name": "sand_1lh_synthetic",
            "soil_scale": 4.0,
            "emitter_rate_l_h": 1.0,
            "event_duration_h": 2.0,
            "output_time": "2024-06-01T02:00:00",
            "event_relative_time_h": 2.0,
        },
        {
            "name": "clay_2lh_4h_synthetic",
            "soil_scale": 0.2,
            "emitter_rate_l_h": 2.0,
            "event_duration_h": 4.0,
            "output_time": "2024-06-01T04:00:00",
            "event_relative_time_h": 4.0,
        },
    ]


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


def _write_nonblank_png(path):
    image = np.zeros((480, 720, 3), dtype=float)
    image[:, :, 0] = np.linspace(0.0, 1.0, 720)
    image[:, :, 1] = np.linspace(1.0, 0.0, 480)[:, None]
    mpimg.imsave(path, image)


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


def _fixture_grid():
    x_values = np.linspace(0.0, 24.0, 5)
    depth_values = np.linspace(0.0, 24.0, 5)
    x_grid, depth_grid = np.meshgrid(x_values, depth_values)
    return x_grid.ravel(), depth_grid.ravel()


def _theta_values(theta):
    if np.isscalar(theta):
        return np.full(25, float(theta))
    values = np.asarray(theta, dtype=float)
    if values.size != 25:
        raise ValueError("Synthetic field fixtures must contain 25 theta values.")
    return values


def _write_hydrus_csv(path, theta, time_h=None, include_theta_sd=True):
    x_values, depth_values = _fixture_grid()
    theta_values = _theta_values(theta)
    frame = pd.DataFrame(
        {
            "x_cm": x_values,
            "depth_cm": depth_values,
            "theta": theta_values,
            "area_cm2": np.ones(25),
            "axisym_volume_cm3": np.full(25, 10.0),
        }
    )
    if include_theta_sd:
        frame["theta_sd"] = np.full(25, 0.02)
    if time_h is not None:
        frame["time_h"] = float(time_h)
    frame.to_csv(path, index=False)


def _write_g03(path, theta):
    x_values, depth_values = _fixture_grid()
    theta_values = _theta_values(theta)
    rows = [
        ("2024-06-01", x, 100.0 - depth, value, 1.0)
        for x, depth, value in zip(x_values, depth_values, theta_values)
    ]
    pd.DataFrame(rows, columns=["Date", "X", "Y", "thNew", "Area"]).to_csv(
        path,
        index=False,
    )


def _comparison_manifest(
    raw_reference_event_path=None,
    raw_reference_baseline_path=None,
    *,
    case_id="synthetic_surface_drip",
    soil_scale=1.0,
    emitter_rate_l_h=2.0,
    event_duration_h=2.0,
    output_time="2024-06-01T00:00:00",
    event_relative_time_h=2.0,
):
    raw_reference_files = [
        _raw_reference_file_record(
            raw_reference_event_path,
            "hydrus_event_theta_csv",
            "hydrus.csv",
        ),
        _raw_reference_file_record(
            raw_reference_baseline_path,
            "hydrus_baseline_theta_csv",
            "hydrus_base.csv",
        ),
    ]
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
        "domain_width_cm": 24.0,
        "domain_depth_cm": 24.0,
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
            "time_selection": f"event-relative time {event_relative_time_h:g} h",
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
        "raw_reference_files": raw_reference_files,
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
        "calibration_data_used": False,
        "model_parameters_frozen": True,
        "calibration_note": (
            "Validation case; parameters are fixed before comparison."
        ),
    }


def _raw_reference_file_record(path, role, fallback_name):
    if path is None:
        return {
            "role": role,
            "path_or_uri": f"memory://synthetic_surface_drip/{fallback_name}",
            "size_bytes": 128,
            "sha256": "a" * 64,
        }
    file_path = Path(path)
    payload = file_path.read_bytes()
    return {
        "role": role,
        "path_or_uri": file_path.name,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _measured_reference_metadata():
    return {
        "instrument_method": "2D neutron radiography fixture",
        "instrument_ids": ["NR-001"],
        "sensor_calibration_id": "theta-cal-001",
        "theta_conversion_equation": "theta = a * attenuation + b",
        "spatial_resolution_cm": 1.0,
        "registration_method": "rigid control-point registration",
        "registration_error_cm": 0.2,
        "qaqc_flags": {"bad_pixels_removed": True},
        "uncertainty_model": {"theta_sd_column": "theta_sd"},
        "replicate_count": 2,
    }


if __name__ == "__main__":
    unittest.main()
