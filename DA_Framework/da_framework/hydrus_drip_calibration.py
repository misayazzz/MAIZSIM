"""HYDRUS-derived calibration targets for MAIZSIM surface drip irrigation."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


DRIP_WET_WIDTH_FALLBACK_CM = 20.0
HYDRUS_SURFACE_DRIP_DIGITIZED_TARGETS_CSV = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "hydrus_surface_drip_digitized_targets.csv"
)
HYDRUS_SURFACE_DRIP_SOURCE = (
    "Lazarovitch_et_al_2023_Fig8_SurfaceDrip_digitized"
)
HYDRUS_SURFACE_DRIP_REFERENCE_DURATION_H = 2.0


@dataclass(frozen=True)
class HydrusSurfaceDripTarget:
    """One digitized HYDRUS SurfaceDrip saturated-radius target."""

    soil_name: str
    event_duration_h: float
    emitter_rate_l_h: float
    applied_volume_l: float
    saturated_radius_cm: float
    source: str = HYDRUS_SURFACE_DRIP_SOURCE

    @property
    def wet_width_max_cm(self):
        """Return the full wetted surface width corresponding to the radius."""
        return 2.0 * self.saturated_radius_cm


HYDRUS_SURFACE_DRIP_TARGETS = {
    "loam": HydrusSurfaceDripTarget(
        soil_name="loam",
        event_duration_h=2.0,
        emitter_rate_l_h=2.0,
        applied_volume_l=4.0,
        saturated_radius_cm=19.85,
    ),
    "sandy_loam": HydrusSurfaceDripTarget(
        soil_name="sandy_loam",
        event_duration_h=2.0,
        emitter_rate_l_h=2.0,
        applied_volume_l=4.0,
        saturated_radius_cm=8.15,
    ),
}

HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM = {
    "loam": (
        (0.0, 0.0),
        (0.03, 5.74),
        (0.05, 12.34),
        (0.10, 20.32),
        (0.20, 25.24),
        (0.30, 28.56),
        (0.50, 32.16),
        (1.00, 35.68),
        (2.00, 39.70),
    ),
    "sandy_loam": (
        (0.0, 0.0),
        (0.03, 8.26),
        (0.05, 10.86),
        (0.10, 13.46),
        (0.20, 15.52),
        (0.30, 16.30),
        (0.50, 16.58),
        (1.00, 16.30),
        (2.00, 16.30),
    ),
}


def calibrated_drip_wet_width_max_cm(soil_name):
    """Return HYDRUS-calibrated width, or the documented fallback."""
    target = HYDRUS_SURFACE_DRIP_TARGETS.get(str(soil_name))
    if target is None:
        return DRIP_WET_WIDTH_FALLBACK_CM
    return target.wet_width_max_cm


def hydrus_surface_drip_width_cm(soil_name, elapsed_hours, wet_width_max_cm=None):
    """Return the target wetted width for elapsed irrigation time."""
    elapsed = max(0.0, float(elapsed_hours))
    limit = wet_width_max_cm
    if limit is None:
        limit = calibrated_drip_wet_width_max_cm(soil_name)
    limit = max(0.0, float(limit))

    curve = HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM.get(str(soil_name))
    if curve is None:
        return _fallback_width(elapsed, limit)
    return min(limit, _interpolate_curve(curve, elapsed))


def drip_wet_width_calibration_source(soil_name):
    """Return a compact source label for a soil's wetted-width limit."""
    target = HYDRUS_SURFACE_DRIP_TARGETS.get(str(soil_name))
    if target is None:
        return "fallback_no_hydrus_surface_drip_target"
    return target.source


def read_hydrus_surface_drip_digitized_targets(path=None):
    """Read the reference CSV used to document the digitized width curves."""
    input_path = Path(path) if path is not None else HYDRUS_SURFACE_DRIP_DIGITIZED_TARGETS_CSV
    rows = []
    with input_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            rows.append(
                {
                    "soil_name": row["soil_name"],
                    "elapsed_hours": float(row["elapsed_hours"]),
                    "target_full_wet_width_cm": float(
                        row["target_full_wet_width_cm"]
                    ),
                    "target_saturated_radius_cm": float(
                        row["target_saturated_radius_cm"]
                    ),
                    "event_duration_h": float(row["event_duration_h"]),
                    "emitter_rate_l_h": float(row["emitter_rate_l_h"]),
                    "applied_volume_l": float(row["applied_volume_l"]),
                    "source": row["source"],
                    "source_figure": row["source_figure"],
                    "digitization_note": row["digitization_note"],
                }
            )
    return rows


def _interpolate_curve(curve, elapsed_hours):
    if elapsed_hours <= curve[0][0]:
        return curve[0][1]
    for index in range(1, len(curve)):
        left_time, left_width = curve[index - 1]
        right_time, right_width = curve[index]
        if elapsed_hours <= right_time:
            fraction = (elapsed_hours - left_time) / (right_time - left_time)
            return left_width + fraction * (right_width - left_width)
    return curve[-1][1]


def _fallback_width(elapsed_hours, limit):
    if limit <= 0.0:
        return 0.0
    progress = min(
        1.0,
        elapsed_hours / HYDRUS_SURFACE_DRIP_REFERENCE_DURATION_H,
    )
    return limit * progress ** 0.5
