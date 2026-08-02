from pathlib import Path

import pytest

from da_framework.hutd06_grid_refinement import refine_hutd06_grid


BASE_RUN = (
    Path(__file__).resolve().parents[1] / "base_runs" / "HUTD06"
)
EXPECTED_AREAS = {
    1: 562.5,
    2: 562.5,
    3: 1162.5,
    4: 1125.0,
    5: 1162.5,
    6: 1125.0,
    7: 1087.5,
}


@pytest.mark.parametrize(
    (
        "level",
        "x_count",
        "y_count",
        "nodes",
        "elements",
        "boundaries",
        "band",
        "emitter_node",
    ),
    (
        (0, 10, 52, 520, 459, 20, 12, 2),
        (1, 19, 76, 1444, 1350, 38, 21, 3),
        (2, 37, 124, 4588, 4428, 74, 39, 5),
    ),
)
def test_refinement_preserves_hutd06_contract(
    tmp_path,
    level,
    x_count,
    y_count,
    nodes,
    elements,
    boundaries,
    band,
    emitter_node,
):
    output_grid = tmp_path / "HUTD06.grd"
    output_nod = tmp_path / "HUTD06.nod"
    result = refine_hutd06_grid(
        BASE_RUN / "HUTD06.grd",
        BASE_RUN / "HUTD06.nod",
        output_grid,
        output_nod,
        level=level,
    )

    assert result["x_node_count"] == x_count
    assert result["y_node_count"] == y_count
    assert result["node_count"] == nodes
    assert result["element_count"] == elements
    assert result["boundary_count"] == boundaries
    assert result["solver_bandwidth"] == band
    assert result["emitter_node"] == emitter_node
    assert result["emitter_x_cm"] == pytest.approx(0.75)
    assert result["domain_width_cm"] == pytest.approx(37.5)
    assert result["material_areas_cm2"] == pytest.approx(EXPECTED_AREAS)

    grid_lines = output_grid.read_text(encoding="utf-8").splitlines()
    assert grid_lines[4].split()[:4] == ["1", "0", "183", "1"]
    emitter_row = grid_lines[3 + emitter_node].split()
    assert emitter_row[:4] == [
        str(emitter_node),
        "0.75",
        "183",
        "1",
    ]
    boundary_header = next(
        index
        for index, line in enumerate(grid_lines)
        if "Boundary geometry information" in line
    )
    boundary_rows = [
        line.split()
        for line in grid_lines[
            boundary_header + 2 : boundary_header + 2 + boundaries
        ]
    ]
    assert {tuple(row[1:5]) for row in boundary_rows[:x_count]} == {
        ("-4", "0", "-4", "-4")
    }
    assert {tuple(row[1:5]) for row in boundary_rows[x_count:]} == {
        ("-7", "0", "1", "1")
    }
    assert sum(float(row[5]) for row in boundary_rows[:x_count]) == pytest.approx(
        37.5
    )
    assert sum(float(row[5]) for row in boundary_rows[x_count:]) == pytest.approx(
        37.5
    )
    assert grid_lines[grid_lines.index("NSeep") + 1].strip() == "0"
    assert grid_lines[grid_lines.index("NDrain") + 1].strip() == "0"

    nod_rows = [
        line.split()
        for line in output_nod.read_text(encoding="utf-8").splitlines()[2:]
        if line.split()
    ]
    assert len(nod_rows) == nodes
    assert nod_rows[0][1:] == [
        "150.34",
        "1656.78",
        "0",
        "0",
        "0",
        "0",
        "0",
        "4.5",
        "23",
        "-300",
        "400",
        "206000",
        "0",
        "0",
    ]


@pytest.mark.parametrize(
    ("level", "x_count", "y_count", "nodes", "elements", "band", "emitter_node"),
    (
        (0, 13, 52, 676, 612, 15, 2),
        (1, 23, 72, 1656, 1562, 25, 3),
        (2, 43, 112, 4816, 4662, 45, 5),
    ),
)
def test_extended_validation_domain_fits_solver_limits(
    tmp_path,
    level,
    x_count,
    y_count,
    nodes,
    elements,
    band,
    emitter_node,
):
    result = refine_hutd06_grid(
        BASE_RUN / "HUTD06.grd",
        BASE_RUN / "HUTD06.nod",
        tmp_path / "HUTD06.grd",
        tmp_path / "HUTD06.nod",
        level=level,
        domain_width_cm=75.0,
        refined_x_max_cm=50.0,
        refined_y_min_cm=137.5,
    )

    assert result["x_node_count"] == x_count
    assert result["y_node_count"] == y_count
    assert result["node_count"] == nodes
    assert result["element_count"] == elements
    assert result["boundary_count"] == 2 * x_count
    assert result["solver_bandwidth"] == band
    assert result["emitter_node"] == emitter_node
    assert result["domain_width_cm"] == pytest.approx(75.0)
    assert result["actual_refined_x_max_cm"] == pytest.approx(50.0)
    assert result["actual_refined_y_min_cm"] == pytest.approx(137.5)
    assert result["material_areas_cm2"] == pytest.approx(
        {material: 2.0 * area for material, area in EXPECTED_AREAS.items()}
    )

    nod_rows = [
        line.split()
        for line in (tmp_path / "HUTD06.nod")
        .read_text(encoding="utf-8")
        .splitlines()[2:]
        if line.split()
    ]
    assert nod_rows[x_count - 1][1:] == nod_rows[9][1:]


def test_refinement_rejects_unregistered_level(tmp_path):
    with pytest.raises(ValueError, match="level"):
        refine_hutd06_grid(
            BASE_RUN / "HUTD06.grd",
            BASE_RUN / "HUTD06.nod",
            tmp_path / "HUTD06.grd",
            tmp_path / "HUTD06.nod",
            level=3,
        )
