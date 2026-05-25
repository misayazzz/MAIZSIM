"""HYDRUS-derived calibration targets for MAIZSIM surface drip irrigation."""

from __future__ import annotations

from dataclasses import dataclass


DRIP_WET_WIDTH_FALLBACK_CM = 20.0
HYDRUS_SURFACE_DRIP_SOURCE = (
    "Lazarovitch_et_al_2023_Fig8_SurfaceDrip_digitized"
)


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


def calibrated_drip_wet_width_max_cm(soil_name):
    """Return HYDRUS-calibrated width, or the documented fallback."""
    target = HYDRUS_SURFACE_DRIP_TARGETS.get(str(soil_name))
    if target is None:
        return DRIP_WET_WIDTH_FALLBACK_CM
    return target.wet_width_max_cm


def drip_wet_width_calibration_source(soil_name):
    """Return a compact source label for a soil's wetted-width limit."""
    target = HYDRUS_SURFACE_DRIP_TARGETS.get(str(soil_name))
    if target is None:
        return "fallback_no_hydrus_surface_drip_target"
    return target.source
