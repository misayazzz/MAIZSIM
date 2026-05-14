"""Observation table loading and vector construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .errors import ObservationError
except ImportError:  # pragma: no cover - used before errors.py is added.
    try:
        from da_framework.errors import ObservationError
    except ImportError:  # pragma: no cover

        class ObservationError(Exception):
            """Raised when observation data cannot be parsed or validated."""


SPEC_COLUMNS = (
    "date",
    "variable",
    "depth_top_cm",
    "depth_bottom_cm",
)
REQUIRED_COLUMNS = SPEC_COLUMNS + ("value", "std")
VARIABLE_ALIASES = {
    "lai": "LAI",
    "theta": "theta",
    "soil_water_content": "theta",
    "swc": "theta",
}


@dataclass(frozen=True)
class ObservationSpec:
    """Identity of one scalar observation in the assimilation vector."""

    date: pd.Timestamp
    variable: str
    depth_top_cm: float | None
    depth_bottom_cm: float | None


@dataclass(frozen=True)
class ObservationData:
    """Loaded observations aligned with the fixed observation-vector order."""

    specs: list[ObservationSpec]
    values: np.ndarray
    std: np.ndarray
    frame: pd.DataFrame
    dropped_rows: pd.DataFrame


def read_observations_csv(path):
    """Read, validate, sort, and vectorize a long-format observation CSV."""
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise ObservationError(f"观测 CSV 文件不存在: {source_path}")

    try:
        raw_frame = pd.read_csv(source_path)
    except pd.errors.EmptyDataError as exc:
        raise ObservationError(f"观测 CSV 为空: {source_path}") from exc
    except Exception as exc:
        raise ObservationError(
            f"观测 CSV 读取失败: {source_path}. 原因: {exc}"
        ) from exc

    frame = _canonicalize_frame(raw_frame, REQUIRED_COLUMNS, source_path)
    dropped_rows = _build_dropped_rows(frame)
    valid_frame = frame.loc[~frame.index.isin(dropped_rows.index)].copy()

    if valid_frame.empty:
        raise ObservationError(
            f"观测 CSV 没有有效观测: {source_path}. "
            "有效规则为 value 非缺失且 std > 0."
        )

    valid_frame = _sort_frame(valid_frame).reset_index(drop=True)
    output_frame = valid_frame.loc[:, REQUIRED_COLUMNS].copy()
    specs = _specs_from_normalized_frame(output_frame)
    values = output_frame["value"].to_numpy(dtype=float)
    std = output_frame["std"].to_numpy(dtype=float)

    return ObservationData(
        specs=specs,
        values=values,
        std=std,
        frame=output_frame,
        dropped_rows=dropped_rows.reset_index(drop=True),
    )


def build_observation_key(spec):
    """Build a stable key for matching model output to an observation spec."""
    return (
        _normalize_date_value(spec.date),
        _normalize_variable_value(spec.variable),
        _optional_float(spec.depth_top_cm),
        _optional_float(spec.depth_bottom_cm),
    )


def observation_specs_from_frame(frame):
    """Create sorted observation specs from a frame with spec columns."""
    normalized = _canonicalize_frame(frame, SPEC_COLUMNS, "DataFrame")
    normalized = _sort_frame(normalized).reset_index(drop=True)
    return _specs_from_normalized_frame(normalized)


def _canonicalize_frame(frame, required_columns, source_name):
    columns = _resolve_columns(frame.columns, required_columns, source_name)
    normalized = pd.DataFrame(index=frame.index)

    for column_name in required_columns:
        normalized[column_name] = frame.loc[:, columns[column_name]]
    normalized["_source_row_number"] = np.arange(len(frame), dtype=int) + 2

    row_numbers = normalized["_source_row_number"]
    normalized["date"] = _parse_dates(
        normalized["date"], row_numbers, source_name
    )
    normalized["variable"] = _normalize_variables(
        normalized["variable"], row_numbers, source_name
    )
    normalized["depth_top_cm"] = _coerce_optional_numeric(
        normalized["depth_top_cm"],
        "depth_top_cm",
        row_numbers,
        source_name,
    )
    normalized["depth_bottom_cm"] = _coerce_optional_numeric(
        normalized["depth_bottom_cm"],
        "depth_bottom_cm",
        row_numbers,
        source_name,
    )

    if "value" in required_columns:
        normalized["value"] = pd.to_numeric(
            normalized["value"], errors="coerce"
        )
    if "std" in required_columns:
        normalized["std"] = pd.to_numeric(
            normalized["std"], errors="coerce"
        )

    return normalized


def _resolve_columns(columns, required_columns, source_name):
    normalized_columns = {}
    duplicate_columns = []

    for column in columns:
        key = _normalize_column_name(column)
        if key in normalized_columns:
            duplicate_columns.append(key)
        else:
            normalized_columns[key] = column

    if duplicate_columns:
        duplicates = ", ".join(sorted(set(duplicate_columns)))
        raise ObservationError(
            f"观测表字段重复: {source_name}. 重复字段: {duplicates}"
        )

    missing = [
        column for column in required_columns if column not in normalized_columns
    ]
    if missing:
        available = ", ".join(str(column) for column in columns)
        missing_text = ", ".join(missing)
        raise ObservationError(
            f"观测表缺少必要字段: {source_name}. "
            f"缺少: {missing_text}. 可用字段: {available}"
        )

    return {column: normalized_columns[column] for column in required_columns}


def _normalize_column_name(value):
    return str(value).strip().lower()


def _parse_dates(values, row_numbers, source_name):
    text_values = values.astype("string").str.strip()
    try:
        parsed = pd.to_datetime(
            text_values, errors="coerce", format="mixed"
        )
    except TypeError:
        parsed = pd.to_datetime(text_values, errors="coerce")

    invalid = parsed.isna()
    if invalid.any():
        rows = _format_rows(row_numbers, invalid)
        samples = _format_samples(text_values.loc[invalid])
        raise ObservationError(
            f"观测日期解析失败: {source_name}. 行: {rows}. 示例: {samples}"
        )

    return parsed.dt.normalize()


def _normalize_variables(values, row_numbers, source_name):
    text_values = values.astype("string").str.strip().str.lower()
    normalized = text_values.map(VARIABLE_ALIASES)
    invalid = normalized.isna()

    if invalid.any():
        rows = _format_rows(row_numbers, invalid)
        samples = _format_samples(values.loc[invalid])
        allowed = ", ".join(["LAI", "lai", "theta", "soil_water_content", "swc"])
        raise ObservationError(
            f"观测变量无法识别: {source_name}. 行: {rows}. "
            f"示例: {samples}. 支持变量: {allowed}"
        )

    return normalized.astype(object)


def _coerce_optional_numeric(values, column_name, row_numbers, source_name):
    text_values = values.astype("string").str.strip()
    missing = text_values.isna() | text_values.eq("")
    numeric = pd.to_numeric(text_values, errors="coerce")
    invalid = numeric.isna() & ~missing

    if invalid.any():
        rows = _format_rows(row_numbers, invalid)
        samples = _format_samples(values.loc[invalid])
        raise ObservationError(
            f"观测字段 {column_name} 无法解析为数值: {source_name}. "
            f"行: {rows}. 示例: {samples}"
        )

    numeric = numeric.astype(float)
    numeric.loc[missing] = np.nan
    return numeric


def _build_dropped_rows(frame):
    value_invalid = frame["value"].isna()
    std_invalid = frame["std"].isna() | frame["std"].le(0)
    drop_mask = value_invalid | std_invalid

    dropped_columns = list(REQUIRED_COLUMNS) + ["_source_row_number"]
    dropped = frame.loc[drop_mask, dropped_columns].copy()
    if dropped.empty:
        return dropped.assign(drop_reason=pd.Series(dtype=object))

    reasons = []
    for index in dropped.index:
        row_reasons = []
        if value_invalid.loc[index]:
            row_reasons.append("value_missing_or_invalid")
        if std_invalid.loc[index]:
            row_reasons.append("std_missing_or_non_positive")
        reasons.append(";".join(row_reasons))

    dropped["drop_reason"] = reasons
    return dropped


def _sort_frame(frame):
    return frame.sort_values(
        list(SPEC_COLUMNS),
        ascending=True,
        kind="mergesort",
        na_position="last",
    )


def _specs_from_normalized_frame(frame):
    specs = []
    for row in frame.loc[:, SPEC_COLUMNS].itertuples(index=False):
        specs.append(
            ObservationSpec(
                date=_normalize_date_value(row.date),
                variable=_normalize_variable_value(row.variable),
                depth_top_cm=_optional_float(row.depth_top_cm),
                depth_bottom_cm=_optional_float(row.depth_bottom_cm),
            )
        )
    return specs


def _normalize_date_value(value):
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ObservationError(f"观测日期无法解析: {value}") from exc

    if pd.isna(parsed):
        raise ObservationError(f"观测日期为空或无效: {value}")
    return parsed.normalize()


def _normalize_variable_value(value):
    if pd.isna(value):
        key = ""
    else:
        key = str(value).strip().lower()

    if key not in VARIABLE_ALIASES:
        allowed = ", ".join(["LAI", "lai", "theta", "soil_water_content", "swc"])
        raise ObservationError(
            f"观测变量无法识别: {value}. 支持变量: {allowed}"
        )
    return VARIABLE_ALIASES[key]


def _optional_float(value):
    if pd.isna(value):
        return None
    return float(value)


def _format_rows(row_numbers, mask):
    rows = row_numbers.loc[mask].astype(int).head(5).astype(str).tolist()
    suffix = "" if mask.sum() <= 5 else "..."
    return ", ".join(rows) + suffix


def _format_samples(values):
    samples = values.astype("string").head(5).fillna("<NA>").tolist()
    return ", ".join(samples)


__all__ = [
    "ObservationData",
    "ObservationSpec",
    "build_observation_key",
    "observation_specs_from_frame",
    "read_observations_csv",
]
