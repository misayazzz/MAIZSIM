"""Compare MAIZSIM 2D theta fields against exported HYDRUS 2D fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd


plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
    }
)


@dataclass
class FieldComparison:
    """HYDRUS-vs-MAIZSIM comparison metrics and point-level values."""

    metrics: dict
    points: pd.DataFrame


REQUIRED_COMPARISON_MANIFEST_KEYS = (
    "hydrus_project",
    "maizsim_run",
    "soil_hydraulic_parameters",
    "initial_condition",
    "emitter_rate_l_h",
    "applied_volume_l",
    "event_duration_h",
    "output_time",
    "event_relative_time_h",
    "domain_width_cm",
    "domain_depth_cm",
    "drip_x_cm",
    "drip_source_left_cm",
    "drip_source_right_cm",
    "drip_source_formulation",
    "water_solver_coupling",
    "boundary_conditions",
    "baseline_definition",
    "hydrus_version",
    "hydrus_mesh",
    "hydrus_time_step_control",
    "maizsim_version",
    "maizsim_grid",
    "maizsim_time_step_control",
    "theta_units",
    "observation_source",
    "reference_data_type",
    "reference_identity",
    "reference_data_provenance",
    "raw_reference_files",
    "independence_proof",
    "uncertainty_basis",
    "comparison_coordinate_system",
    "validation_role",
    "calibration_data_used",
    "model_parameters_frozen",
    "calibration_note",
)

MANIFEST_PLACEHOLDER_PATTERNS = (
    "todo",
    "tbd",
    "placeholder",
    "path/to",
    "describe ",
    "record ",
    "use the same",
)

ACCEPTED_WATER_SOLVER_COUPLINGS = {
    "richards_surface_flux_boundary",
    "richards_pressure_limited_surface_boundary",
    "richards_solver_coupled_source",
}

ACCEPTED_REFERENCE_DATA_TYPES = {
    "hydrus_2d_simulation",
    "hydrus_2d_3d_simulation",
    "measured_2d_theta_field",
}

REQUIRED_REFERENCE_PROVENANCE_KEYS = (
    "source_system",
    "project_or_dataset_id",
    "export_tool_or_protocol",
    "exported_variable",
    "spatial_support",
    "time_selection",
    "preprocessing_steps",
)

REQUIRED_UNCERTAINTY_BASIS_KEYS = (
    "theta_sd_source",
    "uncertainty_units",
    "coverage_level",
)

REQUIRED_REFERENCE_IDENTITY_KEYS = (
    "reference_case_id",
    "dataset_title",
    "dataset_version",
    "originating_institution",
    "data_freeze_timestamp_utc",
)

REQUIRED_INDEPENDENCE_PROOF_KEYS = (
    "parameter_freeze_commit",
    "parameter_freeze_timestamp_utc",
    "freeze_record_sha256",
    "calibration_dataset_ids",
    "validation_dataset_id",
    "excluded_from_calibration",
    "case_selection_protocol",
)

REQUIRED_RAW_REFERENCE_FILE_KEYS = (
    "role",
    "path_or_uri",
    "size_bytes",
    "sha256",
)

RAW_REFERENCE_EVENT_ROLE_TOKENS = (
    "event",
    "output",
    "post",
    "irrigated",
)

RAW_REFERENCE_BASELINE_ROLE_TOKENS = (
    "baseline",
    "initial",
    "pre_event",
    "pre-event",
    "no_drip",
    "without_drip",
)

REQUIRED_HYDRUS_REFERENCE_RUN_KEYS = (
    "domain_mode",
    "soil_model",
    "solver_tolerances",
    "mass_balance_error_percent",
    "output_record_time_h",
    "export_command",
)

REQUIRED_MEASURED_REFERENCE_METADATA_KEYS = (
    "instrument_method",
    "instrument_ids",
    "sensor_calibration_id",
    "theta_conversion_equation",
    "spatial_resolution_cm",
    "registration_method",
    "registration_error_cm",
    "qaqc_flags",
    "uncertainty_model",
    "replicate_count",
)

ACCEPTED_HYDRUS_DOMAIN_MODES = {
    "cartesian_2d",
    "planar_2d",
    "axisymmetric_2d",
    "2d_cartesian",
    "2d_axisymmetric",
}


def read_hydrus_theta_csv(path):
    """Read a HYDRUS-exported theta field from a CSV file.

    Required columns are x position, depth, and water content. Accepted names are
    intentionally broad so exports from spreadsheets or HYDRUS post-processing
    scripts can be used without manual renaming.
    """
    output_path = Path(path)
    frame = _read_csv(output_path)
    x_col = _require_column(frame, ("x_cm", "x", "xcoord", "xcoordinate"), output_path)
    depth_col = _require_column(
        frame,
        ("depth_cm", "depth", "z_cm", "z", "depthbelowsoil"),
        output_path,
    )
    theta_col = _require_column(
        frame,
        ("theta", "theta_hydrus", "th", "water_content", "swc"),
        output_path,
    )
    area_col = _optional_column(frame, ("area_cm2", "area", "cell_area", "weight"))
    volume_col = _optional_column(
        frame,
        ("axisym_volume_cm3", "volume_cm3", "node_volume_cm3"),
    )
    theta_sd_col = _optional_column(
        frame,
        ("theta_sd", "theta_std", "theta_stdev", "theta_uncertainty", "swc_sd"),
    )

    result = pd.DataFrame(
        {
            "x_cm": _numeric(frame[x_col], x_col, output_path),
            "depth_cm": _numeric(frame[depth_col], depth_col, output_path),
            "theta": _numeric(frame[theta_col], theta_col, output_path),
        }
    )
    if area_col is None:
        result["area_cm2"] = 1.0
    else:
        result["area_cm2"] = _numeric(frame[area_col], area_col, output_path)
    if volume_col is not None:
        result["axisym_volume_cm3"] = _numeric(
            frame[volume_col],
            volume_col,
            output_path,
        )
    if theta_sd_col is not None:
        result["theta_sd"] = _numeric(frame[theta_sd_col], theta_sd_col, output_path)
    time_col = _optional_column(frame, ("time_h", "time", "t_h"))
    if time_col is not None:
        times = _numeric(frame[time_col], time_col, output_path)
        if times.nunique() != 1:
            raise ValueError(
                f"HYDRUS theta field {output_path} contains multiple time "
                "values; export one event-relative time per comparison CSV."
            )
        result.attrs["selected_time_h"] = float(times.iloc[0])
    _validate_field(result, output_path)
    return result


def read_comparison_manifest(path):
    """Read and validate same-condition metadata for a HYDRUS comparison."""
    input_path = Path(path)
    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Comparison manifest must be a JSON object: {input_path}.")
    missing = [
        key
        for key in REQUIRED_COMPARISON_MANIFEST_KEYS
        if key not in manifest or manifest[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {input_path} is missing required keys: {missing}."
        )
    if str(manifest["validation_role"]).casefold() != "independent_validation":
        raise ValueError(
            "Comparison manifest validation_role must be "
            "'independent_validation'."
        )
    if manifest["calibration_data_used"] is not False:
        raise ValueError(
            "Comparison manifest calibration_data_used must be false for a "
            "journal-readiness validation case."
        )
    if manifest["model_parameters_frozen"] is not True:
        raise ValueError(
            "Comparison manifest model_parameters_frozen must be true before "
            "the case can be treated as independent validation."
        )
    _validate_event_time_manifest(manifest, input_path)
    _validate_reproducibility_manifest(manifest, input_path)
    _validate_reference_provenance_manifest(manifest, input_path)
    _validate_solver_coupling_manifest(manifest, input_path)
    _validate_drip_source_manifest(manifest, input_path)
    return manifest


def read_maizsim_g03_theta(path, date=None, date_time=None):
    """Read a MAIZSIM G03 theta field and convert y to depth from surface."""
    output_path = Path(path)
    frame = _read_csv(output_path)
    if date_time is not None:
        frame = _nearest_date_time_frame(frame, date_time, output_path)
    elif date is not None:
        frame = _nearest_date_frame(frame, date, output_path)
    elif "Date" in frame.columns and frame["Date"].nunique() > 1:
        raise ValueError(f"Multiple G03 dates in {output_path}; pass a date.")
    _validate_single_maizsim_time(frame, output_path)

    x_col = _require_column(frame, ("x", "x_cm"), output_path)
    y_col = _require_column(frame, ("y", "y_cm"), output_path)
    theta_col = _require_column(frame, ("thnew", "theta", "swc"), output_path)
    area_col = _require_column(frame, ("area", "area_cm2"), output_path)

    x_values = _numeric(frame[x_col], x_col, output_path)
    y_values = _numeric(frame[y_col], y_col, output_path)
    surface_y = float(y_values.max())
    result = pd.DataFrame(
        {
            "x_cm": x_values,
            "depth_cm": surface_y - y_values,
            "theta": _numeric(frame[theta_col], theta_col, output_path),
            "area_cm2": _numeric(frame[area_col], area_col, output_path),
        }
    )
    date_col = _optional_column(frame, ("date",))
    if date_col is not None and frame[date_col].nunique() == 1:
        result.attrs["selected_date"] = str(frame[date_col].iloc[0])
    date_time_col = _optional_column(
        frame,
        ("date_time", "datetime", "time", "time_h"),
    )
    if date_time_col is not None and frame[date_time_col].nunique() == 1:
        value = pd.to_numeric(pd.Series([frame[date_time_col].iloc[0]])).iloc[0]
        result.attrs["selected_date_time"] = float(value)
    _validate_field(result, output_path)
    return result


def compare_theta_fields(
    maizsim,
    hydrus,
    *,
    maizsim_baseline=None,
    hydrus_baseline=None,
    wet_delta_threshold=0.005,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    """Compare MAIZSIM theta against HYDRUS theta on HYDRUS reference points."""
    hydrus_points = _standard_field(hydrus, "hydrus")
    maizsim_field = _standard_field(maizsim, "maizsim")
    points = hydrus_points.copy()
    points = points.rename(
        columns={"theta": "hydrus_theta", "theta_sd": "hydrus_theta_sd"}
    )
    points["maizsim_theta"] = _interpolate_to_points(maizsim_field, points)
    points = points[np.isfinite(points["maizsim_theta"])].copy()
    if points.empty:
        raise ValueError("No overlapping HYDRUS and MAIZSIM theta points.")

    points["theta_residual"] = points["maizsim_theta"] - points["hydrus_theta"]
    if maizsim_baseline is not None and hydrus_baseline is not None:
        maizsim_base = _standard_field(maizsim_baseline, "maizsim_baseline")
        hydrus_base = _standard_field(hydrus_baseline, "hydrus_baseline")
        points["maizsim_theta_base"] = _interpolate_to_points(maizsim_base, points)
        points["hydrus_theta_base"] = _interpolate_to_points(hydrus_base, points)
        points = points[
            np.isfinite(points["maizsim_theta_base"])
            & np.isfinite(points["hydrus_theta_base"])
        ].copy()
        if "theta_sd" in hydrus_base.columns and "hydrus_theta_sd" in points.columns:
            points["hydrus_theta_base_sd"] = _interpolate_column_to_points(
                hydrus_base,
                points,
                "theta_sd",
            )
            points["hydrus_delta_theta_sd"] = np.sqrt(
                points["hydrus_theta_sd"] ** 2 + points["hydrus_theta_base_sd"] ** 2
            )
        points["maizsim_delta_theta"] = (
            points["maizsim_theta"] - points["maizsim_theta_base"]
        )
        points["hydrus_delta_theta"] = (
            points["hydrus_theta"] - points["hydrus_theta_base"]
        )
        points["delta_theta_residual"] = (
            points["maizsim_delta_theta"] - points["hydrus_delta_theta"]
        )

    metrics = _field_metrics(points)
    if "delta_theta_residual" in points.columns:
        metrics.update(
            _delta_metrics(
                points,
                wet_delta_threshold,
                drip_x_cm=drip_x_cm,
                drip_source_left_cm=drip_source_left_cm,
                drip_source_right_cm=drip_source_right_cm,
            )
        )
    metrics.update(_coverage_metrics(hydrus_points, maizsim_field, points))
    return FieldComparison(metrics=metrics, points=points)


def plot_comparison(
    comparison,
    path,
    *,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    """Plot HYDRUS, MAIZSIM, and residual fields on HYDRUS reference points."""
    points = comparison.points
    if "hydrus_delta_theta" in points.columns:
        wet_delta_threshold = comparison.metrics.get("wet_delta_threshold")
        columns = (
            ("hydrus_delta_theta", "HYDRUS delta theta"),
            ("maizsim_delta_theta", "MAIZSIM delta theta"),
            ("delta_theta_residual", "MAIZSIM - HYDRUS"),
        )
        wet_limit = max(
            float(points["hydrus_delta_theta"].max()),
            float(points["maizsim_delta_theta"].max()),
            0.001,
        )
        resid_limit = max(
            abs(float(points["delta_theta_residual"].min())),
            abs(float(points["delta_theta_residual"].max())),
            0.001,
        )
        cmaps = ("YlGnBu", "YlGnBu", "RdBu_r")
        ranges = ((0.0, wet_limit), (0.0, wet_limit), (-resid_limit, resid_limit))
    else:
        wet_delta_threshold = None
        columns = (
            ("hydrus_theta", "HYDRUS theta"),
            ("maizsim_theta", "MAIZSIM theta"),
            ("theta_residual", "MAIZSIM - HYDRUS"),
        )
        theta_min = float(points[["hydrus_theta", "maizsim_theta"]].min().min())
        theta_max = float(points[["hydrus_theta", "maizsim_theta"]].max().max())
        resid_limit = max(
            abs(float(points["theta_residual"].min())),
            abs(float(points["theta_residual"].max())),
            0.001,
        )
        cmaps = ("viridis", "viridis", "RdBu_r")
        ranges = (
            (theta_min, theta_max),
            (theta_min, theta_max),
            (-resid_limit, resid_limit),
        )

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(7.2, 2.45),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    for ax, (column, title), cmap, (vmin, vmax) in zip(axes, columns, cmaps, ranges):
        contour = _tri_contour(ax, points, column, cmap=cmap, vmin=vmin, vmax=vmax)
        _annotate_drip_source(
            ax,
            points,
            drip_x_cm=drip_x_cm,
            drip_source_left_cm=drip_source_left_cm,
            drip_source_right_cm=drip_source_right_cm,
        )
        if wet_delta_threshold is not None and column != "delta_theta_residual":
            _annotate_wet_front(ax, points, column, wet_delta_threshold)
        ax.set_title(title, fontsize=7, pad=2)
        ax.set_xlabel("x (cm)")
        fig.colorbar(contour, ax=ax, shrink=0.78, pad=0.015)
    axes[0].set_ylabel("Depth (cm)")
    fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def write_comparison_outputs(
    comparison,
    output_dir,
    prefix="hydrus_2d_comparison",
    *,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
    comparison_manifest=None,
    audit_context=None,
):
    """Write summary CSV, point CSV, JSON index, and a comparison figure."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary_path = output_path / f"{prefix}_summary.csv"
    points_path = output_path / f"{prefix}_points.csv"
    figure_path = output_path / f"{prefix}_fields.png"
    index_path = output_path / f"{prefix}_outputs.json"
    manifest_path = output_path / f"{prefix}_manifest.json"
    audit_path = output_path / f"{prefix}_audit.json"

    pd.DataFrame([comparison.metrics]).to_csv(summary_path, index=False)
    comparison.points.to_csv(points_path, index=False)
    plot_comparison(
        comparison,
        figure_path,
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
    )
    outputs = {
        "summary_csv": str(summary_path),
        "points_csv": str(points_path),
        "figure": str(figure_path),
    }
    if comparison_manifest is not None:
        manifest_path.write_text(
            json.dumps(comparison_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        outputs["comparison_manifest_json"] = str(manifest_path)
    audit = _comparison_audit(
        outputs,
        audit_context=audit_context,
        wet_delta_threshold=comparison.metrics.get("wet_delta_threshold"),
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
    )
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    outputs["audit_json"] = str(audit_path)
    index_path.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    return outputs


def main(arguments=None):
    """Command-line entry point for HYDRUS 2D field comparison."""
    args = _parse_args(arguments)
    manifest = (
        read_comparison_manifest(args.comparison_manifest)
        if args.comparison_manifest
        else None
    )
    hydrus = read_hydrus_theta_csv(args.hydrus_csv)
    maizsim = read_maizsim_g03_theta(
        args.maizsim_g03,
        args.date,
        args.maizsim_date_time,
    )
    hydrus_baseline = (
        read_hydrus_theta_csv(args.hydrus_baseline_csv)
        if args.hydrus_baseline_csv
        else None
    )
    _validate_reference_time_matches_manifest(manifest, hydrus, args.hydrus_csv)
    _validate_reference_uncertainty_matches_manifest(manifest, hydrus, args.hydrus_csv)
    _validate_reference_uncertainty_matches_manifest(
        manifest,
        hydrus_baseline,
        args.hydrus_baseline_csv,
    )
    maizsim_baseline = (
        read_maizsim_g03_theta(
            args.maizsim_baseline_g03,
            args.date,
            args.maizsim_date_time,
        )
        if args.maizsim_baseline_g03
        else None
    )
    if (hydrus_baseline is None) != (maizsim_baseline is None):
        raise ValueError(
            "Both HYDRUS and MAIZSIM baseline fields are required "
            "for delta comparison."
        )
    drip_x_cm = _arg_or_manifest(args.drip_x_cm, manifest, "drip_x_cm")
    drip_source_left_cm = _arg_or_manifest(
        args.drip_source_left_cm,
        manifest,
        "drip_source_left_cm",
    )
    drip_source_right_cm = _arg_or_manifest(
        args.drip_source_right_cm,
        manifest,
        "drip_source_right_cm",
    )
    _validate_drip_annotation_args(drip_source_left_cm, drip_source_right_cm)
    comparison = compare_theta_fields(
        maizsim,
        hydrus,
        maizsim_baseline=maizsim_baseline,
        hydrus_baseline=hydrus_baseline,
        wet_delta_threshold=args.wet_delta_threshold,
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
    )
    audit_context = {
        "case_id": args.prefix,
        "input_files": {
            "maizsim_g03": _file_audit(args.maizsim_g03),
            "hydrus_csv": _file_audit(args.hydrus_csv),
            "maizsim_baseline_g03": _file_audit(args.maizsim_baseline_g03),
            "hydrus_baseline_csv": _file_audit(args.hydrus_baseline_csv),
            "comparison_manifest": _file_audit(args.comparison_manifest),
        },
        "selected_times": {
            "maizsim": _frame_time_attrs(maizsim),
            "maizsim_baseline": _frame_time_attrs(maizsim_baseline),
            "hydrus": _frame_time_attrs(hydrus),
            "hydrus_baseline": _frame_time_attrs(hydrus_baseline),
        },
        "parameters": {
            "date": args.date,
            "maizsim_date_time": args.maizsim_date_time,
            "wet_delta_threshold": args.wet_delta_threshold,
            "interpolation": "matplotlib.tri.LinearTriInterpolator",
        },
    }
    if manifest is not None:
        audit_context["raw_reference_files"] = _raw_reference_file_audits(manifest)
    outputs = write_comparison_outputs(
        comparison,
        args.output_dir,
        args.prefix,
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
        comparison_manifest=manifest,
        audit_context=audit_context,
    )
    if arguments is None:
        print(json.dumps(outputs, indent=2))
    return 0


def _comparison_audit(
    outputs,
    *,
    audit_context=None,
    wet_delta_threshold=None,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    audit_context = {} if audit_context is None else dict(audit_context)
    artifact_audits = {
        name: _file_audit(path)
        for name, path in outputs.items()
        if name != "audit_json"
    }
    figure_path = outputs.get("figure")
    if figure_path:
        artifact_audits["figure"].update(_figure_audit(figure_path))
    return {
        "case_id": audit_context.get("case_id"),
        "inputs": audit_context.get("input_files", {}),
        "raw_reference_files": audit_context.get("raw_reference_files", []),
        "selected_times": audit_context.get("selected_times", {}),
        "parameters": audit_context.get("parameters", {}),
        "comparison": {
            "wet_delta_threshold": wet_delta_threshold,
            "drip_x_cm": drip_x_cm,
            "drip_source_left_cm": drip_source_left_cm,
            "drip_source_right_cm": drip_source_right_cm,
            "interpolation": "matplotlib.tri.LinearTriInterpolator",
        },
        "artifacts": artifact_audits,
    }


def _raw_reference_file_audits(manifest):
    records = []
    for item in manifest.get("raw_reference_files", []):
        record = {
            "role": item.get("role"),
            "path_or_uri": item.get("path_or_uri"),
            "size_bytes": item.get("size_bytes"),
            "sha256": item.get("sha256"),
        }
        local_path = _local_raw_reference_path(item.get("path_or_uri"), Path.cwd())
        if local_path is not None and local_path.is_file():
            actual = _file_audit(local_path)
            record["actual_size_bytes"] = actual["size_bytes"]
            record["actual_sha256"] = actual["sha256"]
            record["actual_verified"] = (
                str(record["sha256"]).strip().casefold() == actual["sha256"]
                and int(record["size_bytes"]) == int(actual["size_bytes"])
            )
        records.append(record)
    return records


def _validate_reference_time_matches_manifest(manifest, reference, source):
    if manifest is None or reference is None:
        return
    selected_time = reference.attrs.get("selected_time_h")
    if selected_time is None:
        return
    event_time = float(manifest["event_relative_time_h"])
    if not np.isclose(float(selected_time), event_time, rtol=0.0, atol=1.0e-9):
        raise ValueError(
            f"Reference theta field {source} selected_time_h={selected_time} "
            "must match comparison manifest event_relative_time_h="
            f"{event_time}."
        )


def _validate_reference_uncertainty_matches_manifest(manifest, reference, source):
    if manifest is None or reference is None:
        return
    reference_type = str(manifest.get("reference_data_type", "")).strip().casefold()
    if reference_type != "measured_2d_theta_field":
        return
    if "theta_sd" not in reference.columns:
        raise ValueError(
            "Measured 2D reference field "
            f"{source} must include a positive theta_sd column so uncertainty "
            "coverage metrics can be independently recomputed."
        )
    uncertainty = reference["theta_sd"].to_numpy(dtype=float)
    if not np.isfinite(uncertainty).all() or (uncertainty <= 0.0).any():
        raise ValueError(
            "Measured 2D reference field "
            f"{source} must include finite positive theta_sd values."
        )


def _file_audit(path):
    if path in (None, ""):
        return None
    file_path = Path(path)
    return {
        "path": str(file_path),
        "size_bytes": int(file_path.stat().st_size),
        "sha256": _sha256(file_path),
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _figure_audit(path):
    try:
        image = plt.imread(path)
        return {
            "pixel_height": int(image.shape[0]),
            "pixel_width": int(image.shape[1]),
            "nonblank": bool(float(np.nanstd(image[..., :3])) > 0.0),
        }
    except Exception as exc:
        return {
            "pixel_height": 0,
            "pixel_width": 0,
            "nonblank": False,
            "error": str(exc),
        }


def _frame_time_attrs(frame):
    if frame is None:
        return {}
    return {
        key: value
        for key, value in frame.attrs.items()
        if key in ("selected_date", "selected_date_time", "selected_time_h")
    }


def _field_metrics(points):
    weights = _weights(points)
    residual = points["theta_residual"].to_numpy(dtype=float)
    hydrus_theta = points["hydrus_theta"].to_numpy(dtype=float)
    maizsim_theta = points["maizsim_theta"].to_numpy(dtype=float)
    metrics = {
        "point_count": float(len(points)),
        "theta_mae": _weighted_mean(np.abs(residual), weights),
        "theta_rmse": float(np.sqrt(_weighted_mean(residual * residual, weights))),
        "theta_bias": _weighted_mean(residual, weights),
        "theta_corr": _correlation(hydrus_theta, maizsim_theta),
        "hydrus_theta_min": float(np.min(hydrus_theta)),
        "hydrus_theta_max": float(np.max(hydrus_theta)),
        "maizsim_theta_min": float(np.min(maizsim_theta)),
        "maizsim_theta_max": float(np.max(maizsim_theta)),
    }
    if "hydrus_theta_sd" in points.columns:
        metrics.update(
            _uncertainty_metrics(
                points,
                residual_column="theta_residual",
                sd_column="hydrus_theta_sd",
                prefix="theta",
            )
        )
    return metrics


def _delta_metrics(
    points,
    threshold,
    *,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    weights = _weights(points)
    residual = points["delta_theta_residual"].to_numpy(dtype=float)
    hydrus_delta = points["hydrus_delta_theta"].to_numpy(dtype=float)
    maizsim_delta = points["maizsim_delta_theta"].to_numpy(dtype=float)
    hydrus_wet = hydrus_delta >= float(threshold)
    maizsim_wet = maizsim_delta >= float(threshold)
    points["hydrus_wet"] = hydrus_wet
    points["maizsim_wet"] = maizsim_wet
    points["hydrus_source_wet"] = False
    points["maizsim_source_wet"] = False
    intersection = hydrus_wet & maizsim_wet
    union = hydrus_wet | maizsim_wet
    union_area = float(weights[union].sum())
    metrics = {
        "delta_theta_mae": _weighted_mean(np.abs(residual), weights),
        "delta_theta_rmse": float(np.sqrt(_weighted_mean(residual * residual, weights))),
        "delta_theta_bias": _weighted_mean(residual, weights),
        "wet_delta_threshold": float(threshold),
        "hydrus_wet_area_cm2": float(weights[hydrus_wet].sum()),
        "maizsim_wet_area_cm2": float(weights[maizsim_wet].sum()),
        "wet_intersection_area_cm2": float(weights[intersection].sum()),
        "wet_union_area_cm2": union_area,
        "wet_iou": float(weights[intersection].sum() / union_area)
        if union_area > 0.0
        else 0.0,
        "hydrus_wet_width_cm": _span(points.loc[hydrus_wet, "x_cm"]),
        "maizsim_wet_width_cm": _span(points.loc[maizsim_wet, "x_cm"]),
        "hydrus_wet_depth_cm": _max_or_zero(points.loc[hydrus_wet, "depth_cm"]),
        "maizsim_wet_depth_cm": _max_or_zero(points.loc[maizsim_wet, "depth_cm"]),
        "peak_delta_distance_cm": _peak_distance(points),
    }
    volume_weights = _volume_weights(points)
    if volume_weights is not None:
        hydrus_storage_cm3 = float(np.sum(hydrus_delta * volume_weights))
        maizsim_storage_cm3 = float(np.sum(maizsim_delta * volume_weights))
        metrics.update(
            {
                "hydrus_delta_storage_cm3": hydrus_storage_cm3,
                "maizsim_delta_storage_cm3": maizsim_storage_cm3,
                "delta_storage_residual_cm3": (
                    maizsim_storage_cm3 - hydrus_storage_cm3
                ),
                "hydrus_delta_storage_l": hydrus_storage_cm3 / 1000.0,
                "maizsim_delta_storage_l": maizsim_storage_cm3 / 1000.0,
                "delta_storage_residual_l": (
                    maizsim_storage_cm3 - hydrus_storage_cm3
                )
                / 1000.0,
                "delta_theta_volume_rmse": float(
                    np.sqrt(_weighted_mean(residual * residual, volume_weights))
                ),
            }
        )
    if drip_x_cm is not None:
        hydrus_source_wet = _source_connected_wet_mask(
            points,
            hydrus_wet,
            drip_x_cm=drip_x_cm,
            drip_source_left_cm=drip_source_left_cm,
            drip_source_right_cm=drip_source_right_cm,
        )
        maizsim_source_wet = _source_connected_wet_mask(
            points,
            maizsim_wet,
            drip_x_cm=drip_x_cm,
            drip_source_left_cm=drip_source_left_cm,
            drip_source_right_cm=drip_source_right_cm,
        )
        points["hydrus_source_wet"] = hydrus_source_wet
        points["maizsim_source_wet"] = maizsim_source_wet
        source_intersection = hydrus_source_wet & maizsim_source_wet
        source_union = hydrus_source_wet | maizsim_source_wet
        source_union_area = float(weights[source_union].sum())
        metrics.update(
            {
                "hydrus_source_wet_area_cm2": float(weights[hydrus_source_wet].sum()),
                "maizsim_source_wet_area_cm2": float(weights[maizsim_source_wet].sum()),
                "source_wet_intersection_area_cm2": float(
                    weights[source_intersection].sum()
                ),
                "source_wet_union_area_cm2": source_union_area,
                "source_wet_iou": float(
                    weights[source_intersection].sum() / source_union_area
                )
                if source_union_area > 0.0
                else 0.0,
                "hydrus_source_wet_width_cm": _span(
                    points.loc[hydrus_source_wet, "x_cm"]
                ),
                "maizsim_source_wet_width_cm": _span(
                    points.loc[maizsim_source_wet, "x_cm"]
                ),
                "hydrus_source_wet_depth_cm": _max_or_zero(
                    points.loc[hydrus_source_wet, "depth_cm"]
                ),
                "maizsim_source_wet_depth_cm": _max_or_zero(
                    points.loc[maizsim_source_wet, "depth_cm"]
                ),
            }
        )
    if "hydrus_delta_theta_sd" in points.columns:
        metrics.update(
            _uncertainty_metrics(
                points,
                residual_column="delta_theta_residual",
                sd_column="hydrus_delta_theta_sd",
                prefix="delta_theta",
            )
        )
    return metrics


def _uncertainty_metrics(points, *, residual_column, sd_column, prefix):
    values = points[[residual_column, sd_column, "area_cm2"]].dropna()
    values = values[values[sd_column] > 0.0]
    if values.empty:
        return {}
    residual = values[residual_column].to_numpy(dtype=float)
    sd = values[sd_column].to_numpy(dtype=float)
    weights = values["area_cm2"].to_numpy(dtype=float)
    normalized = residual / sd
    within_2sd = np.abs(residual) <= 2.0 * sd
    return {
        f"{prefix}_uncertainty_point_count": float(len(values)),
        f"{prefix}_normalized_rmse": float(
            np.sqrt(_weighted_mean(normalized * normalized, weights))
        ),
        f"{prefix}_abs_residual_le_2sd_fraction": float(
            np.average(within_2sd.astype(float), weights=weights)
        ),
    }


def _coverage_metrics(hydrus_reference, maizsim_source, comparison_points):
    hydrus_area = float(_weights(hydrus_reference).sum())
    comparison_area = float(_weights(comparison_points).sum())
    hydrus_count = float(len(hydrus_reference))
    comparison_count = float(len(comparison_points))
    return {
        "hydrus_reference_point_count": hydrus_count,
        "maizsim_source_point_count": float(len(maizsim_source)),
        "comparison_point_count": comparison_count,
        "dropped_reference_point_count": hydrus_count - comparison_count,
        "comparison_point_fraction": comparison_count / hydrus_count
        if hydrus_count > 0.0
        else 0.0,
        "hydrus_reference_area_cm2": hydrus_area,
        "comparison_area_cm2": comparison_area,
        "dropped_reference_area_cm2": hydrus_area - comparison_area,
        "comparison_area_fraction": comparison_area / hydrus_area
        if hydrus_area > 0.0
        else 0.0,
        "hydrus_x_span_cm": _span(hydrus_reference["x_cm"]),
        "hydrus_depth_span_cm": _span(hydrus_reference["depth_cm"]),
        "maizsim_x_span_cm": _span(maizsim_source["x_cm"]),
        "maizsim_depth_span_cm": _span(maizsim_source["depth_cm"]),
        "comparison_x_span_cm": _span(comparison_points["x_cm"]),
        "comparison_depth_span_cm": _span(comparison_points["depth_cm"]),
    }


def _interpolate_to_points(source, target):
    return _interpolate_column_to_points(source, target, "theta")


def _interpolate_column_to_points(source, target, column):
    triangulation = mtri.Triangulation(
        source["x_cm"].to_numpy(dtype=float),
        source["depth_cm"].to_numpy(dtype=float),
    )
    interpolator = mtri.LinearTriInterpolator(
        triangulation,
        source[column].to_numpy(dtype=float),
    )
    values = interpolator(
        target["x_cm"].to_numpy(dtype=float),
        target["depth_cm"].to_numpy(dtype=float),
    )
    return np.ma.filled(values, np.nan)


def _source_connected_wet_mask(
    points,
    wet_mask,
    *,
    drip_x_cm,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    wet = np.asarray(wet_mask, dtype=bool)
    result = np.zeros(len(points), dtype=bool)
    wet_indices = np.flatnonzero(wet)
    if len(wet_indices) == 0:
        return result

    x_values = points["x_cm"].to_numpy(dtype=float)
    depth_values = points["depth_cm"].to_numpy(dtype=float)
    candidate_indices = wet_indices
    if drip_source_left_cm is not None and drip_source_right_cm is not None:
        left = float(drip_source_left_cm)
        right = float(drip_source_right_cm)
        in_source = wet & (x_values >= left) & (x_values <= right)
        if in_source.any():
            candidate_indices = np.flatnonzero(in_source)

    seed_scores = (
        np.abs(x_values[candidate_indices] - float(drip_x_cm))
        + depth_values[candidate_indices]
    )
    seed = int(candidate_indices[int(np.argmin(seed_scores))])
    adjacency = _triangulation_adjacency(points)
    stack = [seed]
    result[seed] = True
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if wet[neighbor] and not result[neighbor]:
                result[neighbor] = True
                stack.append(neighbor)
    return result


def _triangulation_adjacency(points):
    triangulation = mtri.Triangulation(
        points["x_cm"].to_numpy(dtype=float),
        points["depth_cm"].to_numpy(dtype=float),
    )
    adjacency = [set() for _ in range(len(points))]
    for left, middle, right in triangulation.triangles:
        adjacency[left].update((middle, right))
        adjacency[middle].update((left, right))
        adjacency[right].update((left, middle))
    return adjacency


def _tri_contour(ax, points, column, *, cmap, vmin, vmax):
    triangulation = mtri.Triangulation(
        points["x_cm"].to_numpy(dtype=float),
        points["depth_cm"].to_numpy(dtype=float),
    )
    contour = ax.tricontourf(
        triangulation,
        points[column].to_numpy(dtype=float),
        levels=np.linspace(vmin, vmax, 15),
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        extend="both",
    )
    ax.invert_yaxis()
    return contour


def _annotate_wet_front(ax, points, column, threshold):
    values = points[column].to_numpy(dtype=float)
    threshold = float(threshold)
    if not np.nanmin(values) <= threshold <= np.nanmax(values):
        return
    triangulation = mtri.Triangulation(
        points["x_cm"].to_numpy(dtype=float),
        points["depth_cm"].to_numpy(dtype=float),
    )
    ax.tricontour(
        triangulation,
        values,
        levels=[threshold],
        colors="#1a1a1a",
        linewidths=0.75,
        linestyles="solid",
    )


def _annotate_drip_source(
    ax,
    points,
    *,
    drip_x_cm=None,
    drip_source_left_cm=None,
    drip_source_right_cm=None,
):
    surface_depth = float(points["depth_cm"].min())
    max_depth = float(points["depth_cm"].max())
    if drip_x_cm is not None:
        drip_x = float(drip_x_cm)
        ax.axvline(drip_x, color="#d62728", linestyle="--", linewidth=0.8)
        ax.scatter(
            [drip_x],
            [surface_depth],
            marker="v",
            s=18,
            color="#d62728",
            zorder=5,
        )
        ax.text(
            drip_x,
            surface_depth + 0.04 * max(1.0, max_depth - surface_depth),
            "drip",
            color="#d62728",
            fontsize=6,
            ha="left",
            va="top",
        )
    if drip_source_left_cm is not None and drip_source_right_cm is not None:
        left = float(drip_source_left_cm)
        right = float(drip_source_right_cm)
        ax.hlines(
            surface_depth,
            xmin=left,
            xmax=right,
            colors="#d62728",
            linewidth=1.4,
            zorder=5,
        )
        ax.vlines(
            [left, right],
            surface_depth,
            surface_depth + 0.015 * max(1.0, max_depth - surface_depth),
            colors="#d62728",
            linewidth=1.0,
            zorder=5,
        )


def _standard_field(frame, name):
    columns = ["x_cm", "depth_cm", "theta", "area_cm2"]
    if "axisym_volume_cm3" in frame.columns:
        columns.append("axisym_volume_cm3")
    if "theta_sd" in frame.columns:
        columns.append("theta_sd")
    result = frame[columns].copy()
    _validate_field(result, name)
    return result


def _arg_or_manifest(value, manifest, key):
    if value is not None or manifest is None:
        return value
    return manifest.get(key)


def _validate_drip_annotation_args(left, right):
    if (left is None) != (right is None):
        raise ValueError(
            "Both drip source endpoints are required: "
            "--drip-source-left-cm and --drip-source-right-cm."
        )


def _validate_drip_source_manifest(manifest, source):
    left = float(manifest["drip_source_left_cm"])
    right = float(manifest["drip_source_right_cm"])
    drip_x = float(manifest["drip_x_cm"])
    if not left < right:
        raise ValueError(
            f"Comparison manifest {source} requires drip_source_left_cm < "
            "drip_source_right_cm."
        )
    if not left <= drip_x <= right:
        raise ValueError(
            f"Comparison manifest {source} requires drip_x_cm inside the "
            "drip source interval."
        )


def _validate_reproducibility_manifest(manifest, source):
    _reject_manifest_placeholders(manifest, source)
    for key in ("hydrus_mesh", "maizsim_grid"):
        value = manifest[key]
        if not isinstance(value, dict):
            raise ValueError(f"Comparison manifest {source} requires {key} as an object.")
        if not value:
            raise ValueError(f"Comparison manifest {source} requires non-empty {key}.")
    for key in ("hydrus_time_step_control", "maizsim_time_step_control"):
        value = manifest[key]
        if not isinstance(value, (dict, str)):
            raise ValueError(
                f"Comparison manifest {source} requires {key} as an object or string."
            )
        if isinstance(value, dict) and not value:
            raise ValueError(f"Comparison manifest {source} requires non-empty {key}.")
    theta_units = str(manifest["theta_units"]).strip().casefold()
    accepted_units = {"cm3 cm-3", "cm3/cm3", "m3 m-3", "m3/m3", "fraction"}
    if theta_units not in accepted_units:
        raise ValueError(
            f"Comparison manifest {source} theta_units must be one of "
            f"{sorted(accepted_units)}."
        )
    coordinate_system = str(manifest["comparison_coordinate_system"]).casefold()
    required_terms = ("x", "depth")
    if not all(term in coordinate_system for term in required_terms):
        raise ValueError(
            f"Comparison manifest {source} comparison_coordinate_system must "
            "state x and depth coordinates."
        )


def _validate_reference_provenance_manifest(manifest, source):
    reference_type = str(manifest["reference_data_type"]).strip().casefold()
    if reference_type not in ACCEPTED_REFERENCE_DATA_TYPES:
        raise ValueError(
            f"Comparison manifest {source} reference_data_type must be one of "
            f"{sorted(ACCEPTED_REFERENCE_DATA_TYPES)}."
        )
    _validate_reference_identity(manifest["reference_identity"], source)
    provenance = manifest["reference_data_provenance"]
    if not isinstance(provenance, dict):
        raise ValueError(
            f"Comparison manifest {source} requires reference_data_provenance "
            "as an object."
        )
    missing = [
        key
        for key in REQUIRED_REFERENCE_PROVENANCE_KEYS
        if key not in provenance or provenance[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {source} reference_data_provenance is "
            f"missing required keys: {missing}."
        )
    exported_variable = str(provenance["exported_variable"]).strip().casefold()
    if not any(term in exported_variable for term in ("theta", "water content", "swc")):
        raise ValueError(
            f"Comparison manifest {source} reference_data_provenance."
            "exported_variable must identify theta or water content."
        )
    if reference_type in ("hydrus_2d_simulation", "hydrus_2d_3d_simulation"):
        _validate_hydrus_reference_run(manifest, source)
    if reference_type == "measured_2d_theta_field":
        _validate_measured_reference_metadata(manifest, source)
    _validate_raw_reference_files(manifest["raw_reference_files"], source)
    _validate_independence_proof(manifest["independence_proof"], source)
    uncertainty = manifest["uncertainty_basis"]
    if not isinstance(uncertainty, dict):
        raise ValueError(
            f"Comparison manifest {source} requires uncertainty_basis as an object."
        )
    missing_uncertainty = [
        key
        for key in REQUIRED_UNCERTAINTY_BASIS_KEYS
        if key not in uncertainty or uncertainty[key] in ("", None)
    ]
    if missing_uncertainty:
        raise ValueError(
            f"Comparison manifest {source} uncertainty_basis is missing "
            f"required keys: {missing_uncertainty}."
        )


def _validate_reference_identity(identity, source):
    if not isinstance(identity, dict):
        raise ValueError(
            f"Comparison manifest {source} requires reference_identity as an object."
        )
    missing = [
        key
        for key in REQUIRED_REFERENCE_IDENTITY_KEYS
        if key not in identity or identity[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {source} reference_identity is missing "
            f"required keys: {missing}."
        )
    _validate_timestamp_utc(
        identity["data_freeze_timestamp_utc"],
        source,
        "reference_identity.data_freeze_timestamp_utc",
    )


def _validate_hydrus_reference_run(manifest, source):
    run = manifest.get("hydrus_reference_run")
    if not isinstance(run, dict):
        raise ValueError(
            f"Comparison manifest {source} requires hydrus_reference_run "
            "as an object for HYDRUS reference cases."
        )
    missing = [
        key
        for key in REQUIRED_HYDRUS_REFERENCE_RUN_KEYS
        if key not in run or run[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run is missing "
            f"required keys: {missing}."
        )
    domain_mode = str(run["domain_mode"]).strip().casefold()
    if domain_mode not in ACCEPTED_HYDRUS_DOMAIN_MODES:
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run.domain_mode "
            f"must be one of {sorted(ACCEPTED_HYDRUS_DOMAIN_MODES)}."
        )
    solver_tolerances = run["solver_tolerances"]
    if not isinstance(solver_tolerances, dict) or not solver_tolerances:
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run."
            "solver_tolerances must be a non-empty object."
        )
    mass_balance_error = _finite_float(
        run["mass_balance_error_percent"],
        source,
        "hydrus_reference_run.mass_balance_error_percent",
    )
    if abs(mass_balance_error) > 1.0:
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run."
            "mass_balance_error_percent must be within +/-1%."
        )
    output_time = _finite_float(
        run["output_record_time_h"],
        source,
        "hydrus_reference_run.output_record_time_h",
    )
    if output_time < 0.0:
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run."
            "output_record_time_h must be non-negative."
        )
    event_time = float(manifest["event_relative_time_h"])
    if not np.isclose(output_time, event_time, rtol=0.0, atol=1.0e-9):
        raise ValueError(
            f"Comparison manifest {source} hydrus_reference_run."
            "output_record_time_h must match event_relative_time_h."
        )


def _validate_measured_reference_metadata(manifest, source):
    metadata = manifest.get("measured_reference_metadata")
    if not isinstance(metadata, dict):
        raise ValueError(
            f"Comparison manifest {source} requires measured_reference_metadata "
            "as an object for measured 2D theta fields."
        )
    missing = [
        key
        for key in REQUIRED_MEASURED_REFERENCE_METADATA_KEYS
        if key not in metadata or metadata[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata is "
            f"missing required keys: {missing}."
        )
    instrument_ids = metadata["instrument_ids"]
    if not isinstance(instrument_ids, list) or not instrument_ids:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "instrument_ids must be a non-empty list."
        )
    spatial_resolution = _finite_float(
        metadata["spatial_resolution_cm"],
        source,
        "measured_reference_metadata.spatial_resolution_cm",
    )
    if spatial_resolution <= 0.0:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "spatial_resolution_cm must be positive."
        )
    registration_error = _finite_float(
        metadata["registration_error_cm"],
        source,
        "measured_reference_metadata.registration_error_cm",
    )
    if registration_error < 0.0:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "registration_error_cm must be non-negative."
        )
    replicate_count = _finite_float(
        metadata["replicate_count"],
        source,
        "measured_reference_metadata.replicate_count",
    )
    if replicate_count < 1.0 or not float(replicate_count).is_integer():
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "replicate_count must be a positive integer."
        )
    qaqc_flags = metadata["qaqc_flags"]
    if not isinstance(qaqc_flags, (dict, list)) or not qaqc_flags:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "qaqc_flags must be a non-empty object or list."
        )
    uncertainty_model = metadata["uncertainty_model"]
    if isinstance(uncertainty_model, dict) and not uncertainty_model:
        raise ValueError(
            f"Comparison manifest {source} measured_reference_metadata."
            "uncertainty_model must be non-empty."
        )


def _validate_raw_reference_files(raw_files, source):
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError(
            f"Comparison manifest {source} raw_reference_files must be a non-empty list."
        )
    roles = []
    for index, item in enumerate(raw_files):
        if not isinstance(item, dict):
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}] "
                "must be an object."
            )
        missing = [
            key
            for key in REQUIRED_RAW_REFERENCE_FILE_KEYS
            if key not in item or item[key] in ("", None)
        ]
        if missing:
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}] "
                f"is missing required keys: {missing}."
            )
        roles.append(str(item["role"]))
        _validate_sha256(
            item["sha256"],
            source,
            f"raw_reference_files[{index}].sha256",
        )
        try:
            size = float(item["size_bytes"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}]."
                "size_bytes must be numeric."
            ) from exc
        if not np.isfinite(size) or size <= 0.0:
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}]."
                "size_bytes must be positive."
            )
        local_path = _local_raw_reference_path(item["path_or_uri"], source)
        if local_path is None:
            continue
        if not local_path.is_file():
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}]."
                f"path_or_uri does not exist as a local file: {local_path}."
            )
        actual_size = int(local_path.stat().st_size)
        if int(size) != actual_size:
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}]."
                f"size_bytes does not match {local_path}."
            )
        if str(item["sha256"]).strip().casefold() != _sha256(local_path):
            raise ValueError(
                f"Comparison manifest {source} raw_reference_files[{index}]."
                f"sha256 does not match {local_path}."
            )
        item["path_or_uri"] = str(local_path)
    _validate_raw_reference_role_coverage(roles, source)


def _local_raw_reference_path(path_or_uri, source):
    text = str(path_or_uri).strip()
    if not text or "://" in text or text.startswith("doi:"):
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path(source).parent / path
    return path.expanduser().resolve()


def _validate_raw_reference_role_coverage(roles, source):
    if not _has_raw_reference_role(
        roles,
        RAW_REFERENCE_EVENT_ROLE_TOKENS,
        exclude_tokens=RAW_REFERENCE_BASELINE_ROLE_TOKENS,
    ):
        raise ValueError(
            f"Comparison manifest {source} raw_reference_files must include "
            "an event/output theta-field role."
        )
    if not _has_raw_reference_role(roles, RAW_REFERENCE_BASELINE_ROLE_TOKENS):
        raise ValueError(
            f"Comparison manifest {source} raw_reference_files must include "
            "a baseline/pre-event theta-field role."
        )


def _has_raw_reference_role(roles, tokens, *, exclude_tokens=()):
    for role in roles:
        normalized = str(role).strip().casefold().replace("-", "_").replace(" ", "_")
        if any(token.replace("-", "_") in normalized for token in exclude_tokens):
            continue
        if any(token.replace("-", "_") in normalized for token in tokens):
            return True
    return False


def _validate_independence_proof(independence, source):
    if not isinstance(independence, dict):
        raise ValueError(
            f"Comparison manifest {source} requires independence_proof as an object."
        )
    missing = [
        key
        for key in REQUIRED_INDEPENDENCE_PROOF_KEYS
        if key not in independence or independence[key] in ("", None)
    ]
    if missing:
        raise ValueError(
            f"Comparison manifest {source} independence_proof is missing "
            f"required keys: {missing}."
        )
    if independence["excluded_from_calibration"] is not True:
        raise ValueError(
            f"Comparison manifest {source} independence_proof."
            "excluded_from_calibration must be true."
        )
    calibration_ids = independence["calibration_dataset_ids"]
    if not isinstance(calibration_ids, list):
        raise ValueError(
            f"Comparison manifest {source} independence_proof."
            "calibration_dataset_ids must be a list."
        )
    validation_id = str(independence["validation_dataset_id"])
    if validation_id in {str(item) for item in calibration_ids}:
        raise ValueError(
            f"Comparison manifest {source} validation_dataset_id must not "
            "appear in calibration_dataset_ids."
        )
    _validate_sha256(
        independence["freeze_record_sha256"],
        source,
        "independence_proof.freeze_record_sha256",
    )
    _validate_timestamp_utc(
        independence["parameter_freeze_timestamp_utc"],
        source,
        "independence_proof.parameter_freeze_timestamp_utc",
    )


def _validate_sha256(value, source, path):
    text = str(value).strip().casefold()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"Comparison manifest {source} {path} must be a SHA-256 hex digest.")


def _finite_float(value, source, path):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Comparison manifest {source} {path} must be numeric.") from exc
    if not np.isfinite(number):
        raise ValueError(f"Comparison manifest {source} {path} must be finite.")
    return number


def _validate_timestamp_utc(value, source, path):
    try:
        timestamp = pd.to_datetime(value, utc=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Comparison manifest {source} {path} must be an ISO-like UTC timestamp."
        ) from exc
    if pd.isna(timestamp):
        raise ValueError(
            f"Comparison manifest {source} {path} must be an ISO-like UTC timestamp."
        )


def _validate_event_time_manifest(manifest, source):
    try:
        event_relative_time = float(manifest["event_relative_time_h"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Comparison manifest {source} event_relative_time_h must be numeric."
        ) from exc
    if not np.isfinite(event_relative_time) or event_relative_time < 0.0:
        raise ValueError(
            f"Comparison manifest {source} event_relative_time_h must be finite "
            "and non-negative."
        )
    hydrus_time = manifest.get("hydrus_time_step_control")
    if not isinstance(hydrus_time, dict) or "output_time_h" not in hydrus_time:
        return
    try:
        hydrus_output_time = float(hydrus_time["output_time_h"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Comparison manifest {source} hydrus_time_step_control.output_time_h "
            "must be numeric when provided."
        ) from exc
    if not np.isclose(event_relative_time, hydrus_output_time, rtol=0.0, atol=1.0e-9):
        raise ValueError(
            f"Comparison manifest {source} event_relative_time_h must match "
            "hydrus_time_step_control.output_time_h when both are provided."
        )


def _validate_solver_coupling_manifest(manifest, source):
    coupling = str(manifest["water_solver_coupling"]).strip().casefold()
    if coupling not in ACCEPTED_WATER_SOLVER_COUPLINGS:
        raise ValueError(
            f"Comparison manifest {source} water_solver_coupling must be one "
            f"of {sorted(ACCEPTED_WATER_SOLVER_COUPLINGS)}."
        )
    formulation = str(manifest["drip_source_formulation"]).strip().casefold()
    forbidden_terms = ("bypass", "direct_storage")
    if any(term in formulation for term in forbidden_terms):
        raise ValueError(
            f"Comparison manifest {source} drip_source_formulation must not "
            "describe a WaterMover-bypass or direct-storage source for a "
            "journal-readiness validation case."
        )


def _reject_manifest_placeholders(value, source, path="manifest"):
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_manifest_placeholders(item, source, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_manifest_placeholders(item, source, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    normalized = " ".join(value.strip().casefold().split())
    for pattern in MANIFEST_PLACEHOLDER_PATTERNS:
        if pattern in normalized:
            raise ValueError(
                f"Comparison manifest {source} contains placeholder text at "
                f"{path}: {value!r}."
            )


def _validate_field(frame, source):
    required = ("x_cm", "depth_cm", "theta", "area_cm2")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns {missing} in {source}.")
    if frame.empty:
        raise ValueError(f"Empty theta field: {source}.")
    for column in required:
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"Non-finite {column} values in {source}.")
    if (frame["area_cm2"] <= 0.0).any():
        raise ValueError(f"area_cm2 must be positive in {source}.")
    if "axisym_volume_cm3" in frame.columns:
        volumes = frame["axisym_volume_cm3"].to_numpy(dtype=float)
        if not np.isfinite(volumes).all():
            raise ValueError(f"Non-finite axisym_volume_cm3 values in {source}.")
        if (volumes <= 0.0).any():
            raise ValueError(f"axisym_volume_cm3 must be positive in {source}.")
    if "theta_sd" in frame.columns:
        uncertainty = frame["theta_sd"].to_numpy(dtype=float)
        if not np.isfinite(uncertainty).all():
            raise ValueError(f"Non-finite theta_sd values in {source}.")
        if (uncertainty <= 0.0).any():
            raise ValueError(f"theta_sd must be positive in {source}.")


def _read_csv(path):
    frame = pd.read_csv(path, skipinitialspace=True)
    frame = frame.rename(columns=lambda column: str(column).strip().strip(","))
    frame = frame.dropna(how="all")
    return frame


def _require_column(frame, aliases, path):
    column = _optional_column(frame, aliases)
    if column is None:
        raise ValueError(f"Missing one of {aliases!r} in {path}.")
    return column


def _optional_column(frame, aliases):
    normalized_columns = {
        _normalize(column): column
        for column in frame.columns
    }
    for alias in aliases:
        column = normalized_columns.get(_normalize(alias))
        if column is not None:
            return column
    return None


def _normalize(column):
    return "".join(str(column).casefold().replace("_", "").split())


def _numeric(series, column, path):
    return pd.to_numeric(series, errors="raise").astype(float)


def _nearest_date_frame(frame, target_date, path):
    date_col = _require_column(frame, ("date",), path)
    target = pd.to_datetime(target_date)
    dates = pd.to_datetime(frame[date_col])
    nearest = frame.loc[(dates - target).abs().idxmin(), date_col]
    return frame[frame[date_col] == nearest].copy()


def _nearest_date_time_frame(frame, target_date_time, path):
    date_time_col = _require_column(
        frame,
        ("date_time", "datetime", "time", "time_h"),
        path,
    )
    values = _numeric(frame[date_time_col], date_time_col, path)
    nearest = values.iloc[(values - float(target_date_time)).abs().idxmin()]
    return frame[values == nearest].copy()


def _validate_single_maizsim_time(frame, path):
    date_time_col = _optional_column(frame, ("date_time", "datetime", "time", "time_h"))
    if date_time_col is not None and frame[date_time_col].nunique() > 1:
        raise ValueError(
            f"Multiple G03 Date_time values in {path}; pass --maizsim-date-time."
        )


def _weights(points):
    return points["area_cm2"].to_numpy(dtype=float)


def _volume_weights(points):
    if "axisym_volume_cm3" not in points.columns:
        return None
    return points["axisym_volume_cm3"].to_numpy(dtype=float)


def _weighted_mean(values, weights):
    return float(np.average(np.asarray(values, dtype=float), weights=weights))


def _correlation(left, right):
    if len(left) < 2:
        return 0.0
    if np.allclose(left, left[0]) or np.allclose(right, right[0]):
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _span(values):
    if len(values) == 0:
        return 0.0
    return float(values.max() - values.min())


def _max_or_zero(values):
    if len(values) == 0:
        return 0.0
    return float(values.max())


def _peak_distance(points):
    hydrus_delta = points["hydrus_delta_theta"].to_numpy(dtype=float)
    maizsim_delta = points["maizsim_delta_theta"].to_numpy(dtype=float)
    hydrus_max = float(np.nanmax(hydrus_delta))
    maizsim_max = float(np.nanmax(maizsim_delta))
    hydrus_tol = max(1.0e-9, abs(hydrus_max) * 1.0e-6)
    maizsim_tol = max(1.0e-9, abs(maizsim_max) * 1.0e-6)
    hydrus_peaks = points.loc[
        points["hydrus_delta_theta"] >= hydrus_max - hydrus_tol,
        ["x_cm", "depth_cm"],
    ].to_numpy(dtype=float)
    maizsim_peaks = points.loc[
        points["maizsim_delta_theta"] >= maizsim_max - maizsim_tol,
        ["x_cm", "depth_cm"],
    ].to_numpy(dtype=float)
    if len(hydrus_peaks) == 0 or len(maizsim_peaks) == 0:
        return 0.0
    distances = []
    for point in maizsim_peaks:
        delta = hydrus_peaks - point
        distances.append(float(np.min(np.hypot(delta[:, 0], delta[:, 1]))))
    return float(min(distances))


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description="Compare MAIZSIM G03 theta fields with HYDRUS 2D CSV fields.",
    )
    parser.add_argument("--maizsim-g03", required=True)
    parser.add_argument("--hydrus-csv", required=True)
    parser.add_argument("--date", help="Date to select from MAIZSIM G03 output.")
    parser.add_argument(
        "--maizsim-date-time",
        type=float,
        help=(
            "Numeric MAIZSIM Date_time value to select from G03. "
            "Use this for hourly output where one Date has multiple frames."
        ),
    )
    parser.add_argument("--maizsim-baseline-g03")
    parser.add_argument("--hydrus-baseline-csv")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", default="hydrus_2d_comparison")
    parser.add_argument("--wet-delta-threshold", type=float, default=0.005)
    parser.add_argument(
        "--comparison-manifest",
        help=(
            "Optional JSON metadata proving HYDRUS and MAIZSIM were run under "
            "the same soil, boundary, emitter, and output-time conditions."
        ),
    )
    parser.add_argument("--drip-x-cm", type=float)
    parser.add_argument("--drip-source-left-cm", type=float)
    parser.add_argument("--drip-source-right-cm", type=float)
    return parser.parse_args(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
