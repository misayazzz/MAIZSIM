"""Utilities for validating MAIZSIM drip-irrigation runs."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import re

import numpy as np
import pandas as pd


MAX_DRIP_EVENTS = 75
MAX_DRIP_NODES = 150

_G05_COLUMNS = (
    "Date_time",
    "Date",
    "CumRain",
    "infil",
    "Runoff",
    "Drainage",
)

G05_DRIP_DIAGNOSTIC_COLUMNS = {
    "drip_input_mm": "DripInput",
    "drip_demand_mm": "DripDemand",
    "drip_pressure_loss_mm": "DripPressureLoss",
    "drip_hydraulic_excess_mm": "DripHydraulicExcess",
    "drip_actual_infil_mm": "DripActualInfil",
    "drip_source_input_mm": "DripSourceInput",
    "drip_source_loss_mm": "DripSourceLoss",
    "drip_surface_storage_change_mm": "DripStorageChange",
    "drip_surface_runoff_mm": "DripSurfaceRunoff",
    "drip_surface_storage_mm": "DripSurfaceStorage",
    "drip_boundary_input_closure_mm": "DripBoundaryInClosure",
    "drip_boundary_acceptance_closure_mm": "DripBoundaryAccClosure",
    "drip_wet_nodes_mean": "DripWetNodesMean",
    "drip_wet_nodes_max": "DripWetNodesMax",
    "drip_wet_width_mean_cm": "DripWetWidthMean",
    "drip_wet_width_max_cm": "DripWetWidthMax",
    "drip_surface_application_width_mean_cm": "DripWetWidthMean",
    "drip_surface_application_width_max_cm": "DripWetWidthMax",
    "drip_pressure_factor_mean": "DripPressureFactorMean",
    "drip_pressure_factor_min": "DripPressureFactorMin",
}


@dataclass(frozen=True)
class DripEvent:
    """One drip-irrigation event from a MAIZSIM .drp file."""

    start: datetime
    stop: datetime
    rate_cm_hr: float
    nodes: tuple[int, ...]
    pressure_mode: int = 0
    pressure_head_cm: float = 0.0
    pressure_exponent: float = 1.0
    pressure_pc_min_cm: float = 0.0
    pressure_pc_max_cm: float = 0.0
    wet_width_max_cm: float = 0.0
    spread_mode: int = 0
    source_width_cm: float = 0.0

    @property
    def duration_hours(self):
        return (self.stop - self.start).total_seconds() / 3600.0

    @property
    def applied_depth_cm(self):
        return self.rate_cm_hr * self.duration_hours


@dataclass(frozen=True)
class DripSchedule:
    """Parsed drip-irrigation schedule and mass-balance helpers."""

    events: tuple[DripEvent, ...]

    @property
    def event_count(self):
        return len(self.events)

    @property
    def total_event_node_depth_cm(self):
        return sum(
            event.applied_depth_cm * len(event.nodes)
            for event in self.events
        )

    def expected_grid_depth_mm(self, node_widths_cm, grid_width_cm):
        """Return expected grid-averaged water input in mm.

        MAIZSIM G05 reports surface water terms as grid-averaged mm.
        For a fixed-node surface drip event, the expected increment is:
        rate_cm_hr * duration_hr * sum(node_width_cm) / grid_width_cm * 10.
        In Mode5, source_width_cm overrides the grid node width to keep
        physical emitter flow independent of mesh spacing.
        """
        grid_width = _positive_float(grid_width_cm, "grid_width_cm")
        width_by_node = {
            int(node): _positive_float(width, f"node_widths_cm[{node!r}]")
            for node, width in dict(node_widths_cm).items()
        }

        total_cm2_per_cm = 0.0
        for event in self.events:
            if event.source_width_cm > 0.0:
                total_cm2_per_cm += (
                    event.applied_depth_cm
                    * event.source_width_cm
                    * len(event.nodes)
                )
            else:
                missing = [node for node in event.nodes if node not in width_by_node]
                if missing:
                    raise ValueError(
                        "Missing node width for drip node(s): "
                        + ", ".join(str(node) for node in missing)
                    )
                total_cm2_per_cm += event.applied_depth_cm * sum(
                    width_by_node[node] for node in event.nodes
                )

        return total_cm2_per_cm / grid_width * 10.0


def parse_drip_file(path):
    """Parse the current MAIZSIM .drp schedule format."""
    drip_path = Path(path)
    if not drip_path.exists():
        raise FileNotFoundError(f"Drip file does not exist: {drip_path}")
    if not drip_path.is_file():
        raise FileNotFoundError(f"Drip path is not a file: {drip_path}")

    lines = [
        line.strip()
        for line in drip_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) < 3:
        raise ValueError(f"Drip file is incomplete: {drip_path}")

    event_count = _parse_int_line(lines[2], "number of drip irrigations")
    if event_count < 0 or event_count > MAX_DRIP_EVENTS:
        raise ValueError(
            "Invalid number of drip irrigations: "
            f"{event_count}; expected 0-{MAX_DRIP_EVENTS}"
        )
    if event_count == 0:
        return DripSchedule(())

    index = 4
    events = []
    for event_index in range(event_count):
        if index >= len(lines):
            raise ValueError(
                f"Missing drip event line for event {event_index + 1}: {drip_path}"
            )
        event = _parse_event_line(lines[index], event_index, drip_path)
        index += 1

        if index >= len(lines):
            raise ValueError(
                f"Missing drip node label line for event {event_index + 1}: "
                f"{drip_path}"
            )
        index += 1

        if index >= len(lines):
            raise ValueError(
                f"Missing drip node list for event {event_index + 1}: {drip_path}"
            )
        nodes = _parse_nodes_line(
            lines[index],
            event["node_count"],
            event_index,
            drip_path,
        )
        index += 1

        events.append(
            DripEvent(
                start=event["start"],
                stop=event["stop"],
                rate_cm_hr=event["rate_cm_hr"],
                nodes=nodes,
                pressure_mode=event["pressure_mode"],
                pressure_head_cm=event["pressure_head_cm"],
                pressure_exponent=event["pressure_exponent"],
                pressure_pc_min_cm=event["pressure_pc_min_cm"],
                pressure_pc_max_cm=event["pressure_pc_max_cm"],
                wet_width_max_cm=event["wet_width_max_cm"],
                spread_mode=event["spread_mode"],
                source_width_cm=event["source_width_cm"],
            )
        )

    return DripSchedule(tuple(events))


def read_g05_surface_water(path):
    """Read MAIZSIM G05 water-balance columns, independent of column order."""
    g05_path = Path(path)
    data = _read_csv(g05_path)

    columns = {
        "date_time": _require_column(data, "Date_time", g05_path),
        "date": _require_column(data, "Date", g05_path),
        "cumrain_mm": _require_column(data, "CumRain", g05_path),
        "infil_mm": _require_column(data, "infil", g05_path),
    }
    optional_columns = {
        "runoff_mm": "Runoff",
        "drainage_mm": "Drainage",
    }
    optional_columns.update(G05_DRIP_DIAGNOSTIC_COLUMNS)
    for output_name, source_name in optional_columns.items():
        column = _find_column(data, source_name)
        if column is not None:
            columns[output_name] = column

    frame = pd.DataFrame(
        {
            "date_time": _parse_numeric(
                data[columns["date_time"]],
                "Date_time",
                g05_path,
            ),
            "date": _parse_dates(data[columns["date"]], "Date", g05_path),
            "cumrain_mm": _parse_numeric(
                data[columns["cumrain_mm"]],
                "CumRain",
                g05_path,
            ),
            "infil_mm": _parse_numeric(
                data[columns["infil_mm"]],
                "infil",
                g05_path,
            ),
        }
    )
    for output_name in optional_columns:
        if output_name in columns:
            frame[output_name] = _parse_numeric(
                data[columns[output_name]],
                output_name,
                g05_path,
            )
    if frame.empty:
        raise ValueError(f"G05 output has no rows: {g05_path}")
    return frame


def g05_delta_by_date(baseline_g05, drip_g05, date):
    """Return drip-minus-baseline G05 water terms for one date."""
    baseline = _g05_row_on_date(read_g05_surface_water(baseline_g05), date)
    drip = _g05_row_on_date(read_g05_surface_water(drip_g05), date)
    candidate_columns = (
        "cumrain_mm",
        "infil_mm",
        "runoff_mm",
        "drainage_mm",
        *G05_DRIP_DIAGNOSTIC_COLUMNS,
    )
    shared = [
        column
        for column in candidate_columns
        if column in baseline.index and column in drip.index
    ]
    return {column: float(drip[column] - baseline[column]) for column in shared}


def build_public_comparison_report_skeleton(
    schedule,
    expected_grid_depth_mm=None,
    simulated_delta=None,
):
    """Build a Markdown skeleton for comparing MAIZSIM drip behavior to literature."""
    schedule = _coerce_schedule(schedule)
    expected_text = _format_optional_float(expected_grid_depth_mm, "mm")
    delta = dict(simulated_delta or {})
    cumrain_text = _format_optional_float(delta.get("cumrain_mm"), "mm")
    infil_text = _format_optional_float(delta.get("infil_mm"), "mm")
    runoff_text = _format_optional_float(delta.get("runoff_mm"), "mm")
    drainage_text = _format_optional_float(delta.get("drainage_mm"), "mm")

    return "\n".join(
        [
            "# Drip-Irrigation Public Comparison Report Skeleton",
            "",
            "## Case Summary",
            "",
            f"- Drip events: {schedule.event_count}",
            (
                "- Total event-node applied depth: "
                f"{schedule.total_event_node_depth_cm:.6g} cm"
            ),
            f"- Expected grid-averaged input: {expected_text}",
            "",
            "## Public-Source Comparison Indicators",
            "",
            "- Boundary type: surface point-source Neumann flux at fixed nodes.",
            "- Scheduling: event start/stop time, duration, node count, and rate.",
            "- Water amount: rate * duration * source measure / grid width for Mode5.",
            "- Mode5 uses a dynamic local surface interval bounded by DripWetWidthMax.",
            "- Pressure correction: optional event fields support back-pressure and pressure-compensating surface-source approximations.",
            "- Refined diagnostics: G05 can report drip demand, pressure loss, hydraulic excess, surface application width, wet node count, and pressure factors.",
            "- Water balance: G05 CumRain, infiltration, runoff, and drainage deltas.",
            "- Drip accounting: G05 DripInput and SeasDrip report drip-only water input when available.",
            "- Wetting pattern: G03 theta changes by depth and lateral position.",
            "- Literature gap: subsurface emitter source terms are not represented by this surface-source approximation.",
            "",
            "## Current Run Metrics",
            "",
            f"- G05 CumRain delta: {cumrain_text}",
            f"- G05 infiltration delta: {infil_text}",
            f"- G05 runoff delta: {runoff_text}",
            f"- G05 drainage delta: {drainage_text}",
            "",
            "## Public References To Compare Against",
            "",
            "- HYDRUS-2D/3D Technical Manual: local flux and boundary-condition behavior.",
            (
                "- Skaggs et al. 2004: HYDRUS-2D drip-irrigation simulations "
                "versus observations."
            ),
            (
                "- Morianou et al. 2023: review of HYDRUS 2D/3D drip-irrigation "
                "applications."
            ),
            "",
            "## Assertions Still Requiring A Full MAIZSIM Run",
            "",
            "- G05 CumRain delta is within tolerance of expected grid-averaged input.",
            "- G05 infiltration increases on or after the drip event date.",
            "- G03 theta increases near the active drip node and not uniformly everywhere.",
            "- Water-balance terms remain finite through a long drip schedule.",
        ]
    )


def _parse_event_line(line, event_index, path):
    tokens = _split_tokens(line)
    if len(tokens) not in (6, 11, 12, 13, 14):
        raise ValueError(
            f"Drip event {event_index + 1} in {path} must have 6, 11, 12, 13, or 14 fields: "
            "start_date, start_hour, stop_date, stop_hour, rate_cm_hr, "
            "node_count[, pressure_mode, pressure_head_cm, pressure_exponent, "
            "pressure_pc_min_cm, pressure_pc_max_cm[, wet_width_max_cm"
            "[, spread_mode[, source_width_cm]]]]"
        )
    start_date, start_hour, stop_date, stop_hour, rate, node_count = tokens[:6]
    pressure_mode = 0
    pressure_head_cm = 0.0
    pressure_exponent = 1.0
    pressure_pc_min_cm = 0.0
    pressure_pc_max_cm = 0.0
    wet_width_max_cm = 0.0
    spread_mode = 0
    source_width_cm = 0.0
    if len(tokens) in (11, 12, 13, 14):
        pressure_mode = _parse_int(tokens[6], "pressure_mode", event_index)
        pressure_head_cm = _parse_float(tokens[7], "pressure_head_cm", event_index)
        pressure_exponent = _parse_float(
            tokens[8],
            "pressure_exponent",
            event_index,
        )
        pressure_pc_min_cm = _parse_float(
            tokens[9],
            "pressure_pc_min_cm",
            event_index,
        )
        pressure_pc_max_cm = _parse_float(
            tokens[10],
            "pressure_pc_max_cm",
            event_index,
        )
    if len(tokens) in (12, 13, 14):
        wet_width_max_cm = _parse_float(
            tokens[11],
            "wet_width_max_cm",
            event_index,
        )
    if len(tokens) in (13, 14):
        spread_mode = _parse_int(tokens[12], "spread_mode", event_index)
    if len(tokens) == 14:
        source_width_cm = _parse_float(
            tokens[13],
            "source_width_cm",
            event_index,
        )
    start = _combine_date_hour(start_date, start_hour, event_index, "start")
    stop = _combine_date_hour(stop_date, stop_hour, event_index, "stop")
    if stop <= start:
        raise ValueError(
            f"Drip event {event_index + 1} stop time must be after start time"
        )

    rate_cm_hr = _parse_float(rate, "rate_cm_hr", event_index)
    if rate_cm_hr <= 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} rate_cm_hr must be positive"
        )

    count = _parse_int(node_count, "node_count", event_index)
    if count < 1 or count > MAX_DRIP_NODES:
        raise ValueError(
            f"Drip event {event_index + 1} node_count must be 1-{MAX_DRIP_NODES}"
        )
    if pressure_mode < 0 or pressure_mode > 3:
        raise ValueError(
            f"Drip event {event_index + 1} pressure_mode must be 0, 1, 2, or 3"
        )
    if pressure_mode in (1, 2) and pressure_head_cm <= 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} pressure_head_cm must be positive "
            "when pressure_mode is 1 or 2"
        )
    if pressure_exponent <= 0.0:
        pressure_exponent = 1.0
    if pressure_pc_min_cm < 0.0 or pressure_pc_max_cm < 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} pressure compensation heads "
            "must be non-negative"
        )
    if wet_width_max_cm < 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} wet_width_max_cm must be non-negative"
        )
    if spread_mode not in (0, 5):
        raise ValueError(
            f"Drip event {event_index + 1} spread_mode must be 0 or 5"
        )
    if source_width_cm < 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} source_width_cm must be non-negative"
        )
    if spread_mode != 5 and source_width_cm > 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} source_width_cm requires spread_mode 5"
        )
    if spread_mode == 5 and source_width_cm <= 0.0:
        raise ValueError(
            f"Drip event {event_index + 1} source_width_cm must be positive "
            "when spread_mode is 5"
        )

    return {
        "start": start,
        "stop": stop,
        "rate_cm_hr": rate_cm_hr,
        "node_count": count,
        "pressure_mode": pressure_mode,
        "pressure_head_cm": pressure_head_cm,
        "pressure_exponent": pressure_exponent,
        "pressure_pc_min_cm": pressure_pc_min_cm,
        "pressure_pc_max_cm": pressure_pc_max_cm,
        "wet_width_max_cm": wet_width_max_cm,
        "spread_mode": spread_mode,
        "source_width_cm": source_width_cm,
    }


def _parse_nodes_line(line, expected_count, event_index, path):
    nodes = tuple(
        _parse_int(token, "node", event_index)
        for token in _split_tokens(line)
    )
    if len(nodes) != expected_count:
        raise ValueError(
            f"Drip event {event_index + 1} in {path} declares "
            f"{expected_count} node(s) but lists {len(nodes)}"
        )
    invalid = [node for node in nodes if node < 1]
    if invalid:
        raise ValueError(
            f"Drip event {event_index + 1} has invalid node id(s): "
            + ", ".join(str(node) for node in invalid)
        )
    return nodes


def _split_tokens(line):
    return [
        token.strip().strip("'\"")
        for token in re.split(r"[\s,]+", line.strip())
        if token.strip()
    ]


def _combine_date_hour(date_text, hour_text, event_index, field_name):
    date = _parse_date(date_text, event_index, field_name)
    hour = _parse_float(hour_text, f"{field_name}_hour", event_index)
    if hour < 0.0 or hour > 24.0:
        raise ValueError(
            f"Drip event {event_index + 1} {field_name}_hour must be 0-24"
        )
    whole_hours = int(hour)
    minutes = round((hour - whole_hours) * 60.0)
    if minutes == 60:
        whole_hours += 1
        minutes = 0
    return date + timedelta(hours=whole_hours, minutes=minutes)


def _parse_date(value, event_index, field_name):
    for date_format in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    raise ValueError(
        f"Drip event {event_index + 1} has invalid {field_name}_date {value!r}"
    )


def _parse_int_line(line, field_name):
    tokens = _split_tokens(line)
    if len(tokens) != 1:
        raise ValueError(f"Invalid {field_name} line: {line!r}")
    return _parse_int(tokens[0], field_name, None)


def _parse_int(value, field_name, event_index):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        location = (
            f" in drip event {event_index + 1}"
            if event_index is not None
            else ""
        )
        raise ValueError(f"Invalid {field_name}{location}: {value!r}") from exc


def _parse_float(value, field_name, event_index):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {field_name} in drip event {event_index + 1}: {value!r}"
        ) from exc
    if not np.isfinite(number):
        raise ValueError(
            f"Invalid {field_name} in drip event {event_index + 1}: {value!r}"
        )
    return number


def _read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"G05 output file does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"G05 output path is not a file: {path}")
    try:
        data = pd.read_csv(path, skipinitialspace=True)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"G05 output file is empty: {path}") from exc
    data = data.rename(columns=lambda column: str(column).strip())
    data = data.dropna(how="all")
    return data


def _require_column(data, required_name, path):
    column = _find_column(data, required_name)
    if column is None:
        available = ", ".join(str(column) for column in data.columns)
        raise ValueError(
            f"Missing required G05 column {required_name!r} in {path}. "
            f"Available columns: {available}"
        )
    return column


def _find_column(data, required_name):
    normalized_required = _normalize_column(required_name)
    for column in data.columns:
        if _normalize_column(column) == normalized_required:
            return column
    return None


def _normalize_column(column):
    return "".join(str(column).strip().casefold().split()).replace("_", "")


def _parse_dates(values, column_name, path):
    dates = pd.to_datetime(values, errors="coerce").dt.normalize()
    invalid = dates.isna()
    if invalid.any():
        raise ValueError(
            f"Column {column_name!r} in {path} contains "
            f"{int(invalid.sum())} invalid date value(s)."
        )
    return dates


def _parse_numeric(values, column_name, path):
    numbers = pd.to_numeric(values, errors="coerce")
    invalid = numbers.isna()
    if invalid.any():
        raise ValueError(
            f"Column {column_name!r} in {path} contains "
            f"{int(invalid.sum())} non-numeric value(s)."
        )
    return numbers.astype(float)


def _g05_row_on_date(frame, date):
    target = pd.Timestamp(date).normalize()
    matches = frame.loc[frame["date"] == target]
    if matches.empty:
        raise ValueError(
            f"G05 output is missing date {target.strftime('%Y-%m-%d')}"
        )
    return matches.iloc[-1]


def _positive_float(value, field_name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if not np.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field_name} must be a positive number")
    return number


def _coerce_schedule(schedule):
    if isinstance(schedule, DripSchedule):
        return schedule
    return DripSchedule(tuple(schedule))


def _format_optional_float(value, unit):
    if value is None:
        return "pending"
    return f"{float(value):.6g} {unit}"
