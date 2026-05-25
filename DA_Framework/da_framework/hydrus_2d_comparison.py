"""Compare MAIZSIM 2D theta fields against exported HYDRUS 2D fields."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd


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
    "domain_width_cm",
    "domain_depth_cm",
    "drip_x_cm",
    "boundary_conditions",
    "baseline_definition",
)


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
    return manifest


def read_maizsim_g03_theta(path, date=None):
    """Read a MAIZSIM G03 theta field and convert y to depth from surface."""
    output_path = Path(path)
    frame = _read_csv(output_path)
    if date is not None:
        frame = _nearest_date_frame(frame, date, output_path)
    elif "Date" in frame.columns and frame["Date"].nunique() > 1:
        raise ValueError(f"Multiple G03 dates in {output_path}; pass a date.")

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
    _validate_field(result, output_path)
    return result


def compare_theta_fields(
    maizsim,
    hydrus,
    *,
    maizsim_baseline=None,
    hydrus_baseline=None,
    wet_delta_threshold=0.005,
):
    """Compare MAIZSIM theta against HYDRUS theta on HYDRUS reference points."""
    hydrus_points = _standard_field(hydrus, "hydrus")
    maizsim_field = _standard_field(maizsim, "maizsim")
    points = hydrus_points.copy()
    points = points.rename(columns={"theta": "hydrus_theta"})
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
        metrics.update(_delta_metrics(points, wet_delta_threshold))
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
        columns = (
            ("hydrus_delta_theta", "HYDRUS delta theta"),
            ("maizsim_delta_theta", "MAIZSIM delta theta"),
            ("delta_theta_residual", "MAIZSIM - HYDRUS"),
        )
        limit = max(
            abs(float(points["hydrus_delta_theta"].min())),
            abs(float(points["hydrus_delta_theta"].max())),
            abs(float(points["maizsim_delta_theta"].min())),
            abs(float(points["maizsim_delta_theta"].max())),
            0.001,
        )
        cmaps = ("RdBu_r", "RdBu_r", "RdBu_r")
        ranges = ((-limit, limit), (-limit, limit), (-limit, limit))
    else:
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

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.5), sharex=True, sharey=True)
    last = None
    for ax, (column, title), cmap, (vmin, vmax) in zip(axes, columns, cmaps, ranges):
        last = _tri_contour(ax, points, column, cmap=cmap, vmin=vmin, vmax=vmax)
        _annotate_drip_source(
            ax,
            points,
            drip_x_cm=drip_x_cm,
            drip_source_left_cm=drip_source_left_cm,
            drip_source_right_cm=drip_source_right_cm,
        )
        ax.set_title(title)
        ax.set_xlabel("x (cm)")
    axes[0].set_ylabel("Depth (cm)")
    fig.colorbar(last, ax=axes.ravel().tolist(), shrink=0.78)
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
):
    """Write summary CSV, point CSV, JSON index, and a comparison figure."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary_path = output_path / f"{prefix}_summary.csv"
    points_path = output_path / f"{prefix}_points.csv"
    figure_path = output_path / f"{prefix}_fields.png"
    index_path = output_path / f"{prefix}_outputs.json"
    manifest_path = output_path / f"{prefix}_manifest.json"

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
    maizsim = read_maizsim_g03_theta(args.maizsim_g03, args.date)
    hydrus_baseline = (
        read_hydrus_theta_csv(args.hydrus_baseline_csv)
        if args.hydrus_baseline_csv
        else None
    )
    maizsim_baseline = (
        read_maizsim_g03_theta(args.maizsim_baseline_g03, args.date)
        if args.maizsim_baseline_g03
        else None
    )
    if (hydrus_baseline is None) != (maizsim_baseline is None):
        raise ValueError(
            "Both HYDRUS and MAIZSIM baseline fields are required "
            "for delta comparison."
        )
    comparison = compare_theta_fields(
        maizsim,
        hydrus,
        maizsim_baseline=maizsim_baseline,
        hydrus_baseline=hydrus_baseline,
        wet_delta_threshold=args.wet_delta_threshold,
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
    outputs = write_comparison_outputs(
        comparison,
        args.output_dir,
        args.prefix,
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
        comparison_manifest=manifest,
    )
    if arguments is None:
        print(json.dumps(outputs, indent=2))
    return 0


def _field_metrics(points):
    weights = _weights(points)
    residual = points["theta_residual"].to_numpy(dtype=float)
    hydrus_theta = points["hydrus_theta"].to_numpy(dtype=float)
    maizsim_theta = points["maizsim_theta"].to_numpy(dtype=float)
    return {
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


def _delta_metrics(points, threshold):
    weights = _weights(points)
    residual = points["delta_theta_residual"].to_numpy(dtype=float)
    hydrus_delta = points["hydrus_delta_theta"].to_numpy(dtype=float)
    maizsim_delta = points["maizsim_delta_theta"].to_numpy(dtype=float)
    hydrus_wet = hydrus_delta >= float(threshold)
    maizsim_wet = maizsim_delta >= float(threshold)
    intersection = hydrus_wet & maizsim_wet
    union = hydrus_wet | maizsim_wet
    union_area = float(weights[union].sum())
    return {
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


def _interpolate_to_points(source, target):
    triangulation = mtri.Triangulation(
        source["x_cm"].to_numpy(dtype=float),
        source["depth_cm"].to_numpy(dtype=float),
    )
    interpolator = mtri.LinearTriInterpolator(
        triangulation,
        source["theta"].to_numpy(dtype=float),
    )
    values = interpolator(
        target["x_cm"].to_numpy(dtype=float),
        target["depth_cm"].to_numpy(dtype=float),
    )
    return np.ma.filled(values, np.nan)


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
    result = frame[["x_cm", "depth_cm", "theta", "area_cm2"]].copy()
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
    normalized_aliases = {_normalize(alias) for alias in aliases}
    for column in frame.columns:
        if _normalize(column) in normalized_aliases:
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


def _weights(points):
    return points["area_cm2"].to_numpy(dtype=float)


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
    hydrus_idx = int(points["hydrus_delta_theta"].idxmax())
    maizsim_idx = int(points["maizsim_delta_theta"].idxmax())
    dx = float(points.loc[maizsim_idx, "x_cm"] - points.loc[hydrus_idx, "x_cm"])
    dz = float(points.loc[maizsim_idx, "depth_cm"] - points.loc[hydrus_idx, "depth_cm"])
    return float(np.hypot(dx, dz))


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description="Compare MAIZSIM G03 theta fields with HYDRUS 2D CSV fields.",
    )
    parser.add_argument("--maizsim-g03", required=True)
    parser.add_argument("--hydrus-csv", required=True)
    parser.add_argument("--date", help="Date to select from MAIZSIM G03 output.")
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
