"""Write MAIZSIM parameter files with basic physical validation."""

import math
import operator
import re
from pathlib import Path

try:
    from .errors import ParameterWriteError
except ImportError:  # pragma: no cover - used only before errors.py is available.
    class ParameterWriteError(Exception):
        """Raised when MAIZSIM parameter writing fails."""


VAR_DATA_LINE_INDEX = 3
VAR_MIN_COLUMNS = 7
VAR_PARAMETER_COLUMNS = {
    "JuvenileLeaves": 0,
    "StayGreen": 2,
    "LM_min": 3,
    "Rmax_LTAR": 4,
}

SOI_HEADER_LINES = 2
SOI_MIN_COLUMNS = 11
SOI_PARAMETER_COLUMNS = {
    "thetaS": (1, 3, 8),
    "n": (5,),
}

POSITIVE_PARAMETERS = {
    "JuvenileLeaves",
    "StayGreen",
    "LM_min",
    "Rmax_LTAR",
}

TOKEN_RE = re.compile(r"[^,\s]+")

__all__ = [
    "validate_parameter_values",
    "write_member_parameters",
    "write_soi_parameters",
    "write_var_parameters",
]


def validate_parameter_values(values, soil_theta_r=None):
    """Validate supported MAIZSIM parameter values."""
    values = _ensure_mapping(values)

    for name in POSITIVE_PARAMETERS:
        if name not in values:
            continue
        number = _as_float(values[name], name)
        if number <= 0:
            raise ParameterWriteError(f"{name} must be positive, got {number}.")

    if "n" in values:
        number = _as_float(values["n"], "n")
        if number <= 1:
            raise ParameterWriteError(f"n must be greater than 1, got {number}.")

    if "thetaS" in values:
        theta_s = _as_float(values["thetaS"], "thetaS")
        theta_r = 0.0
        if soil_theta_r is not None:
            theta_r = _as_float(soil_theta_r, "soil_theta_r")
        if not theta_r < theta_s < 1:
            raise ParameterWriteError(
                "thetaS must be greater than thetaR and less than 1, "
                f"got thetaS={theta_s}, thetaR={theta_r}."
            )


def write_var_parameters(var_path, values):
    """Write supported crop parameters into the first data row of a .var file."""
    update = _build_var_update(var_path, values)
    if update is None:
        return
    path, lines = update
    _write_lines(path, lines, "VAR")


def write_soi_parameters(soi_path, values, material_index=0):
    """Write supported soil parameters into one material row of a .soi file."""
    update = _build_soi_update(soi_path, values, material_index)
    if update is None:
        return
    path, lines = update
    _write_lines(path, lines, "SOI")


def write_member_parameters(run_dir, parameter_values, var_file, soi_file):
    """Write supported crop and soil parameters inside a member run directory."""
    parameter_values = _ensure_mapping(parameter_values)
    updates = []

    if _select_values(parameter_values, VAR_PARAMETER_COLUMNS):
        var_path = _resolve_member_path(run_dir, var_file, "VAR")
        update = _build_var_update(var_path, parameter_values)
        if update is not None:
            updates.append(("VAR", update))

    if _select_values(parameter_values, SOI_PARAMETER_COLUMNS):
        soi_path = _resolve_member_path(run_dir, soi_file, "SOI")
        update = _build_soi_update(soi_path, parameter_values)
        if update is not None:
            updates.append(("SOI", update))

    for file_kind, update in updates:
        path, lines = update
        _write_lines(path, lines, file_kind)


def _build_var_update(var_path, values):
    values = _select_values(values, VAR_PARAMETER_COLUMNS)
    if not values:
        return None

    validate_parameter_values(values)
    path = _coerce_path(var_path, "VAR")
    lines = _read_lines(path, "VAR")
    _require_line_count(lines, VAR_DATA_LINE_INDEX + 1, path, "VAR")

    line_number = VAR_DATA_LINE_INDEX + 1
    tokens = _line_tokens(lines[VAR_DATA_LINE_INDEX])
    _require_column_count(tokens, VAR_MIN_COLUMNS, path, "VAR", line_number)

    replacements = {}
    for name, column_index in VAR_PARAMETER_COLUMNS.items():
        if name in values:
            replacements[column_index] = _format_parameter_value(
                name, values[name]
            )

    lines[VAR_DATA_LINE_INDEX] = _replace_tokens(
        lines[VAR_DATA_LINE_INDEX], replacements
    )
    return path, lines


def _build_soi_update(soi_path, values, material_index=0):
    values = _select_values(values, SOI_PARAMETER_COLUMNS)
    if not values:
        return None

    material_index = _validate_material_index(material_index)
    path = _coerce_path(soi_path, "SOI")
    lines = _read_lines(path, "SOI")
    line_index = SOI_HEADER_LINES + material_index
    line_number = line_index + 1
    _require_line_count(lines, line_index + 1, path, "SOI")

    tokens = _line_tokens(lines[line_index])
    _require_column_count(tokens, SOI_MIN_COLUMNS, path, "SOI", line_number)

    soil_theta_r = None
    if "thetaS" in values:
        soil_theta_r = _parse_float_token(
            tokens[0], "thetaR", path, line_number, 1
        )

    validate_parameter_values(values, soil_theta_r=soil_theta_r)

    replacements = {}
    for name, column_indexes in SOI_PARAMETER_COLUMNS.items():
        if name not in values:
            continue
        replacement = _format_parameter_value(name, values[name])
        for column_index in column_indexes:
            replacements[column_index] = replacement

    lines[line_index] = _replace_tokens(lines[line_index], replacements)
    return path, lines


def _ensure_mapping(values):
    if values is None:
        return {}
    if not hasattr(values, "items"):
        raise ParameterWriteError(
            "Parameter values must be a mapping of names to values."
        )
    return values


def _select_values(values, supported_columns):
    values = _ensure_mapping(values)
    return {
        name: values[name]
        for name in supported_columns
        if name in values
    }


def _resolve_member_path(run_dir, file_name, file_kind):
    if file_name is None:
        raise ParameterWriteError(f"{file_kind} file name is required.")

    file_path = _coerce_path(file_name, file_kind)
    if file_path.is_absolute():
        return file_path

    if run_dir is None:
        raise ParameterWriteError(
            f"run_dir is required for relative {file_kind} file paths."
        )

    return _coerce_path(run_dir, "run_dir") / file_path


def _coerce_path(path_value, file_kind):
    try:
        return Path(path_value)
    except TypeError as exc:
        raise ParameterWriteError(
            f"{file_kind} path must be path-like, got {path_value!r}."
        ) from exc


def _read_lines(path, file_kind):
    if not path.exists():
        raise ParameterWriteError(f"{file_kind} file not found: {path}")
    if not path.is_file():
        raise ParameterWriteError(f"{file_kind} path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8", newline="") as file_obj:
            return file_obj.read().splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise ParameterWriteError(
            f"Could not decode {file_kind} file as UTF-8: {path}"
        ) from exc
    except OSError as exc:
        raise ParameterWriteError(
            f"Could not read {file_kind} file {path}: {exc}"
        ) from exc


def _write_lines(path, lines, file_kind):
    try:
        with path.open("w", encoding="utf-8", newline="") as file_obj:
            file_obj.writelines(lines)
    except OSError as exc:
        raise ParameterWriteError(
            f"Could not write {file_kind} file {path}: {exc}"
        ) from exc


def _require_line_count(lines, minimum_count, path, file_kind):
    if len(lines) < minimum_count:
        raise ParameterWriteError(
            f"{file_kind} file has {len(lines)} line(s), "
            f"expected at least {minimum_count}: {path}"
        )


def _require_column_count(tokens, minimum_count, path, file_kind, line_number):
    if len(tokens) < minimum_count:
        raise ParameterWriteError(
            f"{file_kind} file line {line_number} has {len(tokens)} "
            f"column(s), expected at least {minimum_count}: {path}"
        )


def _line_tokens(line):
    body, _ = _split_line_ending(line)
    return [match.group(0) for match in TOKEN_RE.finditer(body)]


def _replace_tokens(line, replacements):
    body, line_ending = _split_line_ending(line)
    matches = list(TOKEN_RE.finditer(body))
    parts = []
    last_index = 0

    for token_index, match in enumerate(matches):
        parts.append(body[last_index:match.start()])
        parts.append(replacements.get(token_index, match.group(0)))
        last_index = match.end()

    parts.append(body[last_index:])
    return "".join(parts) + line_ending


def _split_line_ending(line):
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _format_parameter_value(name, value):
    if name == "JuvenileLeaves":
        return str(_as_int(value, name))
    return f"{_as_float(value, name):.12g}"


def _as_int(value, name):
    number = _as_float(value, name)
    if not number.is_integer():
        raise ParameterWriteError(f"{name} must be an integer, got {value!r}.")
    return int(number)


def _as_float(value, name):
    if isinstance(value, bool):
        raise ParameterWriteError(f"{name} must be numeric, got {value!r}.")

    try:
        if isinstance(value, str):
            number = float(value.strip().replace("D", "E").replace("d", "e"))
        else:
            number = float(value)
    except (TypeError, ValueError) as exc:
        raise ParameterWriteError(
            f"{name} must be numeric, got {value!r}."
        ) from exc

    if not math.isfinite(number):
        raise ParameterWriteError(
            f"{name} must be a finite number, got {value!r}."
        )
    return number


def _parse_float_token(token, name, path, line_number, column_number):
    try:
        return _as_float(token, name)
    except ParameterWriteError as exc:
        raise ParameterWriteError(
            f"Invalid {name} value at {path} line {line_number}, "
            f"column {column_number}: {token!r}."
        ) from exc


def _validate_material_index(material_index):
    if isinstance(material_index, bool):
        raise ParameterWriteError(
            f"material_index must be a non-negative integer, got {material_index!r}."
        )

    try:
        index = operator.index(material_index)
    except TypeError as exc:
        raise ParameterWriteError(
            f"material_index must be a non-negative integer, got {material_index!r}."
        ) from exc

    if index < 0:
        raise ParameterWriteError(
            f"material_index must be a non-negative integer, got {material_index!r}."
        )
    return index
