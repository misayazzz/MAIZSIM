"""Export official HYDRUS project theta fields to CSV and validation figures."""

from __future__ import annotations

import argparse
import json
import re
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


HYDRUS_STORAGE_NAME = "Hydrus3D Files 1.00"
HYDRUS_REQUIRED_STREAMS = (
    "DIMENSIO.IN",
    "MESHTRIA.000",
    "th.out",
)


@dataclass(frozen=True)
class HydrusDimensions:
    """HYDRUS mesh dimensions needed for binary field parsing."""

    node_count: int
    element_count: int
    boundary_node_count: int
    material_count: int
    observation_node_count: int


@dataclass(frozen=True)
class HydrusMesh:
    """HYDRUS 2D mesh nodes and triangular element connectivity."""

    nodes: pd.DataFrame
    elements: pd.DataFrame


@dataclass(frozen=True)
class HydrusThetaOutput:
    """HYDRUS theta output frames."""

    times_h: np.ndarray
    theta: np.ndarray


@dataclass(frozen=True)
class HydrusOfficialProject:
    """Parsed official HYDRUS project data."""

    dimensions: HydrusDimensions
    mesh: HydrusMesh
    theta_output: HydrusThetaOutput
    selector_metadata: dict


def read_hydrus_dimensions_text(text):
    """Parse HYDRUS ``DIMENSIO.IN`` text."""
    lines = text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if "NumNPD" in line and "NumElD" in line
        ),
        None,
    )
    if header_index is None or header_index + 1 >= len(lines):
        raise ValueError("DIMENSIO.IN does not contain the NumNPD/NumElD header.")
    values = [int(value) for value in re.findall(r"[-+]?\d+", lines[header_index + 1])]
    if len(values) < 10:
        raise ValueError("DIMENSIO.IN dimension row is incomplete.")
    return HydrusDimensions(
        node_count=values[0],
        element_count=values[1],
        boundary_node_count=values[2],
        material_count=values[8],
        observation_node_count=values[9],
    )


def read_hydrus_dimensions(path):
    """Read HYDRUS dimensions from ``DIMENSIO.IN``."""
    return read_hydrus_dimensions_text(Path(path).read_text(encoding="utf-8"))


def read_hydrus_selector_text(text):
    """Parse the subset of ``SELECTOR.IN`` needed for validation manifests."""
    lines = text.splitlines()
    metadata: dict[str, object] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("LUnit") and index + 3 < len(lines):
            metadata["length_unit"] = lines[index + 1].strip()
            metadata["time_unit"] = lines[index + 2].strip()
            metadata["mass_unit"] = lines[index + 3].strip()
        elif stripped.startswith("Kat") and index + 1 < len(lines):
            values = _numbers(lines[index + 1])
            if values:
                metadata["kat"] = int(values[0])
        elif stripped.startswith("thr") and index + 1 < len(lines):
            values = _numbers(lines[index + 1])
            if len(values) >= 6:
                metadata["soil_hydraulic_parameters"] = {
                    "theta_r": values[0],
                    "theta_s": values[1],
                    "alpha_cm_inv": values[2],
                    "n": values[3],
                    "ks_cm_h": values[4],
                    "l": values[5],
                }
        elif stripped.startswith("tInit") and index + 1 < len(lines):
            values = _numbers(lines[index + 1])
            if len(values) >= 2:
                metadata["t_init_h"] = values[0]
                metadata["t_max_h"] = values[1]
        elif stripped.startswith("TPrint"):
            tprint: list[float] = []
            for later in lines[index + 1 :]:
                if later.strip().startswith("***"):
                    break
                tprint.extend(_numbers(later))
            metadata["t_print_h"] = tprint
    return metadata


def read_hydrus_mesh_bytes(data, dimensions, *, depth_reference_cm=None):
    """Parse HYDRUS ``MESHTRIA.000`` binary mesh bytes.

    The official project files store a short ``Pcp_File_Version`` prefix, then
    16-byte node records ``x, y, unused, unused`` and 12-byte triangular element
    records with one-based node ids.
    """
    dimensions = _coerce_dimensions(dimensions)
    prefix = b"Pcp_File_Version="
    if not data.startswith(prefix):
        raise ValueError("MESHTRIA.000 is missing the Pcp_File_Version prefix.")
    header_size = len(prefix) + 18
    node_count = dimensions.node_count
    element_count = dimensions.element_count
    expected_size = header_size + node_count * 16 + element_count * 12
    if len(data) < expected_size:
        raise ValueError(
            "MESHTRIA.000 is too small for the declared node/element counts: "
            f"{len(data)} < {expected_size}."
        )
    stored_node_count = int(np.frombuffer(data, dtype="<i4", count=1, offset=19)[0])
    stored_element_count = int(np.frombuffer(data, dtype="<i4", count=1, offset=27)[0])
    if stored_node_count != node_count or stored_element_count != element_count:
        raise ValueError(
            "MESHTRIA.000 counts do not match DIMENSIO.IN: "
            f"{stored_node_count}/{stored_element_count} vs "
            f"{node_count}/{element_count}."
        )

    node_offset = header_size
    raw_nodes = np.frombuffer(
        data,
        dtype="<f4",
        count=node_count * 4,
        offset=node_offset,
    ).reshape(node_count, 4)
    z_values = raw_nodes[:, 1].astype(float)
    surface_z = float(z_values.max()) if depth_reference_cm is None else float(depth_reference_cm)
    nodes = pd.DataFrame(
        {
            "node": np.arange(1, node_count + 1, dtype=int),
            "x_cm": raw_nodes[:, 0].astype(float),
            "z_cm": z_values,
            "y_cm": z_values,
            "depth_cm": surface_z - z_values,
        }
    )

    element_offset = node_offset + node_count * 16
    raw_elements = np.frombuffer(
        data,
        dtype="<i4",
        count=element_count * 3,
        offset=element_offset,
    ).reshape(element_count, 3)
    if raw_elements.min() < 1 or raw_elements.max() > node_count:
        raise ValueError("MESHTRIA.000 element connectivity references invalid nodes.")
    elements = pd.DataFrame(
        raw_elements,
        columns=["node1", "node2", "node3"],
    )
    elements.insert(0, "element", np.arange(1, element_count + 1, dtype=int))
    nodes["area_cm2"] = _nodal_areas(nodes, elements)
    return HydrusMesh(nodes=nodes, elements=elements)


def read_hydrus_mesh(path, dimensions, *, depth_reference_cm=None):
    """Read a HYDRUS binary mesh file."""
    return read_hydrus_mesh_bytes(
        Path(path).read_bytes(),
        dimensions,
        depth_reference_cm=depth_reference_cm,
    )


def read_hydrus_theta_output_bytes(data, node_count):
    """Parse HYDRUS ``th.out`` bytes as frames of ``time, theta_1..theta_n``."""
    node_count = int(node_count)
    values = np.frombuffer(data, dtype="<f4")
    frame_width = node_count + 1
    if values.size == 0 or values.size % frame_width != 0:
        raise ValueError(
            "th.out size is not divisible by node_count + 1: "
            f"{values.size} float32 values for {node_count} nodes."
        )
    frames = values.reshape((-1, frame_width)).astype(float, copy=True)
    times = frames[:, 0]
    theta = frames[:, 1:]
    if not np.all(np.isfinite(theta)):
        raise ValueError("th.out contains non-finite theta values.")
    if not np.all(np.diff(times) >= -1.0e-8):
        raise ValueError("th.out output times are not monotonic.")
    return HydrusThetaOutput(times_h=times, theta=theta)


def read_hydrus_theta_output(path, node_count):
    """Read a HYDRUS ``th.out`` file."""
    return read_hydrus_theta_output_bytes(Path(path).read_bytes(), node_count)


def read_official_project(project_dir=None, project_file=None):
    """Read an official HYDRUS project from an extracted directory or OLE file."""
    streams, project_name = read_official_project_streams(
        project_dir=project_dir,
        project_file=project_file,
    )
    dimensions = read_hydrus_dimensions_text(_decode_text(streams["DIMENSIO.IN"]))
    selector_metadata = {}
    if "SELECTOR.IN" in streams:
        selector_metadata = read_hydrus_selector_text(_decode_text(streams["SELECTOR.IN"]))
    selector_metadata.setdefault("project_name", project_name)
    mesh = read_hydrus_mesh_bytes(streams["MESHTRIA.000"], dimensions)
    theta_output = read_hydrus_theta_output_bytes(
        streams["th.out"],
        dimensions.node_count,
    )
    _validate_selector_times(theta_output, selector_metadata)
    if int(selector_metadata.get("kat", -1)) == 1:
        mesh.nodes["axisym_volume_cm3"] = _nodal_axisymmetric_volumes(
            mesh.nodes,
            mesh.elements,
        )
    return HydrusOfficialProject(
        dimensions=dimensions,
        mesh=mesh,
        theta_output=theta_output,
        selector_metadata=selector_metadata,
    )


def read_official_project_streams(project_dir=None, project_file=None):
    """Read raw HYDRUS project streams and return ``(streams, project_name)``."""
    if (project_dir is None) == (project_file is None):
        raise ValueError("Pass exactly one of project_dir or project_file.")
    if project_dir is not None:
        streams = _load_project_streams_from_dir(Path(project_dir))
        project_name = Path(project_dir).name
    else:
        streams = _load_project_streams_from_file(Path(project_file))
        project_name = Path(project_file).stem
    return streams, project_name


def theta_frame_dataframe(mesh, theta_output, time_h=None):
    """Return a node-level theta field at the nearest requested HYDRUS time."""
    index = nearest_time_index(theta_output.times_h, time_h)
    frame = mesh.nodes[["node", "x_cm", "depth_cm", "area_cm2"]].copy()
    if "z_cm" in mesh.nodes.columns:
        frame["z_cm"] = mesh.nodes["z_cm"]
    frame["time_h"] = float(theta_output.times_h[index])
    frame["theta"] = theta_output.theta[index]
    if "axisym_volume_cm3" in mesh.nodes.columns:
        frame["axisym_volume_cm3"] = mesh.nodes["axisym_volume_cm3"]
    columns = ["node", "time_h", "x_cm"]
    if "z_cm" in frame.columns:
        columns.append("z_cm")
    columns.extend(["depth_cm", "theta", "area_cm2"])
    if "axisym_volume_cm3" in frame.columns:
        columns.append("axisym_volume_cm3")
    return frame[columns]


def nearest_time_index(times_h, time_h=None):
    """Find the nearest HYDRUS frame index."""
    times = np.asarray(times_h, dtype=float)
    if time_h is None:
        return int(len(times) - 1)
    return int(np.abs(times - float(time_h)).argmin())


def hydrus_shape_metrics(mesh, theta_output, *, output_time_h=None, baseline_time_h=0.0, wet_delta_threshold=0.005):
    """Summarize HYDRUS 2D wetting-body shape metrics."""
    output_index = nearest_time_index(theta_output.times_h, output_time_h)
    baseline_index = nearest_time_index(theta_output.times_h, baseline_time_h)
    delta = theta_output.theta[output_index] - theta_output.theta[baseline_index]
    nodes = mesh.nodes
    wet = delta >= float(wet_delta_threshold)
    areas = nodes["area_cm2"].to_numpy(dtype=float)
    x = nodes["x_cm"].to_numpy(dtype=float)
    depth = nodes["depth_cm"].to_numpy(dtype=float)
    peak_index = int(np.argmax(delta))
    return {
        "baseline_time_h": float(theta_output.times_h[baseline_index]),
        "output_time_h": float(theta_output.times_h[output_index]),
        "wet_delta_threshold": float(wet_delta_threshold),
        "cross_section_area_cm2": float(areas.sum()),
        "triangle_count": int(len(mesh.elements)),
        "theta_initial_min": float(theta_output.theta[baseline_index].min()),
        "theta_initial_max": float(theta_output.theta[baseline_index].max()),
        "theta_output_min": float(theta_output.theta[output_index].min()),
        "theta_output_max": float(theta_output.theta[output_index].max()),
        "delta_theta_min": float(delta.min()),
        "delta_theta_max": float(delta.max()),
        "delta_theta_mean": float(np.average(delta, weights=areas)),
        "wet_node_count": int(wet.sum()),
        "wet_area_cm2": float(areas[wet].sum()) if wet.any() else 0.0,
        "wet_width_cm": _span(x[wet]) if wet.any() else 0.0,
        "wet_depth_cm": float(depth[wet].max()) if wet.any() else 0.0,
        "peak_delta_x_cm": float(x[peak_index]),
        "peak_delta_depth_cm": float(depth[peak_index]),
        "peak_delta_theta": float(delta[peak_index]),
    }


def write_official_project_outputs(
    project,
    output_dir,
    *,
    prefix="hydrus_official",
    output_time_h=None,
    baseline_time_h=0.0,
    wet_delta_threshold=0.005,
    drip_x_cm=0.0,
):
    """Write HYDRUS node CSVs, summary metrics, and a 2D field figure."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    baseline = theta_frame_dataframe(project.mesh, project.theta_output, baseline_time_h)
    output = theta_frame_dataframe(project.mesh, project.theta_output, output_time_h)
    baseline_path = output_path / f"{prefix}_theta_baseline.csv"
    output_csv_path = output_path / f"{prefix}_theta_output.csv"
    mesh_nodes_path = output_path / f"{prefix}_mesh_nodes.csv"
    mesh_elements_path = output_path / f"{prefix}_mesh_elements.csv"
    summary_path = output_path / f"{prefix}_summary.csv"
    figure_path = output_path / f"{prefix}_hydrus_fields.png"
    manifest_path = output_path / f"{prefix}_hydrus_manifest.json"
    index_path = output_path / f"{prefix}_outputs.json"

    baseline.to_csv(baseline_path, index=False)
    output.to_csv(output_csv_path, index=False)
    project.mesh.nodes.to_csv(mesh_nodes_path, index=False)
    project.mesh.elements.to_csv(mesh_elements_path, index=False)
    metrics = hydrus_shape_metrics(
        project.mesh,
        project.theta_output,
        output_time_h=output_time_h,
        baseline_time_h=baseline_time_h,
        wet_delta_threshold=wet_delta_threshold,
    )
    pd.DataFrame([metrics]).to_csv(summary_path, index=False)
    plot_hydrus_field_plate(
        project.mesh,
        project.theta_output,
        figure_path,
        output_time_h=output_time_h,
        baseline_time_h=baseline_time_h,
        drip_x_cm=drip_x_cm,
    )
    manifest = {
        "dimensions": project.dimensions.__dict__,
        "selector_metadata": project.selector_metadata,
        "shape_metrics": metrics,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    outputs = {
        "baseline_csv": str(baseline_path),
        "output_csv": str(output_csv_path),
        "mesh_nodes_csv": str(mesh_nodes_path),
        "mesh_elements_csv": str(mesh_elements_path),
        "summary_csv": str(summary_path),
        "figure": str(figure_path),
        "hydrus_manifest_json": str(manifest_path),
    }
    index_path.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    return outputs


def plot_hydrus_field_plate(
    mesh,
    theta_output,
    path,
    *,
    output_time_h=None,
    baseline_time_h=0.0,
    drip_x_cm=0.0,
):
    """Render initial theta, output theta, and delta-theta HYDRUS fields."""
    output_index = nearest_time_index(theta_output.times_h, output_time_h)
    baseline_index = nearest_time_index(theta_output.times_h, baseline_time_h)
    initial = theta_output.theta[baseline_index]
    final = theta_output.theta[output_index]
    delta = final - initial
    theta_min = float(min(initial.min(), final.min()))
    theta_max = float(max(initial.max(), final.max()))
    delta_limit = max(abs(float(delta.min())), abs(float(delta.max())), 0.001)

    fields = (
        (initial, f"theta t={theta_output.times_h[baseline_index]:g} h", "viridis", theta_min, theta_max),
        (final, f"theta t={theta_output.times_h[output_index]:g} h", "viridis", theta_min, theta_max),
        (delta, "delta theta", "RdBu_r", -delta_limit, delta_limit),
    )
    triangulation = mtri.Triangulation(
        mesh.nodes["x_cm"].to_numpy(dtype=float),
        mesh.nodes["depth_cm"].to_numpy(dtype=float),
        triangles=mesh.elements[["node1", "node2", "node3"]].to_numpy(dtype=int) - 1,
    )
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(7.2, 2.45),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    for ax, (values, title, cmap, vmin, vmax) in zip(axes, fields):
        contour = ax.tricontourf(
            triangulation,
            values,
            levels=np.linspace(vmin, vmax, 17),
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            extend="both",
        )
        _annotate_drip(ax, mesh, drip_x_cm)
        ax.set_title(title, fontsize=7, pad=2)
        ax.set_xlabel("x (cm)")
        ax.invert_yaxis()
        fig.colorbar(contour, ax=ax, shrink=0.78, pad=0.015)
    axes[0].set_ylabel("Depth (cm)")
    fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def main(arguments=None):
    """Command-line entry point."""
    args = _parse_args(arguments)
    project = read_official_project(
        project_dir=args.project_dir,
        project_file=args.project_file,
    )
    prefix = args.prefix
    if prefix is None:
        prefix = project.selector_metadata.get("project_name", "hydrus_official")
    outputs = write_official_project_outputs(
        project,
        args.output_dir,
        prefix=str(prefix),
        output_time_h=args.output_time_h,
        baseline_time_h=args.baseline_time_h,
        wet_delta_threshold=args.wet_delta_threshold,
        drip_x_cm=args.drip_x_cm,
    )
    if arguments is None:
        print(json.dumps(outputs, indent=2))
    return 0


def _load_project_streams_from_dir(project_dir):
    streams = {}
    names = HYDRUS_REQUIRED_STREAMS + ("SELECTOR.IN", "BOUNDARY.IN")
    for stream_name in names:
        path = _find_stream_file(project_dir, stream_name)
        if path is not None:
            streams[stream_name] = path.read_bytes()
    missing = [name for name in HYDRUS_REQUIRED_STREAMS if name not in streams]
    if missing:
        raise FileNotFoundError(f"Missing HYDRUS stream files in {project_dir}: {missing}")
    return streams


def _load_project_streams_from_file(project_file):
    try:
        import pythoncom
        from win32com import storagecon
    except ImportError as exc:
        raise ImportError(
            "Reading HYDRUS OLE project files requires the existing pywin32 "
            "dependency. Use --project-dir with extracted files if unavailable."
        ) from exc

    mode = storagecon.STGM_READ | storagecon.STGM_SHARE_EXCLUSIVE
    storage = pythoncom.StgOpenStorage(str(project_file), None, mode)
    hydrus_storage = storage.OpenStorage(HYDRUS_STORAGE_NAME, None, mode)
    streams = {}
    for stream_name in HYDRUS_REQUIRED_STREAMS + ("SELECTOR.IN", "BOUNDARY.IN"):
        try:
            stream = hydrus_storage.OpenStream(stream_name, None, mode)
        except Exception:
            if stream_name in HYDRUS_REQUIRED_STREAMS:
                raise
            continue
        streams[stream_name] = _read_ole_stream(stream)
    return streams


def _read_ole_stream(stream):
    data = bytearray()
    while True:
        chunk = stream.Read(65536)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _find_stream_file(project_dir, stream_name):
    normalized = stream_name.casefold()
    for path in Path(project_dir).rglob("*"):
        if not path.is_file():
            continue
        name = path.name.casefold()
        if name == normalized or name.endswith(f"__{normalized}"):
            return path
    return None


def _decode_text(data):
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _validate_selector_times(theta_output, selector_metadata):
    t_print = selector_metadata.get("t_print_h")
    if not t_print:
        return
    expected = np.asarray([0.0, *t_print], dtype=float)
    if len(expected) != len(theta_output.times_h):
        raise ValueError(
            "th.out frame count does not match SELECTOR.IN TPrint count: "
            f"{len(theta_output.times_h)} vs {len(expected)}."
        )
    if not np.allclose(theta_output.times_h, expected, rtol=0.0, atol=1.0e-5):
        raise ValueError("th.out output times do not match SELECTOR.IN TPrint.")


def _numbers(line):
    return [float(value) for value in re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?", line)]


def _coerce_dimensions(dimensions):
    if isinstance(dimensions, HydrusDimensions):
        return dimensions
    if isinstance(dimensions, dict):
        return HydrusDimensions(**dimensions)
    raise TypeError("dimensions must be HydrusDimensions or a matching dict.")


def _nodal_areas(nodes, elements):
    xy = nodes[["x_cm", "depth_cm"]].to_numpy(dtype=float)
    conn = elements[["node1", "node2", "node3"]].to_numpy(dtype=int) - 1
    areas = np.zeros(len(nodes), dtype=float)
    for tri in conn:
        p0, p1, p2 = xy[tri]
        edge1 = p1 - p0
        edge2 = p2 - p0
        area = 0.5 * abs(edge1[0] * edge2[1] - edge1[1] * edge2[0])
        areas[tri] += area / 3.0
    if not np.all(areas > 0.0):
        raise ValueError("Computed non-positive nodal areas from HYDRUS mesh.")
    return areas


def _nodal_axisymmetric_volumes(nodes, elements):
    xy = nodes[["x_cm", "depth_cm"]].to_numpy(dtype=float)
    conn = elements[["node1", "node2", "node3"]].to_numpy(dtype=int) - 1
    volumes = np.zeros(len(nodes), dtype=float)
    for tri in conn:
        p0, p1, p2 = xy[tri]
        edge1 = p1 - p0
        edge2 = p2 - p0
        area = 0.5 * abs(edge1[0] * edge2[1] - edge1[1] * edge2[0])
        radius = float(np.mean(xy[tri, 0]))
        volume = 2.0 * np.pi * radius * area
        volumes[tri] += volume / 3.0
    if not np.all(volumes >= 0.0):
        raise ValueError("Computed negative axisymmetric nodal volumes.")
    return volumes


def _span(values):
    if len(values) == 0:
        return 0.0
    return float(np.max(values) - np.min(values))


def _annotate_drip(ax, mesh, drip_x_cm):
    surface_depth = float(mesh.nodes["depth_cm"].min())
    max_depth = float(mesh.nodes["depth_cm"].max())
    drip_x = float(drip_x_cm)
    ax.axvline(drip_x, color="#d62728", linestyle="--", linewidth=0.8)
    ax.scatter(
        [drip_x],
        [surface_depth],
        marker="v",
        s=20,
        color="#d62728",
        zorder=5,
    )
    ax.text(
        drip_x + 0.02 * max(1.0, float(mesh.nodes["x_cm"].max())),
        surface_depth + 0.04 * max(1.0, max_depth - surface_depth),
        "drip",
        color="#d62728",
        fontsize=6,
        ha="left",
        va="top",
    )


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description="Export official HYDRUS theta fields to CSV and 2D figures.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project-dir", help="Directory containing extracted HYDRUS streams.")
    source.add_argument("--project-file", help="HYDRUS .h3d3/.hyd5 OLE project file.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix")
    parser.add_argument("--output-time-h", type=float)
    parser.add_argument("--baseline-time-h", type=float, default=0.0)
    parser.add_argument("--wet-delta-threshold", type=float, default=0.005)
    parser.add_argument("--drip-x-cm", type=float, default=0.0)
    return parser.parse_args(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
