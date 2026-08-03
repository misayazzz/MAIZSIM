"""Nested HUTD06 half-domain grids with the drip line on the x=0 axis."""

from __future__ import annotations

import math
from pathlib import Path


EMITTER_X_CM = 0.0
REFINED_X_MAX_CM = 37.5
# Absolute grid elevation: the HUTD06 surface is y=183 cm, so this refines
# the upper 61 cm and leaves a buffer below the 30 mm event wetting front.
REFINED_Y_MIN_CM = 122.0
MAX_NODES = 5000
MAX_ELEMENTS = 5000
MAX_BOUNDARIES = 600
MAX_BANDWIDTH = 64


def refine_hutd06_grid(
    source_grid,
    source_nod,
    output_grid,
    output_nod,
    *,
    level,
    domain_width_cm=None,
    refined_x_max_cm=REFINED_X_MAX_CM,
    refined_y_min_cm=REFINED_Y_MIN_CM,
):
    """Write one nested HUTD06 grid for ``level`` 0, 1, or 2."""
    refinement_level = int(level)
    if refinement_level not in (0, 1, 2):
        raise ValueError("HUTD06 refinement level must be 0, 1, or 2")
    factor = 2**refinement_level
    profile = _read_hutd06_grid(source_grid)
    nod_header, nod_values = _read_nod(source_nod, profile["node_count"])
    old_x = profile["x_values"]
    old_y = profile["y_values"]
    target_width = (
        old_x[-1] - old_x[0]
        if domain_width_cm is None
        else float(domain_width_cm)
    )
    if target_width < old_x[-1] - old_x[0] - 1.0e-12:
        raise ValueError("Expanded HUTD06 domain cannot be narrower than the source")
    extended_x = _extended_x_coordinates(old_x, target_width)
    requested_refined_x_max = float(refined_x_max_cm)
    requested_refined_y_min = float(refined_y_min_cm)
    if not EMITTER_X_CM <= requested_refined_x_max <= extended_x[-1]:
        raise ValueError("refined_x_max_cm must include the emitter and lie in-domain")
    if not old_y[-1] <= requested_refined_y_min <= old_y[0]:
        raise ValueError("refined_y_min_cm must lie inside the vertical domain")
    new_x = _refined_coordinates(
        extended_x,
        factor=factor,
        refine_interval=lambda left, right: (
            left >= old_x[0] and right <= requested_refined_x_max
        ),
    )
    new_y = _refined_coordinates(
        old_y,
        factor=factor,
        refine_interval=lambda top, bottom: (
            top >= requested_refined_y_min
            and bottom >= requested_refined_y_min
        ),
    )
    x_count = len(new_x)
    y_count = len(new_y)
    node_count = x_count * y_count
    element_count = (x_count - 1) * (y_count - 1)
    boundary_count = 2 * x_count
    solver_bandwidth = x_count + 2
    if node_count > MAX_NODES:
        raise ValueError(f"Refined node count {node_count} exceeds {MAX_NODES}")
    if element_count > MAX_ELEMENTS:
        raise ValueError(
            f"Refined element count {element_count} exceeds {MAX_ELEMENTS}"
        )
    if boundary_count > MAX_BOUNDARIES:
        raise ValueError(
            f"Refined boundary count {boundary_count} exceeds {MAX_BOUNDARIES}"
        )
    if solver_bandwidth > MAX_BANDWIDTH:
        raise ValueError(
            f"Refined bandwidth {solver_bandwidth} exceeds {MAX_BANDWIDTH}"
        )
    emitter_matches = [
        index + 1
        for index, x_value in enumerate(new_x)
        if abs(x_value - EMITTER_X_CM) <= 1.0e-12
    ]
    if len(emitter_matches) != 1:
        raise AssertionError("Emitter x=0 cm must remain exactly one surface node")
    emitter_node = emitter_matches[0]

    row_materials = [
        _material_for_y(y_value, profile) for y_value in new_y
    ]
    grid_lines = _render_grid(
        profile,
        new_x,
        new_y,
        row_materials,
    )
    nod_lines = _render_nod(
        nod_header,
        nod_values,
        old_x,
        old_y,
        new_x,
        new_y,
    )
    Path(output_grid).write_text(
        "\n".join(grid_lines) + "\n",
        encoding="utf-8",
    )
    Path(output_nod).write_text(
        "\n".join(nod_lines) + "\n",
        encoding="utf-8",
    )

    original_areas = _material_areas(
        old_x,
        old_y,
        profile["row_materials"],
    )
    refined_areas = _material_areas(new_x, new_y, row_materials)
    area_scale = (new_x[-1] - new_x[0]) / (old_x[-1] - old_x[0])
    for material, original_area in original_areas.items():
        expected_area = original_area * area_scale
        if abs(refined_areas.get(material, 0.0) - expected_area) > 1.0e-8:
            raise AssertionError(
                f"Material {material} thickness changed during refinement"
            )
    widths = _surface_widths(new_x)
    domain_width = new_x[-1] - new_x[0]
    if abs(sum(widths) - domain_width) > 1.0e-10:
        raise AssertionError("Surface control widths do not close")
    return {
        "level": refinement_level,
        "factor": factor,
        "x_node_count": x_count,
        "y_node_count": y_count,
        "node_count": node_count,
        "element_count": element_count,
        "boundary_count": boundary_count,
        "solver_bandwidth": solver_bandwidth,
        "emitter_node": emitter_node,
        "emitter_x_cm": EMITTER_X_CM,
        "domain_width_cm": domain_width,
        "surface_y_cm": new_y[0],
        "bottom_y_cm": new_y[-1],
        "requested_refined_x_max_cm": requested_refined_x_max,
        "actual_refined_x_max_cm": max(
            value for value in new_x if value <= requested_refined_x_max + 1.0e-12
        ),
        "requested_refined_y_min_cm": requested_refined_y_min,
        "actual_refined_y_min_cm": min(
            value for value in new_y if value >= requested_refined_y_min - 1.0e-12
        ),
        "material_areas_cm2": refined_areas,
    }


def _read_hutd06_grid(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    count_header = next(
        index
        for index, line in enumerate(lines)
        if "KAT" in line and "NumNP" in line
    )
    counts = [int(value) for value in lines[count_header + 1].split()[:6]]
    kat, node_count, element_count, boundary_count, x_count, num_mat = counts
    if kat != 2 or num_mat != 7:
        raise ValueError("Expected the seven-material KAT=2 HUTD06 grid")
    node_header = next(
        index
        for index, line in enumerate(lines)
        if "MatNum" in line and "x" in line and "y" in line
    )
    node_rows = [
        line.split()
        for line in lines[node_header + 1 : node_header + 1 + node_count]
    ]
    nodes = [
        {
            "node": int(parts[0]),
            "x": float(parts[1]),
            "y": float(parts[2]),
            "material": int(parts[3]),
        }
        for parts in node_rows
    ]
    if [item["node"] for item in nodes] != list(range(1, node_count + 1)):
        raise ValueError("HUTD06 nodes must be sequential")
    if node_count % x_count:
        raise ValueError("HUTD06 node count is not divisible by IJ")
    y_count = node_count // x_count
    if element_count != (x_count - 1) * (y_count - 1):
        raise ValueError("HUTD06 element count is not structured")
    if boundary_count != 2 * x_count:
        raise ValueError("Expected surface and bottom boundary rows")
    x_values = [nodes[index]["x"] for index in range(x_count)]
    y_values = []
    row_materials = []
    for row_index in range(y_count):
        row = nodes[row_index * x_count : (row_index + 1) * x_count]
        if [item["x"] for item in row] != x_values:
            raise ValueError("HUTD06 x coordinates differ between rows")
        if len({item["y"] for item in row}) != 1:
            raise ValueError("HUTD06 rows must have constant y")
        if len({item["material"] for item in row}) != 1:
            raise ValueError("HUTD06 rows must have one material")
        y_values.append(row[0]["y"])
        row_materials.append(row[0]["material"])
    if any(right <= left for left, right in zip(x_values, x_values[1:])):
        raise ValueError("HUTD06 x coordinates must increase")
    if any(bottom >= top for top, bottom in zip(y_values, y_values[1:])):
        raise ValueError("HUTD06 y coordinates must decrease")

    boundary_header = next(
        index
        for index, line in enumerate(lines)
        if "Boundary geometry information" in line
    )
    boundary_rows = [
        line.split()
        for line in lines[
            boundary_header + 2 : boundary_header + 2 + boundary_count
        ]
    ]
    surface_codes = {tuple(row[1:5]) for row in boundary_rows[:x_count]}
    bottom_codes = {tuple(row[1:5]) for row in boundary_rows[x_count:]}
    if surface_codes != {("-4", "0", "-4", "-4")}:
        raise ValueError("Unexpected HUTD06 surface boundary codes")
    if bottom_codes != {("-7", "0", "1", "1")}:
        raise ValueError("Unexpected HUTD06 bottom boundary codes")
    nseep_index = next(
        index for index, line in enumerate(lines) if line.strip() == "NSeep"
    )
    ndrain_index = next(
        index for index, line in enumerate(lines) if line.strip() == "NDrain"
    )
    if int(lines[nseep_index + 1]) != 0 or int(lines[ndrain_index + 1]) != 0:
        raise ValueError("Expected NSeep=0 and NDrain=0")
    return {
        "kat": kat,
        "num_mat": num_mat,
        "node_count": node_count,
        "x_count": x_count,
        "y_count": y_count,
        "x_values": x_values,
        "y_values": y_values,
        "row_materials": row_materials,
    }


def _read_nod(path, expected_nodes):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header = lines[:2]
    records = []
    for line in lines[2:]:
        parts = line.split()
        if parts:
            records.append([float(value) for value in parts])
    if len(records) != expected_nodes:
        raise ValueError(
            f"Nodal record count {len(records)} does not match {expected_nodes}"
        )
    if [int(row[0]) for row in records] != list(
        range(1, expected_nodes + 1)
    ):
        raise ValueError("HUTD06 nodal records must be sequential")
    return header, records


def _refined_coordinates(values, *, factor, refine_interval):
    refined = []
    for left, right in zip(values[:-1], values[1:]):
        subdivisions = factor if refine_interval(left, right) else 1
        refined.extend(
            left + (right - left) * step / subdivisions
            for step in range(subdivisions)
        )
    refined.append(values[-1])
    return refined


def _extended_x_coordinates(values, target_width):
    domain_start = float(values[0])
    target_end = domain_start + float(target_width)
    if target_end <= values[-1] + 1.0e-12:
        return list(values)
    outer_spacing = values[-1] - values[-2]
    interval_count = max(
        1,
        math.ceil((target_end - values[-1]) / (1.1 * outer_spacing)),
    )
    extension_spacing = (target_end - values[-1]) / interval_count
    return list(values) + [
        values[-1] + extension_spacing * step
        for step in range(1, interval_count + 1)
    ]


def _material_for_y(y_value, profile):
    old_y = profile["y_values"]
    old_materials = profile["row_materials"]
    for index, old_value in enumerate(old_y):
        if abs(y_value - old_value) <= 1.0e-10:
            return old_materials[index]
    for index, (top, bottom) in enumerate(zip(old_y[:-1], old_y[1:])):
        if top > y_value > bottom:
            return old_materials[index + 1]
    raise ValueError(f"Refined y coordinate {y_value:g} is outside HUTD06")


def _render_grid(profile, x_values, y_values, row_materials):
    x_count = len(x_values)
    y_count = len(y_values)
    node_count = x_count * y_count
    element_count = (x_count - 1) * (y_count - 1)
    lines = [
        "***************** GRID GENERATOR INFORMATION **********************************************",
        "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
        (
            f"  {profile['kat']}     {node_count}     {element_count}     "
            f"{2 * x_count}     {x_count}     {profile['num_mat']}"
        ),
        "   n           x          y      MatNum",
    ]
    node = 1
    for y_value, material in zip(y_values, row_materials):
        for x_value in x_values:
            lines.append(
                f"\t{node}\t{x_value:.10g}\t{y_value:.10g}\t{material}"
            )
            node += 1
    lines.extend(
        [
            "***************** ELEMENT INFORMATION ******************************************************",
            "         e         i         j         k         l     MatNumE",
        ]
    )
    element = 1
    for row_index in range(y_count - 1):
        material = row_materials[row_index + 1]
        for column_index in range(x_count - 1):
            top_left = row_index * x_count + column_index + 1
            bottom_left = top_left + x_count
            lines.append(
                f"\t{element}\t{top_left}\t{bottom_left}\t"
                f"{bottom_left + 1}\t{top_left + 1}\t{material}"
            )
            element += 1
    lines.extend(
        [
            "****************Boundary geometry information**************************************",
            "    n  CodeW  CodeC  CodeH  CodeG  Width",
        ]
    )
    widths = _surface_widths(x_values)
    for node, width in enumerate(widths, start=1):
        lines.append(f"    {node} -4    0     -4    -4      {width:.10g}")
    bottom_start = (y_count - 1) * x_count + 1
    for offset, width in enumerate(widths):
        lines.append(
            f"  {bottom_start + offset}   -7   0       1         1      "
            f"{width:.10g}"
        )
    lines.extend(
        [
            "***************************Seepage face information********************************************",
            "NSeep",
            "  0",
            "***************************Drainage Boundaries******************************************",
            "NDrain",
            "0",
        ]
    )
    return lines


def _render_nod(header, records, old_x, old_y, new_x, new_y):
    field_count = len(records[0]) - 1
    old_x_count = len(old_x)
    lines = list(header)
    node = 1
    for y_value in new_y:
        top, bottom, y_weight = _axis_interval(old_y, y_value)
        for x_value in new_x:
            left, right, x_weight = _axis_interval(
                old_x,
                x_value,
                clamp_outside=True,
            )
            values = []
            for field in range(1, field_count + 1):
                top_left = records[top * old_x_count + left][field]
                top_right = records[top * old_x_count + right][field]
                bottom_left = records[bottom * old_x_count + left][field]
                bottom_right = records[bottom * old_x_count + right][field]
                top_value = top_left + x_weight * (top_right - top_left)
                bottom_value = (
                    bottom_left + x_weight * (bottom_right - bottom_left)
                )
                values.append(top_value + y_weight * (bottom_value - top_value))
            lines.append(
                "\t"
                + "\t".join(
                    [str(node)] + [f"{value:.10g}" for value in values]
                )
            )
            node += 1
    return lines


def _axis_interval(values, target, *, clamp_outside=False):
    for index, value in enumerate(values):
        if abs(target - value) <= 1.0e-10:
            return index, index, 0.0
    increasing = values[-1] > values[0]
    for index, (first, second) in enumerate(zip(values[:-1], values[1:])):
        inside = first < target < second if increasing else first > target > second
        if inside:
            return index, index + 1, (target - first) / (second - first)
    if clamp_outside:
        if increasing and target > values[-1]:
            return len(values) - 1, len(values) - 1, 0.0
        if not increasing and target < values[-1]:
            return len(values) - 1, len(values) - 1, 0.0
    raise ValueError(f"Coordinate {target:g} is outside interpolation axis")


def _surface_widths(x_values):
    widths = []
    for index, x_value in enumerate(x_values):
        if index == 0:
            widths.append(0.5 * (x_values[1] - x_value))
        elif index == len(x_values) - 1:
            widths.append(0.5 * (x_value - x_values[index - 1]))
        else:
            widths.append(0.5 * (x_values[index + 1] - x_values[index - 1]))
    return widths


def _material_areas(x_values, y_values, row_materials):
    width = x_values[-1] - x_values[0]
    areas = {}
    for row_index, (top, bottom) in enumerate(zip(y_values[:-1], y_values[1:])):
        material = row_materials[row_index + 1]
        areas[material] = areas.get(material, 0.0) + width * (top - bottom)
    return areas
