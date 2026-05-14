"""Read MAIZSIM outputs and map them into observation space."""

from pathlib import Path

import numpy as np
import pandas as pd


_SUPPORTED_SUFFIXES = {".g01", ".g03"}
_G01_COLUMNS = ("Date", "LAI")
_G03_COLUMNS = ("Date", "Y", "thNew", "Area")
_THETA_VARIABLES = {"theta", "soil_water_content", "swc"}
_MISSING = object()


def read_g01_daily_lai(path):
    """Read hourly g01 LAI output and return daily mean LAI."""
    output_path = Path(path)
    data = _read_output_csv(output_path, _G01_COLUMNS)

    date_col = _require_column(data, "Date", output_path)
    lai_col = _require_column(data, "LAI", output_path)

    frame = pd.DataFrame(
        {
            "date": _parse_dates(data[date_col], "Date", output_path),
            "lai": _parse_numeric(data[lai_col], "LAI", output_path),
        }
    )
    if frame.empty:
        raise ValueError(f"g01 output has no rows: {output_path}")

    daily_lai = frame.groupby("date", sort=True)["lai"].mean()
    daily_lai.index.name = "date"
    daily_lai.name = "LAI"
    return daily_lai


def read_g03_daily_theta(path, depth_top_cm, depth_bottom_cm):
    """Read G03 output and return daily thNew by depth.

    G03 ``Y`` is a vertical coordinate rather than depth. Depth is calculated
    as ``max(Y) - Y`` before filtering the requested depth interval.
    When the top and bottom depths are equal, the function returns the daily
    point-depth value by linearly interpolating the area-weighted profile.
    """
    output_path = Path(path)
    top, bottom = _validate_depth_range(depth_top_cm, depth_bottom_cm)
    frame = _read_g03_theta_frame(output_path)
    return _daily_theta_from_frame(frame, top, bottom, output_path)


def _read_g03_theta_frame(output_path):
    data = _read_output_csv(output_path, _G03_COLUMNS)

    date_col = _require_column(data, "Date", output_path)
    y_col = _require_column(data, "Y", output_path)
    theta_col = _require_column(data, "thNew", output_path)
    area_col = _require_column(data, "Area", output_path)

    frame = pd.DataFrame(
        {
            "date": _parse_dates(data[date_col], "Date", output_path),
            "y": _parse_numeric(data[y_col], "Y", output_path),
            "theta": _parse_numeric(data[theta_col], "thNew", output_path),
            "area": _parse_numeric(data[area_col], "Area", output_path),
        }
    )
    if frame.empty:
        raise ValueError(f"G03 output has no rows: {output_path}")

    surface_y = frame["y"].max()
    frame["depth_cm"] = surface_y - frame["y"]
    return frame


def _daily_theta_from_frame(frame, top, bottom, output_path, profile_cache=None):
    surface_y = frame["y"].max()
    if np.isclose(top, bottom):
        return _daily_theta_at_point_depth(
            frame,
            top,
            output_path,
            profile_cache=profile_cache,
        )

    in_depth = (top <= frame["depth_cm"]) & (frame["depth_cm"] <= bottom)
    depth_frame = frame.loc[in_depth].copy()
    if depth_frame.empty:
        raise ValueError(
            "G03 output has no nodes in depth range "
            f"{top:g}-{bottom:g} cm after converting Y to depth_cm "
            f"with surface Y={surface_y:g}: {output_path}"
        )

    depth_frame["weighted_theta"] = depth_frame["theta"] * depth_frame["area"]
    grouped = depth_frame.groupby("date", sort=True).agg(
        weighted_theta=("weighted_theta", "sum"),
        area=("area", "sum"),
    )
    zero_area = grouped["area"] == 0
    if zero_area.any():
        dates = ", ".join(
            date.strftime("%Y-%m-%d") for date in grouped.index[zero_area]
        )
        raise ValueError(
            "G03 output has zero total Area for depth range "
            f"{top:g}-{bottom:g} cm after converting Y to depth_cm "
            f"with surface Y={surface_y:g} on date(s): {dates}"
        )

    daily_theta = grouped["weighted_theta"] / grouped["area"]
    daily_theta.index.name = "date"
    daily_theta.name = "theta"
    return daily_theta


def _daily_theta_at_point_depth(
    frame,
    depth_cm,
    output_path,
    profile_cache=None,
):
    if profile_cache is None:
        profile_cache = {}

    daily_values = []
    for date, date_frame in frame.groupby("date", sort=True):
        if date not in profile_cache:
            profile_cache[date] = _area_weighted_depth_profile(
                date_frame,
                output_path,
                date,
            )
        profile = profile_cache[date]
        depth_values = profile.index.to_numpy(dtype=float)
        theta_values = profile.to_numpy(dtype=float)
        if depth_cm < depth_values[0] or depth_cm > depth_values[-1]:
            raise ValueError(
                "G03 output cannot interpolate requested depth "
                f"{depth_cm:g} cm on {date.strftime('%Y-%m-%d')}; "
                f"available depth range is {depth_values[0]:g}-"
                f"{depth_values[-1]:g} cm: {output_path}"
            )
        daily_values.append(
            (
                date,
                float(np.interp(depth_cm, depth_values, theta_values)),
            )
        )

    daily_theta = pd.Series(
        [value for _, value in daily_values],
        index=[date for date, _ in daily_values],
        dtype=float,
        name="theta",
    )
    daily_theta.index.name = "date"
    return daily_theta


def _area_weighted_depth_profile(date_frame, output_path, date):
    profile_frame = date_frame.copy()
    profile_frame["weighted_theta"] = (
        profile_frame["theta"] * profile_frame["area"]
    )
    grouped = profile_frame.groupby("depth_cm", sort=True).agg(
        weighted_theta=("weighted_theta", "sum"),
        area=("area", "sum"),
    )
    zero_area = grouped["area"] == 0
    if zero_area.any():
        depths = ", ".join(f"{depth:g}" for depth in grouped.index[zero_area])
        raise ValueError(
            "G03 output has zero total Area for point-depth interpolation "
            f"on {date.strftime('%Y-%m-%d')} at depth(s): {depths}: "
            f"{output_path}"
        )
    profile = grouped["weighted_theta"] / grouped["area"]
    if len(profile) < 2:
        raise ValueError(
            "G03 output needs at least two depth levels for point-depth "
            f"interpolation on {date.strftime('%Y-%m-%d')}: {output_path}"
        )
    return profile


def find_output_file(run_dir, suffix):
    """Find an output file by suffix, sorting by name when several exist."""
    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run directory does not exist: {run_path}")
    if not run_path.is_dir():
        raise NotADirectoryError(f"Run path is not a directory: {run_path}")

    normalized_suffix = _normalize_suffix(suffix)
    candidates = [
        path
        for path in run_path.iterdir()
        if path.is_file() and path.suffix.casefold() == normalized_suffix
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No MAIZSIM output file with suffix {suffix!r} in {run_path}"
        )

    return sorted(candidates, key=lambda path: path.name.casefold())[0]


def build_simulation_vector(run_dir, observation_specs):
    """Build simulated observation values in the order of observation_specs."""
    run_path = Path(run_dir)
    values = []
    g01_daily_lai = None
    g03_path = None
    g03_theta_frame = None
    g03_daily_theta = {}
    g03_profile_cache = {}

    for index, spec in enumerate(observation_specs):
        variable = _get_spec_value(spec, "variable", index=index)
        variable_key = str(variable).strip().casefold()
        date = _parse_spec_date(_get_spec_value(spec, "date", index=index), index)

        if variable_key == "lai":
            if g01_daily_lai is None:
                g01_daily_lai = read_g01_daily_lai(
                    find_output_file(run_path, ".g01")
                )
            values.append(_value_on_date(g01_daily_lai, date, spec, index))
        elif variable_key in _THETA_VARIABLES:
            top = _parse_spec_depth(spec, ("depth_top_cm", "depth_top"), index)
            bottom = _parse_spec_depth(
                spec, ("depth_bottom_cm", "depth_bottom"), index
            )
            top, bottom = _validate_depth_range(top, bottom)
            depth_key = (top, bottom)
            if g03_path is None:
                g03_path = find_output_file(run_path, ".G03")
            if g03_theta_frame is None:
                g03_theta_frame = _read_g03_theta_frame(g03_path)
            if depth_key not in g03_daily_theta:
                g03_daily_theta[depth_key] = _daily_theta_from_frame(
                    g03_theta_frame,
                    top,
                    bottom,
                    g03_path,
                    profile_cache=g03_profile_cache,
                )
            values.append(
                _value_on_date(g03_daily_theta[depth_key], date, spec, index)
            )
        else:
            raise ValueError(
                "Unsupported observation variable "
                f"{variable!r} at observation_specs[{index}]. "
                "Supported variables are LAI, theta, and soil_water_content."
            )

    return np.asarray(values, dtype=float)


def _read_output_csv(path, required_columns=None):
    if not path.exists():
        raise FileNotFoundError(f"MAIZSIM output file does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"MAIZSIM output path is not a file: {path}")

    read_csv_kwargs = {"skipinitialspace": True}
    if required_columns is not None:
        normalized_required = {
            _normalize_column(column) for column in required_columns
        }

        def is_required_column(column):
            return _normalize_column(column) in normalized_required

        read_csv_kwargs["usecols"] = is_required_column

    try:
        data = pd.read_csv(path, **read_csv_kwargs)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"MAIZSIM output file is empty: {path}") from exc

    data = data.rename(columns=lambda column: str(column).strip())
    data = data.dropna(how="all")
    return data


def _require_column(data, required_name, path):
    normalized_required = _normalize_column(required_name)
    column_by_key = {
        _normalize_column(column): column
        for column in data.columns
    }
    if normalized_required not in column_by_key:
        available = ", ".join(str(column) for column in data.columns)
        raise ValueError(
            f"Missing required column {required_name!r} in {path}. "
            f"Available columns: {available}"
        )
    return column_by_key[normalized_required]


def _normalize_column(column):
    return "".join(str(column).strip().casefold().split())


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


def _validate_depth_range(depth_top_cm, depth_bottom_cm):
    top = _coerce_depth_value(depth_top_cm, "depth_top_cm")
    bottom = _coerce_depth_value(depth_bottom_cm, "depth_bottom_cm")
    if top > bottom:
        raise ValueError(
            "depth_top_cm must be less than or equal to depth_bottom_cm: "
            f"{top:g} > {bottom:g}"
        )
    return top, bottom


def _normalize_suffix(suffix):
    suffix_text = str(suffix).strip().casefold()
    if not suffix_text.startswith("."):
        suffix_text = f".{suffix_text}"
    if suffix_text not in _SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(
            f"Unsupported MAIZSIM output suffix {suffix!r}. "
            f"Supported suffixes: {supported}"
        )
    return suffix_text


def _get_spec_value(spec, name, index=None, default=_MISSING):
    if isinstance(spec, dict):
        if name in spec:
            return spec[name]
    elif hasattr(spec, name):
        return getattr(spec, name)

    if default is not _MISSING:
        return default

    location = (
        f"observation_specs[{index}]"
        if index is not None
        else "observation spec"
    )
    raise ValueError(f"Missing required field {name!r} in {location}.")


def _get_first_spec_value(spec, names, index):
    for name in names:
        value = _get_spec_value(spec, name, index=index, default=_MISSING)
        if value is not _MISSING:
            return value
    names_text = ", ".join(repr(name) for name in names)
    raise ValueError(
        f"Missing one of required fields {names_text} in observation_specs[{index}]."
    )


def _parse_spec_date(value, index):
    if _is_missing(value):
        raise ValueError(f"Missing date in observation_specs[{index}].")
    try:
        return pd.Timestamp(value).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid date {value!r} in observation_specs[{index}]."
        ) from exc


def _parse_spec_depth(spec, names, index):
    value = _get_first_spec_value(spec, names, index)
    return _coerce_depth_value(value, names[0], index=index)


def _coerce_depth_value(value, field_name, index=None):
    if _is_missing(value):
        location = (
            f"observation_specs[{index}]"
            if index is not None
            else "depth range"
        )
        raise ValueError(f"Missing {field_name!r} in {location}.")
    try:
        depth = float(value)
    except (TypeError, ValueError) as exc:
        location = (
            f" in observation_specs[{index}]"
            if index is not None
            else ""
        )
        raise ValueError(f"Invalid {field_name} value {value!r}{location}.") from exc
    if not np.isfinite(depth):
        location = (
            f" in observation_specs[{index}]"
            if index is not None
            else ""
        )
        raise ValueError(f"Invalid {field_name} value {value!r}{location}.")
    return depth


def _value_on_date(series, date, spec, index):
    if date not in series.index:
        raise ValueError(
            "Simulation output is missing observation date "
            f"{date.strftime('%Y-%m-%d')} for {_format_spec(spec, index)}. "
            "Interpolation is not applied."
        )
    return float(series.loc[date])


def _format_spec(spec, index):
    try:
        variable = _get_spec_value(spec, "variable", index=index)
    except ValueError:
        variable = "unknown"
    return f"observation_specs[{index}] variable={variable!r}"


def _is_missing(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
