from pathlib import Path

import pandas as pd
import pytest

try:
    from . import context  # noqa: F401
except ImportError:
    import context  # noqa: F401

from da_framework.mode6_30mm_validation import _set_water_solver_controls
from da_framework.mode6_30mm_validation import _select_soils
from da_framework.mode6_30mm_validation import _validate_results
from da_framework.mode6_30mm_validation import _water_balance_metrics
from da_framework.mode6_30mm_validation import _wetting_shape
from da_framework.mode6_30mm_validation import _write_drip_file
from da_framework.mode6_30mm_validation import _write_homogeneous_soil
from da_framework.mode6_30mm_validation import three_grid_gci
from da_framework.mode6_30mm_validation import wetting_geometry_from_field
from da_framework.drip_regression import DEFAULT_SOILS


def test_default_soils_preserve_hutd06_near_saturation_bridge(tmp_path):
    for soil in DEFAULT_SOILS:
        assert soil.kk == pytest.approx(0.9 * soil.ks)
        assert soil.thk == pytest.approx(soil.ths - 0.004)
        path = tmp_path / f"{soil.name}.soi"
        _write_homogeneous_soil(path, soil, material_count=7)
        assert len(path.read_text(encoding="utf-8").splitlines()) == 9


def test_set_water_solver_controls_updates_scientific_tolerances(tmp_path):
    path = tmp_path / "WaterMovDefault.dat"
    path.write_text(
        "header\n"
        "MaxIt TolTh TolH hCritA hCritS DtMx htab1 htabN heat solute\n"
        "20 0.01 0.05 -1e5 1e-3 0.02 0.001 1000 0.5 0.5\n",
        encoding="utf-8",
    )

    _set_water_solver_controls(
        path,
        max_iterations=200,
        theta_tolerance=0.0001,
        head_tolerance_cm=0.005,
        dtmx_days=0.001,
    )

    values = path.read_text(encoding="utf-8").splitlines()[2].split()
    assert values[:3] == ["200", "0.0001", "0.005"]
    assert values[5] == "0.001"


def test_water_balance_metrics_convert_section_volume_to_depth(tmp_path):
    path = Path(tmp_path) / "WaterMassBalance.out"
    path.write_text(
        "Date_time,Date,Storage_cm2,DeltaStorage_cm2,"
        "CumulativeIn_cm2,CumulativeOut_cm2,CumulativeSink_cm2,"
        "Residual_cm2,RelativeError_pct,MaxStepResidual_cm2,"
        "AcceptedSteps\n"
        "1,01/01/2000,100,0,0,0,0,0,0,0,0\n"
        "2,01/02/2000,110,10,12,2,0,0.01875,0.08,0.001875,42\n",
        encoding="utf-8",
    )

    metrics = _water_balance_metrics(
        path,
        prefix="mode6",
        domain_width_cm=37.5,
    )

    assert metrics["mode6_water_balance_residual_mm"] == pytest.approx(0.005)
    assert metrics["mode6_water_balance_relative_error_pct"] == pytest.approx(
        0.08
    )
    assert metrics["mode6_water_balance_max_step_residual_mm"] == pytest.approx(
        0.0005
    )
    assert metrics["mode6_water_balance_accepted_steps"] == 42


def test_drip_event_stop_is_derived_from_duration(tmp_path):
    path = Path(tmp_path) / "HUTD06.drp"

    _write_drip_file(
        path,
        emitter_node=2,
        w_appl_cm_h=3.125,
        source_width_cm=1.0,
        duration_h=36.0,
    )

    event = path.read_text(encoding="utf-8").splitlines()[4]
    assert "'04/01/2006' 0" in event
    assert "'04/02/2006' 12" in event


def test_select_soils_preserves_requested_order():
    soils = _select_soils(("clay_loam", "loam"))

    assert [soil.name for soil in soils] == ["clay_loam", "loam"]


@pytest.mark.parametrize(
    ("soil_names", "message"),
    [
        ((), "at least one"),
        (("silt",), "Unknown soil"),
        (("loam", "loam"), "duplicates"),
    ],
)
def test_select_soils_rejects_invalid_selection(soil_names, message):
    with pytest.raises(ValueError, match=message):
        _select_soils(soil_names)


def test_validator_accepts_physical_boundary_limited_runoff():
    frame = pd.DataFrame(
        [
            {
                "soil": "clay_loam",
                "delivered_input_mm": 30.0,
                "source_closure_error_mm": 0.0,
                "accepted_actual_error_mm": 0.0,
                "remaining_runoff_error_mm": 0.0,
                "storage_change_mm": 0.0,
                "mode6_closure_abs_max_mm": 0.0,
                "acceptance_closure_abs_max_mm": 0.0,
                "solver_limit_max": 0.0,
                "boundary_limit_max": 1.0,
                "mode6_remaining_mm": 0.6,
                "surface_runoff_mm": 0.6,
                "uncategorized_step_cuts": 0.0,
                "baseline_water_balance_residual_mm": 0.0,
                "baseline_water_balance_max_step_residual_mm": 0.0,
                "mode6_water_balance_residual_mm": 0.0,
                "mode6_water_balance_relative_error_pct": 0.0,
                "mode6_water_balance_max_step_residual_mm": 0.0,
                "delta_theta_max": 0.1,
                "wetting_depth_cm": 10.0,
            }
        ]
    )

    _validate_results(frame, expected_depth_mm=30.0)


def test_wetting_shape_uses_linear_element_edge_intersections(tmp_path):
    baseline_path = tmp_path / "baseline.G03"
    drip_path = tmp_path / "drip.G03"
    coordinates = [(0.0, 1.0), (1.0, 1.0), (0.0, 0.0), (1.0, 0.0)]
    baseline = pd.DataFrame(
        [
            {
                "Date_time": 1,
                "X": x_value,
                "Y": y_value,
                "thNew": 0.2,
            }
            for x_value, y_value in coordinates
        ]
    )
    delta_theta = {
        (0.0, 1.0): 0.01,
        (1.0, 1.0): 0.0,
        (0.0, 0.0): 0.0,
        (1.0, 0.0): 0.0,
    }
    drip = baseline.copy()
    drip["thNew"] = [
        row.thNew + delta_theta[(row.X, row.Y)]
        for row in baseline.itertuples(index=False)
    ]
    baseline.to_csv(baseline_path, index=False)
    drip.to_csv(drip_path, index=False)

    metrics = _wetting_shape(
        baseline_path,
        drip_path,
        emitter_x_cm=0.0,
        refinement_bounds=(0.0, 1.0, 0.0, 1.0),
    )

    # Nodal max-min would report zero width and depth for this one-node wet
    # response. Linear triangle clipping resolves the half-cell contour.
    assert metrics["wetting_width_cm"] == pytest.approx(0.5)
    assert metrics["wetting_depth_cm"] == pytest.approx(0.5)
    assert metrics["wetting_area_cm2"] == pytest.approx(0.25)
    assert metrics["wetting_touches_axis_boundary"]
    assert metrics["wetting_touches_surface_boundary"]
    assert not metrics["wetting_touches_outer_boundary"]
    assert not metrics["wetting_touches_bottom_boundary"]
    assert not metrics["wetting_censored_physical_boundary"]
    assert not metrics["wetting_censored_refinement_boundary"]


def test_wetting_shape_uses_requested_event_end_time(tmp_path):
    baseline_path = tmp_path / "baseline.G03"
    drip_path = tmp_path / "drip.G03"
    records = []
    for date_time in (38808.0, 38809.0):
        for y_value in (1.0, 0.0):
            for x_value in (0.0, 1.0):
                records.append(
                    {
                        "Date_time": date_time,
                        "X": x_value,
                        "Y": y_value,
                        "thNew": 0.2,
                    }
                )
    baseline = pd.DataFrame(records)
    drip = baseline.copy()
    drip.loc[drip["Date_time"] == 38809.0, "thNew"] = 0.21
    baseline.to_csv(baseline_path, index=False)
    drip.to_csv(drip_path, index=False)

    metrics = _wetting_shape(
        baseline_path,
        drip_path,
        emitter_x_cm=0.0,
        evaluation_time=pd.Timestamp("2006-04-02"),
        refinement_bounds=(0.0, 1.0, 0.0, 1.0),
    )

    assert metrics["wetting_evaluation_time"] == "2006-04-02T00:00:00"
    assert metrics["wetting_area_cm2"] == pytest.approx(1.0)


def test_wetting_geometry_flags_physical_and_refinement_censor_edges():
    field = pd.DataFrame(
        [
            {"X": x_value, "Y": y_value, "delta_theta": 0.01}
            for y_value in (2.0, 1.0, 0.0)
            for x_value in (0.0, 1.0, 2.0)
        ]
    )

    metrics = wetting_geometry_from_field(
        field,
        refinement_bounds=(0.5, 1.5, 0.5, 1.5),
    )

    assert metrics["wetting_area_cm2"] == pytest.approx(4.0)
    assert metrics["wetting_touches_physical_boundary"]
    assert metrics["wetting_censored_physical_boundary"]
    assert metrics["wetting_touches_refinement_boundary"]
    assert metrics["wetting_censored_refinement_boundary"]
    assert metrics["wetting_touches_refinement_x_max"]
    assert metrics["wetting_touches_refinement_y_min"]


def test_wetting_geometry_rejects_nonfinite_threshold():
    field = pd.DataFrame(
        [
            {"X": x_value, "Y": y_value, "delta_theta": 0.01}
            for y_value in (1.0, 0.0)
            for x_value in (0.0, 1.0)
        ]
    )

    with pytest.raises(ValueError, match="threshold"):
        wetting_geometry_from_field(field, threshold=float("nan"))


def test_three_grid_gci_accepts_known_asymptotic_sequence():
    result = three_grid_gci(104.0, 101.0, 100.25)

    assert result["status"] == "pass"
    assert result["valid"]
    assert result["monotonic"]
    assert result["asymptotic"]
    assert result["apparent_order"] == pytest.approx(2.0)
    assert result["asymptotic_ratio"] == pytest.approx(
        0.9925742574,
    )
    assert result["gci_21"] is not None
    assert result["gci_fine_pct"] == pytest.approx(
        100.0 * result["gci_21"]
    )


@pytest.mark.parametrize(
    ("values", "status"),
    [
        ((1.0, 3.0, 2.0), "non_monotonic"),
        ((1.0, 2.0, 4.0), "non_asymptotic_order"),
        ((4.0, 2.0, 1.5), "non_asymptotic_ratio"),
    ],
)
def test_three_grid_gci_rejects_non_asymptotic_sequences(values, status):
    result = three_grid_gci(*values)

    assert result["status"] == status
    assert not result["valid"]
    assert result["gci_21"] is None
    assert result["gci_32"] is None
    assert result["gci_fine_pct"] is None
