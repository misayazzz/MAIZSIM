"""Build and run MAIZSIM cases aligned to official HYDRUS SurfaceDrip projects."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .drip_validation import read_g05_surface_water
from .hydrus_2d_comparison import compare_theta_fields, read_hydrus_theta_csv
from .hydrus_2d_comparison import read_maizsim_g03_theta, write_comparison_outputs
from .hydrus_official_export import _decode_text
from .hydrus_official_export import hydrus_shape_metrics, read_official_project
from .hydrus_official_export import read_official_project_streams
from .hydrus_official_export import write_official_project_outputs
from .model_runner import run_model


BASE_RUN_RELATIVE = Path("DA_Framework") / "base_runs" / "SingleLayerLoam2D"
EXECUTABLE_NAME = "2dMAIZSIM.exe"
DLL_NAME = "Maizsim.dll"
RUN_FILE = "run.dat"
INITIAL_DATE = "04/27/2007"
FINAL_DATE = "04/28/2007"
EVENT_START_HOUR = 22.0
EVENT_STOP_HOUR = 0.0
SENSITIVITY_THRESHOLDS = (0.002, 0.005, 0.01, 0.02, 0.05)


@dataclass(frozen=True)
class HydrusBoundary:
    """HYDRUS boundary node table."""

    nodes: pd.DataFrame


@dataclass(frozen=True)
class PreparedAlignedRuns:
    """Prepared MAIZSIM run directories for one HYDRUS project."""

    prefix: str
    baseline_dir: Path
    drip_dir: Path
    manifest: dict


def read_hydrus_boundary_text(text, mesh):
    """Parse HYDRUS ``BOUNDARY.IN`` node ids and boundary integration widths."""
    node_block = _required_block(text, "Node Number Array", "Width Array")
    width_block = _required_block(text, "Width Array", "Length of")
    nodes = [int(value) for value in re.findall(r"[-+]?\d+", node_block)]
    widths = [float(value) for value in _number_tokens(width_block)]
    if len(nodes) != len(widths):
        raise ValueError(
            "BOUNDARY.IN node and width counts differ: "
            f"{len(nodes)} != {len(widths)}."
        )
    frame = pd.DataFrame({"node": nodes, "width": widths})
    frame = frame.merge(
        mesh.nodes[["node", "x_cm", "z_cm", "depth_cm"]],
        on="node",
        how="left",
        validate="one_to_one",
    )
    if frame[["x_cm", "z_cm", "depth_cm"]].isna().any().any():
        missing = frame.loc[frame["x_cm"].isna(), "node"].tolist()
        raise ValueError(f"BOUNDARY.IN references mesh nodes not present: {missing}.")
    surface_depth = float(mesh.nodes["depth_cm"].min())
    bottom_depth = float(mesh.nodes["depth_cm"].max())
    frame["boundary_role"] = "other"
    frame.loc[frame["depth_cm"].sub(surface_depth).abs() < 1.0e-6, "boundary_role"] = "surface"
    frame.loc[frame["depth_cm"].sub(bottom_depth).abs() < 1.0e-6, "boundary_role"] = "bottom"
    return HydrusBoundary(nodes=frame)


def prepare_hydrus_aligned_runs(
    project_file=None,
    project_dir=None,
    *,
    workspace,
    repo_root=None,
    prefix=None,
    wet_delta_threshold=0.005,
    output_time_h=None,
    emitter_rate_l_h=None,
    drip_mode_override=None,
    drip_spread_mode=5,
    drip_wet_width_max_cm=None,
):
    """Create baseline and drip MAIZSIM runs aligned to one official HYDRUS project."""
    repo = _resolve_repo_root(repo_root)
    output_root = Path(workspace).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    streams, project_name = read_official_project_streams(
        project_dir=project_dir,
        project_file=project_file,
    )
    project = read_official_project(project_dir=project_dir, project_file=project_file)
    case_prefix = prefix or str(project.selector_metadata.get("project_name", project_name))
    boundary = read_hydrus_boundary_text(
        _decode_text(streams["BOUNDARY.IN"]),
        project.mesh,
    )
    selector = project.selector_metadata
    hydrus_output_time = (
        float(output_time_h)
        if output_time_h is not None
        else float(selector.get("t_max_h", project.theta_output.times_h[-1]))
    )
    hydrus_metrics = hydrus_shape_metrics(
        project.mesh,
        project.theta_output,
        output_time_h=hydrus_output_time,
        baseline_time_h=0.0,
        wet_delta_threshold=wet_delta_threshold,
    )
    drip_spread_mode = int(drip_spread_mode)
    if drip_spread_mode not in (0, 5, 6):
        raise ValueError("drip_spread_mode must be 0, 5, or 6")
    if drip_wet_width_max_cm is not None:
        drip_radius_cm = float(drip_wet_width_max_cm)
    elif drip_spread_mode in (5, 6):
        drip_radius_cm = 0.0
    else:
        drip_radius_cm = _hydrus_calibrated_drip_radius_cm(
            case_prefix,
            fallback=float(hydrus_metrics["wet_width_cm"]),
        )
    drip_source_depth_cm = 0.0
    drip_mode = 0
    if drip_mode_override is not None:
        drip_mode = int(drip_mode_override)
    if drip_spread_mode == 6:
        drip_source_formulation = "surface active-boundary approximation with h=0 switching"
        water_solver_coupling = "richards_surface_active_boundary"
    else:
        drip_source_formulation = "partial-width surface flux boundary"
        water_solver_coupling = "richards_surface_flux_boundary"
    rate_l_h = (
        float(emitter_rate_l_h)
        if emitter_rate_l_h is not None
        else _surface_drip_rate_l_h(_decode_text(streams.get("ATMOSPH.IN", b"")))
    )
    duration_h = float(selector.get("t_max_h", 2.0)) - float(selector.get("t_init_h", 0.0))
    source = _source_boundary_node(boundary.nodes)
    source_width = float(source["width"])
    # KAT=1 uses the HYDRUS axisymmetric boundary integration weight. Mode5
    # applies wAppl over the covered source measure, so this keeps the original
    # L/h emitter rate when the source measure is the HYDRUS source width.
    w_appl_cm_h = rate_l_h * 1000.0 / source_width

    base_run = repo / BASE_RUN_RELATIVE
    baseline_dir = output_root / f"{case_prefix}__baseline"
    drip_dir = output_root / f"{case_prefix}__drip"
    for run_dir in (baseline_dir, drip_dir):
        _copy_base_run(base_run, run_dir)
        write_maizsim_grid_from_hydrus(project, boundary, run_dir / "LOAM2D.grd")
        write_maizsim_soil_file(run_dir / "Loam_200cm.soi", selector)
        write_maizsim_node_file(run_dir / "LOAM2D.nod", project.dimensions.node_count)
        write_maizsim_time_file(run_dir / "LOAM2D.tim")
        write_zero_weather_header_file(run_dir / "WyeClimate.dat")
        write_zero_weather_file(run_dir / "LOAM2D.wea")
        write_zero_management_file(run_dir / "LOAM2D.man")
        write_no_sprinkler_irrigation_file(run_dir / "LOAM2D.irr")
        write_short_ini_file(run_dir / "LOAM2D.ini")
    write_maizsim_drip_file(
        drip_dir / "LOAM2D.drp",
        source,
        w_appl_cm_h,
        drip_radius_cm,
        drip_source_depth_cm=drip_source_depth_cm,
        drip_mode=drip_mode,
        drip_spread_mode=drip_spread_mode,
        drip_source_width_cm=source_width if drip_spread_mode in (5, 6) else 0.0,
    )
    write_maizsim_drip_file(
        baseline_dir / "LOAM2D.drp",
        source,
        0.0,
        drip_radius_cm,
        drip_source_depth_cm=drip_source_depth_cm,
        drip_mode=drip_mode,
        drip_spread_mode=drip_spread_mode,
        drip_source_width_cm=source_width if drip_spread_mode in (5, 6) else 0.0,
    )

    manifest = {
        "hydrus_project": case_prefix,
        "maizsim_run": str(output_root),
        "soil_hydraulic_parameters": selector.get("soil_hydraulic_parameters", {}),
        "initial_condition": "uniform pressure head hNew=-100 cm",
        "emitter_rate_l_h": rate_l_h,
        "applied_volume_l": rate_l_h * duration_h,
        "event_duration_h": duration_h,
        "hydrus_output_time_h": hydrus_output_time,
        "output_time": f"HYDRUS {hydrus_output_time:g} h; MAIZSIM final hourly frame",
        "event_relative_time_h": hydrus_output_time,
        "domain_width_cm": float(project.mesh.nodes["x_cm"].max() - project.mesh.nodes["x_cm"].min()),
        "domain_depth_cm": float(project.mesh.nodes["depth_cm"].max() - project.mesh.nodes["depth_cm"].min()),
        "drip_x_cm": float(source["x_cm"]),
        "drip_source_left_cm": 0.0 if int(selector.get("kat", -1)) == 1 else float(source["x_cm"] - 0.5 * drip_radius_cm),
        "drip_source_right_cm": drip_radius_cm if int(selector.get("kat", -1)) == 1 else float(source["x_cm"] + 0.5 * drip_radius_cm),
        "drip_source_formulation": drip_source_formulation,
        "water_solver_coupling": water_solver_coupling,
        "validation_scope": "same-condition HYDRUS field comparison, not HYDRUS solver replication",
        "boundary_conditions": "HYDRUS BOUNDARY.IN widths; MAIZSIM surface atmospheric, bottom seepage face",
        "baseline_definition": "same MAIZSIM setup with zero drip events",
        "hydrus_kat": int(selector.get("kat", -1)),
        "hydrus_boundary_count": int(len(boundary.nodes)),
        "hydrus_surface_boundary_count": int((boundary.nodes["boundary_role"] == "surface").sum()),
        "source_node": int(source["node"]),
        "source_boundary_width": source_width,
        "maizsim_wAppl_cm_h": w_appl_cm_h,
        "drip_wet_radius_cm": drip_radius_cm,
        "drip_source_depth_cm": drip_source_depth_cm,
        "drip_mode": drip_mode,
        "drip_spread_mode": drip_spread_mode,
        "hydrus_threshold_wet_width_cm": float(hydrus_metrics["wet_width_cm"]),
        "hydrus_threshold_wet_depth_cm": float(hydrus_metrics["wet_depth_cm"]),
        "wet_delta_threshold": float(wet_delta_threshold),
    }
    return PreparedAlignedRuns(
        prefix=case_prefix,
        baseline_dir=baseline_dir,
        drip_dir=drip_dir,
        manifest=manifest,
    )


def run_hydrus_aligned_validation(
    project_file=None,
    project_dir=None,
    *,
    workspace,
    output_dir,
    repo_root=None,
    prefix=None,
    wet_delta_threshold=0.005,
    emitter_rate_l_h=None,
    drip_mode_override=None,
    drip_spread_mode=5,
    drip_wet_width_max_cm=None,
    timeout_seconds=180,
):
    """Prepare runs, execute MAIZSIM, and write HYDRUS/MAIZSIM 2D comparisons."""
    prepared = prepare_hydrus_aligned_runs(
        project_file=project_file,
        project_dir=project_dir,
        workspace=workspace,
        repo_root=repo_root,
        prefix=prefix,
        wet_delta_threshold=wet_delta_threshold,
        emitter_rate_l_h=emitter_rate_l_h,
        drip_mode_override=drip_mode_override,
        drip_spread_mode=drip_spread_mode,
        drip_wet_width_max_cm=drip_wet_width_max_cm,
    )
    _run_model_checked(prepared.baseline_dir, timeout_seconds=timeout_seconds)
    _run_model_checked(prepared.drip_dir, timeout_seconds=timeout_seconds)

    project = read_official_project(project_dir=project_dir, project_file=project_file)
    output_path = Path(output_dir).expanduser().resolve()
    hydrus_outputs = write_official_project_outputs(
        project,
        output_path,
        prefix=prepared.prefix,
        output_time_h=float(prepared.manifest["hydrus_output_time_h"]),
        baseline_time_h=0.0,
        wet_delta_threshold=wet_delta_threshold,
        drip_x_cm=prepared.manifest["drip_x_cm"],
    )
    target_date_time = _final_date_time(prepared.drip_dir / "LOAM2D.G03")
    baseline_date_time = _final_date_time(prepared.baseline_dir / "LOAM2D.G03")
    if abs(target_date_time - baseline_date_time) > 1.0e-6:
        raise ValueError(
            "Baseline and drip MAIZSIM G03 final times differ: "
            f"{baseline_date_time} vs {target_date_time}."
        )
    manifest = dict(prepared.manifest)
    manifest["maizsim_date_time"] = target_date_time
    maizsim_field = read_maizsim_g03_theta(
        prepared.drip_dir / "LOAM2D.G03",
        date_time=target_date_time,
    )
    hydrus_field = read_hydrus_theta_csv(hydrus_outputs["output_csv"])
    maizsim_baseline = read_maizsim_g03_theta(
        prepared.baseline_dir / "LOAM2D.G03",
        date_time=target_date_time,
    )
    hydrus_baseline = read_hydrus_theta_csv(hydrus_outputs["baseline_csv"])
    comparison = compare_theta_fields(
        maizsim_field,
        hydrus_field,
        maizsim_baseline=maizsim_baseline,
        hydrus_baseline=hydrus_baseline,
        wet_delta_threshold=wet_delta_threshold,
        drip_x_cm=manifest["drip_x_cm"],
        drip_source_left_cm=manifest["drip_source_left_cm"],
        drip_source_right_cm=manifest["drip_source_right_cm"],
    )
    _add_applied_volume_metrics(comparison.metrics, manifest)
    g05_metrics = _g05_drip_diagnostics(
        prepared.baseline_dir / "LOAM2D.G05",
        prepared.drip_dir / "LOAM2D.G05",
    )
    comparison_outputs = write_comparison_outputs(
        comparison,
        output_path,
        prefix=f"{prepared.prefix}_aligned",
        drip_x_cm=manifest["drip_x_cm"],
        drip_source_left_cm=manifest["drip_source_left_cm"],
        drip_source_right_cm=manifest["drip_source_right_cm"],
        comparison_manifest=manifest,
    )
    threshold_outputs = write_threshold_sensitivity_outputs(
        maizsim_field,
        hydrus_field,
        maizsim_baseline,
        hydrus_baseline,
        output_path,
        prefix=f"{prepared.prefix}_aligned",
        manifest=manifest,
    )
    summary = pd.DataFrame([{**manifest, **comparison.metrics, **g05_metrics}])
    summary_path = output_path / f"{prepared.prefix}_aligned_validation_summary.csv"
    summary.to_csv(summary_path, index=False)
    outputs = {
        "baseline_run_dir": str(prepared.baseline_dir),
        "drip_run_dir": str(prepared.drip_dir),
        "hydrus_outputs": hydrus_outputs,
        "comparison_outputs": comparison_outputs,
        "threshold_sensitivity_outputs": threshold_outputs,
        "summary_csv": str(summary_path),
    }
    index_path = output_path / f"{prepared.prefix}_aligned_validation_outputs.json"
    index_path.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    return outputs


def _add_applied_volume_metrics(metrics, manifest):
    applied_volume_l = float(manifest.get("applied_volume_l", 0.0))
    if applied_volume_l <= 0.0:
        return
    for key in ("hydrus_delta_storage_l", "maizsim_delta_storage_l"):
        if key in metrics:
            metrics[f"{key}_per_applied_l"] = float(metrics[key]) / applied_volume_l


def _g05_drip_diagnostics(baseline_g05, drip_g05):
    """Return run-summed G05 drip diagnostics as drip-minus-baseline values."""
    baseline = read_g05_surface_water(baseline_g05)
    drip = read_g05_surface_water(drip_g05)
    columns = (
        "drip_input_mm",
        "drip_demand_mm",
        "drip_pressure_loss_mm",
        "drip_hydraulic_excess_mm",
        "drip_actual_infil_mm",
        "drip_source_input_mm",
        "drip_source_loss_mm",
        "drip_surface_storage_change_mm",
        "drip_surface_runoff_mm",
        "drip_surface_storage_mm",
        "drip_boundary_input_closure_mm",
        "drip_boundary_acceptance_closure_mm",
    )
    result = {}
    for column in columns:
        if column in baseline.columns and column in drip.columns:
            result[f"g05_{column}_sum"] = float(
                drip[column].sum() - baseline[column].sum()
            )
    source_input = result.get("g05_drip_source_input_mm_sum")
    source_loss = result.get("g05_drip_source_loss_mm_sum")
    demand = result.get("g05_drip_demand_mm_sum")
    if source_input is not None and source_loss is not None and demand is not None:
        result["g05_source_closure_residual_mm"] = float(
            demand - source_input - source_loss
        )
        result["g05_direct_source_closure_residual_mm"] = result[
            "g05_source_closure_residual_mm"
        ]
    drip_input = result.get("g05_drip_input_mm_sum")
    pressure_loss = result.get("g05_drip_pressure_loss_mm_sum")
    actual_infil = result.get("g05_drip_actual_infil_mm_sum")
    hydraulic_excess = result.get("g05_drip_hydraulic_excess_mm_sum")
    storage_change = result.get("g05_drip_surface_storage_change_mm_sum", 0.0)
    surface_runoff = result.get("g05_drip_surface_runoff_mm_sum", 0.0)
    if (
        demand is not None
        and pressure_loss is not None
        and drip_input is not None
    ):
        direct_residual = result.get("g05_drip_boundary_input_closure_mm_sum")
        if direct_residual is None:
            direct_residual = float(demand - pressure_loss - drip_input)
        result["g05_boundary_input_closure_residual_mm"] = direct_residual
    if (
        drip_input is not None
        and actual_infil is not None
        and hydraulic_excess is not None
    ):
        direct_residual = result.get("g05_drip_boundary_acceptance_closure_mm_sum")
        if direct_residual is None:
            direct_residual = float(
                drip_input
                - actual_infil
                - hydraulic_excess
                - storage_change
                - surface_runoff
            )
        result["g05_boundary_acceptance_residual_mm"] = direct_residual
    return result


def write_threshold_sensitivity_outputs(
    maizsim_field,
    hydrus_field,
    maizsim_baseline,
    hydrus_baseline,
    output_dir,
    *,
    prefix,
    manifest,
    thresholds=SENSITIVITY_THRESHOLDS,
):
    """Write threshold sensitivity metrics and a compact QA figure."""
    output_path = Path(output_dir)
    rows = []
    for threshold in thresholds:
        comparison = compare_theta_fields(
            maizsim_field,
            hydrus_field,
            maizsim_baseline=maizsim_baseline,
            hydrus_baseline=hydrus_baseline,
            wet_delta_threshold=threshold,
            drip_x_cm=manifest["drip_x_cm"],
            drip_source_left_cm=manifest["drip_source_left_cm"],
            drip_source_right_cm=manifest["drip_source_right_cm"],
        )
        _add_applied_volume_metrics(comparison.metrics, manifest)
        metrics = comparison.metrics
        rows.append(
            {
                "wet_delta_threshold": threshold,
                "delta_theta_rmse": metrics.get("delta_theta_rmse"),
                "delta_theta_volume_rmse": metrics.get("delta_theta_volume_rmse"),
                "hydrus_delta_storage_l": metrics.get("hydrus_delta_storage_l"),
                "maizsim_delta_storage_l": metrics.get("maizsim_delta_storage_l"),
                "delta_storage_residual_l": metrics.get("delta_storage_residual_l"),
                "hydrus_delta_storage_l_per_applied_l": metrics.get(
                    "hydrus_delta_storage_l_per_applied_l"
                ),
                "maizsim_delta_storage_l_per_applied_l": metrics.get(
                    "maizsim_delta_storage_l_per_applied_l"
                ),
                "wet_iou": metrics.get("wet_iou"),
                "source_wet_iou": metrics.get("source_wet_iou"),
                "hydrus_wet_width_cm": metrics.get("hydrus_wet_width_cm"),
                "maizsim_wet_width_cm": metrics.get("maizsim_wet_width_cm"),
                "hydrus_source_wet_width_cm": metrics.get(
                    "hydrus_source_wet_width_cm"
                ),
                "maizsim_source_wet_width_cm": metrics.get(
                    "maizsim_source_wet_width_cm"
                ),
                "hydrus_wet_depth_cm": metrics.get("hydrus_wet_depth_cm"),
                "maizsim_wet_depth_cm": metrics.get("maizsim_wet_depth_cm"),
                "hydrus_source_wet_depth_cm": metrics.get(
                    "hydrus_source_wet_depth_cm"
                ),
                "maizsim_source_wet_depth_cm": metrics.get(
                    "maizsim_source_wet_depth_cm"
                ),
            }
        )

    frame = pd.DataFrame(rows)
    csv_path = output_path / f"{prefix}_threshold_sensitivity.csv"
    figure_path = output_path / f"{prefix}_threshold_sensitivity.png"
    frame.to_csv(csv_path, index=False)
    _plot_threshold_sensitivity(frame, figure_path)
    return {
        "summary_csv": str(csv_path),
        "figure": str(figure_path),
    }


def _plot_threshold_sensitivity(frame, path):
    x_values = frame["wet_delta_threshold"]
    has_storage = frame[
        [
            "hydrus_delta_storage_l_per_applied_l",
            "maizsim_delta_storage_l_per_applied_l",
        ]
    ].notna().any().any()
    column_count = 4 if has_storage else 3
    fig, axes = plt.subplots(
        1,
        column_count,
        figsize=(9.2 if has_storage else 7.2, 2.2),
        constrained_layout=True,
    )

    axes[0].plot(x_values, frame["wet_iou"], marker="o", label="all wet area")
    axes[0].plot(
        x_values,
        frame["source_wet_iou"],
        marker="s",
        label="source-connected",
    )
    axes[0].set_ylabel("IoU")
    axes[0].set_ylim(0.0, 1.02)
    axes[0].legend(fontsize=6)

    axes[1].plot(
        x_values,
        frame["hydrus_source_wet_width_cm"],
        marker="o",
        label="HYDRUS",
    )
    axes[1].plot(
        x_values,
        frame["maizsim_source_wet_width_cm"],
        marker="s",
        label="MAIZSIM",
    )
    axes[1].set_ylabel("Connected width (cm)")
    axes[1].legend(fontsize=6)

    axes[2].plot(
        x_values,
        frame["hydrus_source_wet_depth_cm"],
        marker="o",
        label="HYDRUS",
    )
    axes[2].plot(
        x_values,
        frame["maizsim_source_wet_depth_cm"],
        marker="s",
        label="MAIZSIM",
    )
    axes[2].set_ylabel("Connected depth (cm)")
    axes[2].legend(fontsize=6)

    if has_storage:
        axes[3].plot(
            x_values,
            frame["hydrus_delta_storage_l_per_applied_l"],
            marker="o",
            label="HYDRUS",
        )
        axes[3].plot(
            x_values,
            frame["maizsim_delta_storage_l_per_applied_l"],
            marker="s",
            label="MAIZSIM",
        )
        axes[3].set_ylabel("Stored / applied")
        axes[3].legend(fontsize=6)

    for ax in axes:
        ax.set_xlabel("Delta theta threshold")
        ax.grid(color="0.9", linewidth=0.5)
    fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def write_maizsim_grid_from_hydrus(project, boundary, path):
    """Write a MAIZSIM ``.grd`` file using HYDRUS mesh and boundary widths."""
    selector = project.selector_metadata
    kat = int(selector.get("kat", 1))
    nodes = project.mesh.nodes.sort_values("node")
    elements = project.mesh.elements.sort_values("element")
    boundary_nodes = boundary.nodes
    lines = [
        "***************** GRID GENERATOR INFORMATION **********************************************",
        "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
        f"  {kat}     {len(nodes)}     {len(elements)}     {len(boundary_nodes)}     10     1",
        "   n           x          y      MatNum",
    ]
    for row in nodes.itertuples(index=False):
        lines.append(f"\t{int(row.node)}\t{float(row.x_cm):.6g}\t{float(row.z_cm):.6g}\t1")
    lines.extend(
        [
            "***************** ELEMENT INFORMATION ******************************************************",
            "         e         i         j         k         l     MatNumE",
        ]
    )
    for row in elements.itertuples(index=False):
        lines.append(
            f"\t{int(row.element)}\t{int(row.node1)}\t{int(row.node2)}\t"
            f"{int(row.node3)}\t0\t1"
        )
    lines.extend(
        [
            "****************Boundary geometry information**************************************",
            "    n  CodeW  CodeC  CodeH  CodeG  Width",
        ]
    )
    for row in boundary_nodes.itertuples(index=False):
        code_w, code_c, code_h, code_g = _boundary_codes(row.boundary_role)
        lines.append(
            f"    {int(row.node)} {code_w:4d} {code_c:4d} {code_h:6d} "
            f"{code_g:9d}      {float(row.width):.8g}"
        )
    bottom_nodes = [
        int(row.node)
        for row in boundary_nodes.itertuples(index=False)
        if row.boundary_role == "bottom"
    ]
    lines.extend(
        [
            "***************************Seepage face information********************************************",
            "NSeep",
        ]
    )
    if bottom_nodes:
        lines.extend(
            [
                " 1",
                "NSP(1)",
                f" {len(bottom_nodes)}",
                "NP(NSP,1)  NP(NSP,2)  NP(NSP,3) ...... NP(NSP,IJ-1)NP(NSP,IJ)",
                _format_int_row(bottom_nodes),
            ]
        )
    else:
        lines.append("  0")
    lines.extend(
        [
            "***************************Drainage Boundaries******************************************",
            "NDrain",
            "0",
        ]
    )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_maizsim_soil_file(path, selector_metadata):
    """Write MAIZSIM material parameters from HYDRUS van Genuchten parameters."""
    params = selector_metadata.get("soil_hydraulic_parameters", {})
    theta_r = float(params.get("theta_r", 0.078))
    theta_s = float(params.get("theta_s", 0.43))
    alpha = float(params.get("alpha_cm_inv", 0.036))
    n_value = float(params.get("n", 1.56))
    ks_day = float(params.get("ks_cm_h", 1.0)) * 24.0
    name = str(selector_metadata.get("project_name", "")).casefold()
    bulk_density = 1.55 if "drip2" in name else 1.40
    sand = 0.65 if "drip2" in name else 0.43
    silt = 0.25 if "drip2" in name else 0.39
    lines = [
        "           *** Material information ****                                                                   g/g  ",
        "   thr       ths         tha       thm      Alfa      n        Ks         Kk       thk       BulkD     OM    Sand    Silt   InitType",
        (
            f" {theta_r:.3f}\t {theta_s:.3f}\t {theta_r:.3f}\t {theta_s:.3f}\t "
            f"{alpha:.5f}\t {n_value:.5f}\t {ks_day:.5f}\t {ks_day:.5f}\t "
            f" {theta_s:.3f}\t {bulk_density:.3f}\t 0.0020\t {sand:.2f}\t "
            f"{silt:.2f}\t  'm'"
        ),
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_maizsim_node_file(path, node_count, *, h_new=-100.0, temperature_c=20.0):
    """Write uniform MAIZSIM initial nodal conditions."""
    lines = [
        " ***************** NODAL INFORMATION for MAIZSIM *******************************************************",
        "\tNode\tHumusN\tHumusC\tLitterN\tLitterC\tManureN\tManureC\tNH4\tNO3\tTmpr\thNew\tCO2\tO2\tN2O\tRTWT",
    ]
    for node in range(1, int(node_count) + 1):
        lines.append(
            f"\t{node}\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t"
            f"0.00\t0.00\t{temperature_c:.2f}\t{h_new:.2f}\t"
            "400.00\t206000.00\t0.00\t0.000000"
        )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_maizsim_time_file(path):
    """Write a 24 h model window with hourly output and a 22-24 h drip event."""
    lines = [
        "*** SYNCHRONIZER INFORMATION *****************************",
        "Initial time       dt       dtMin     DMul1    DMul2    tFin",
        f"'{INITIAL_DATE}'   0.0001        0.0000001     1.3           0.3          '{FINAL_DATE}'",
        "Output variables, 1 if true  Daily    Hourly",
        " 1             1 ",
        " Daily       Hourly   Weather data frequency. if daily enter 1   0; if hourly enter 0  1  ",
        " 0             1 ",
        "RunToEnd  - if 1 model continues after crop maturity to end time in time file",
        " 1 ",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_zero_weather_file(path):
    """Write hourly weather with no rain and no atmospheric evaporation driver."""
    rows = [
        "*** zero-weather HYDRUS-aligned short validation",
        " JDay   Date  Hour     Rad      Temper    rain     Wind   RH   CO2",
    ]
    dates = [("117", INITIAL_DATE), ("118", FINAL_DATE)]
    for jday, date in dates:
        for hour in range(1, 25):
            rows.append(f" {jday} '{date}' {hour} 0 20 0 0 100 380")
    Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_zero_weather_header_file(path):
    """Write weather descriptors that let constant temperature imply zero VPD."""
    lines = [
        "***STANDARD METEOROLOGICAL DATA  Header file for HYDRUS-aligned no-VPD run",
        "Latitude Longitude",
        " 39.02        -76.55 ",
        "^Daily Bulb T(1) ^ Daily Wind(2) ^RainIntensity(3) ^Daily Conc^(4) ,Furrow(5) ^Rel_humid(6) ^CO2(7)",
        " 0             0             0             0             0             0             0 ",
        "Parameters for changing of units: BSOLAR BTEMP ATEMP ERAIN BWIND BIR ",
        " BSOLAR is 1e6/3600 to go from j m-2 h-1 to wm-2",
        " 1000000       1             0             0.1           1             1 ",
        "Average values for the site",
        "wind    ChemConc     CO2  ",
        "8 0 380",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_zero_management_file(path):
    """Disable fertilizer, residue, and tillage for the short validation."""
    lines = [
        "*** Script for management practices fertilizer, residue and tillage",
        "[N Fertilizer]",
        "****Script for chemical application module  *******mg/cm2",
        "Number of Fertilizer applications (max=25)",
        " 0",
        "tAppl(i)  AmtAppl(i) depth(i) lAppl_C(i) lAppl_N(i)  mAppl_C(i) mAppl_N(i)",
        "No fertilizer",
        "[Residue]",
        "****Script for residue/mulch application module",
        "**** Residue amount can be thickness ('t') or mass ('m')   ***",
        "application  1 or 0, 1(yes) 0(no)",
        "0",
        "[Tillage]",
        "1: Tillage , 0: No till",
        " 0",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_no_sprinkler_irrigation_file(path):
    """Disable non-drip irrigation."""
    lines = [
        "****Script for Irrigation",
        "[Sprinkler]",
        "Sprinkler irrigation",
        "Average irrigation rate (cm/hour)",
        " 0",
        "Number of irrigation application",
        " 0",
        "No Irrigation",
        "[Flood_H]",
        "Flood irrigation as depth of water (cm)",
        "Number of flood irrigations as head (cm)",
        " 0",
        "No flood Irrigation",
        "[Flood_R]",
        "Flood irrigation as rate applied (cm/day)",
        "Number of flood irrigations as rate",
        " 0",
        "No flood Irrigation",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_short_ini_file(path):
    """Write initialization values for a pre-sowing short water-flow run."""
    lines = [
        "***INitialization data for HYDRUS-aligned short drip validation",
        "POPROW  ROWSP  Plant Density      ROWANG  xSeed  ySeed         CEC    EOMult",
        " 5.2578        76.2          6.9           0             0             137           0.65          0.5 ",
        "Latitude longitude altitude",
        " 39.02         76.55         50 ",
        "AutoIrrigate",
        " 0 ",
        "  Sowing        end         timestep",
        "'05/18/2007'  '09/18/2007'  60",
        "output soils data (g03, g04, g05 and g06 files) 1 if true",
        "'05/18/2007'  '07/04/2007'  60",
        "    0                     1",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_maizsim_drip_file(
    path,
    source,
    w_appl_cm_h,
    drip_radius_cm,
    *,
    drip_source_depth_cm=0.0,
    drip_mode=0,
    drip_spread_mode=5,
    drip_source_width_cm=0.0,
):
    """Write one precision drip event or a zero-event baseline."""
    if w_appl_cm_h <= 0.0:
        lines = [
            "*****Script for Drip application module  ******* wAppl is cm water per hour; Mode5 uses dynamic local source; Mode6 uses surface active-boundary approximation",
            "Number of Drip irrigations(max=75)",
            " 0 ",
            "No drip irrigation",
        ]
    else:
        drip_spread_mode = int(drip_spread_mode)
        if drip_spread_mode not in (0, 5, 6):
            raise ValueError("drip_spread_mode must be 0, 5, or 6")
        if drip_spread_mode not in (5, 6) and float(drip_source_width_cm) > 0.0:
            raise ValueError("drip_source_width_cm requires drip_spread_mode 5 or 6")
        if drip_spread_mode in (5, 6) and float(drip_source_width_cm) <= 0.0:
            raise ValueError("drip_source_width_cm must be positive when drip_spread_mode is 5 or 6")
        lines = [
            "*****Script for Drip application module  ******* wAppl is cm water per hour; Mode5 uses dynamic local source; Mode6 uses surface active-boundary approximation",
            "Number of Drip irrigations(max=75)",
            " 1 ",
            "Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode DripSourceWidth",
            (
                f"'{INITIAL_DATE}' {EVENT_START_HOUR:g} '{FINAL_DATE}' {EVENT_STOP_HOUR:g} "
                f"{w_appl_cm_h:.10g} 1 {int(drip_mode)} 0 1 0 "
                f"{float(drip_source_depth_cm):.10g} {drip_radius_cm:.10g} "
                f"{int(drip_spread_mode)} {float(drip_source_width_cm):.10g}"
            ),
            "Drip application nodes",
            f" {int(source['node'])}",
        ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _boundary_codes(role):
    if role == "surface":
        return -4, 0, -4, -4
    if role == "bottom":
        return -2, 0, 1, 1
    return 0, 0, 0, 0


def _format_int_row(values, *, per_line=10):
    lines = []
    for offset in range(0, len(values), per_line):
        chunk = values[offset : offset + per_line]
        lines.append("".join(f"{value:7d}" for value in chunk))
    return "\n".join(lines)


def _required_block(text, start_label, end_label):
    pattern = rf"{re.escape(start_label)}\s*\n(.*?)\n{re.escape(end_label)}"
    match = re.search(pattern, text, re.S)
    if match is None:
        raise ValueError(f"BOUNDARY.IN is missing block {start_label!r}.")
    return match.group(1)


def _number_tokens(text):
    return re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?", text)


def _source_boundary_node(boundary):
    surface = boundary[boundary["boundary_role"] == "surface"].copy()
    if surface.empty:
        raise ValueError("HYDRUS boundary has no surface nodes.")
    surface["radius"] = surface["x_cm"].abs()
    return surface.sort_values(["radius", "depth_cm", "node"]).iloc[0]


def _hydrus_calibrated_drip_radius_cm(project_name, *, fallback):
    name = str(project_name).casefold()
    if "drip2" in name or "sandy" in name:
        return 16.3
    if "drip1" in name or "loam" in name:
        return 39.7
    return float(fallback)


def _surface_drip_rate_l_h(atmos_text):
    if not atmos_text.strip():
        return 2.0
    lines = atmos_text.splitlines()
    header_index = next((i for i, line in enumerate(lines) if "tAtm" in line and "rt" in line), None)
    if header_index is None:
        return 2.0
    for line in lines[header_index + 1 :]:
        values = [float(value) for value in _number_tokens(line)]
        if len(values) >= 6 and values[5] > 0.0:
            return values[5] / 1000.0
    return 2.0


def _copy_base_run(base_run, run_dir):
    run_path = Path(run_dir)
    if run_path.exists():
        shutil.rmtree(run_path)
    shutil.copytree(
        base_run,
        run_path,
        ignore=shutil.ignore_patterns(
            "logs",
            "*.out",
            "*.g0*",
            "*.G0*",
            "MassBl.out",
            "MassBlRunOff.out",
            "MassBlMulch.out",
        ),
    )
    repo = Path(base_run).resolve().parents[2]
    build_output = repo / "build" / "maizsim" / "x64" / "Release"
    if (build_output / EXECUTABLE_NAME).is_file():
        shutil.copy2(build_output / EXECUTABLE_NAME, run_path / EXECUTABLE_NAME)
    if (build_output / DLL_NAME).is_file():
        shutil.copy2(build_output / DLL_NAME, run_path / DLL_NAME)
    if not (run_path / EXECUTABLE_NAME).is_file() or not (run_path / DLL_NAME).is_file():
        raise FileNotFoundError(f"Base run is missing {EXECUTABLE_NAME} or {DLL_NAME}: {base_run}")


def _run_model_checked(run_dir, *, timeout_seconds):
    result = run_model(run_dir, timeout_seconds=timeout_seconds)
    stdout = result.stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = result.stderr_path.read_text(encoding="utf-8", errors="replace")
    failure_markers = (
        "ORTHOMIN TERMINATES",
        "Traceback",
        "forrtl: severe",
        "Invalid drip",
        "Drip data error",
        "Sowing date cannot be earlier",
    )
    marker = next(
        (text for text in failure_markers if text.casefold() in (stdout + stderr).casefold()),
        None,
    )
    if not result.success or marker is not None:
        detail = marker or result.message
        raise RuntimeError(f"Aligned MAIZSIM run failed in {run_dir}: {detail}.")


def _final_date_time(g03_path):
    data = pd.read_csv(g03_path, skipinitialspace=True)
    data = data.rename(columns=lambda column: str(column).strip().strip(","))
    if "Date_time" not in data.columns:
        raise ValueError(f"G03 output lacks Date_time: {g03_path}")
    return float(pd.to_numeric(data["Date_time"], errors="raise").max())


def _resolve_repo_root(repo_root):
    if repo_root is not None:
        return Path(repo_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def main(arguments=None):
    args = _parse_args(arguments)
    outputs = run_hydrus_aligned_validation(
        project_file=args.project_file,
        project_dir=args.project_dir,
        workspace=args.workspace,
        output_dir=args.output_dir,
        repo_root=args.repo_root,
        prefix=args.prefix,
        wet_delta_threshold=args.wet_delta_threshold,
        emitter_rate_l_h=args.emitter_rate_l_h,
        timeout_seconds=args.timeout_seconds,
        drip_mode_override=args.drip_mode,
        drip_spread_mode=args.drip_spread_mode,
        drip_wet_width_max_cm=args.drip_wet_width_max_cm,
    )
    if arguments is None:
        print(json.dumps(outputs, indent=2))
    return 0


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description="Run same-condition MAIZSIM validation against an official HYDRUS SurfaceDrip project.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project-dir")
    source.add_argument("--project-file")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root")
    parser.add_argument("--prefix")
    parser.add_argument("--wet-delta-threshold", type=float, default=0.005)
    parser.add_argument("--emitter-rate-l-h", type=float)
    parser.add_argument("--drip-mode", type=int)
    parser.add_argument("--drip-spread-mode", type=int, default=5)
    parser.add_argument("--drip-wet-width-max-cm", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    return parser.parse_args(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
