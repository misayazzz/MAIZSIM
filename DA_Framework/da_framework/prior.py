"""Prior ensemble generation utilities."""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Integral

import numpy as np
import pandas as pd


def sample_uniform_prior(parameters, n_ensemble, rng=None):
    """按参数上下界生成均匀分布先验集合."""

    ensemble_size = _validate_ensemble_size(n_ensemble)
    parameter_list = list(parameters)
    if not parameter_list:
        raise ValueError("parameters 不能为空.")

    generator = _coerce_rng(rng)
    data = {}
    names = []
    for index, parameter in enumerate(parameter_list, 1):
        name, lower, upper = _parameter_limits(parameter, index)
        if name in data:
            raise ValueError(f"参数名重复: {name}.")
        names.append(name)
        data[name] = generator.uniform(lower, upper, size=ensemble_size)

    return pd.DataFrame(data, columns=names)


def dataframe_to_parameter_matrix(df, parameter_names):
    """将参数 DataFrame 转为 p x Ne 参数矩阵."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df 必须是 pandas.DataFrame.")
    names = _parameter_name_list(parameter_names)
    missing_names = [name for name in names if name not in df.columns]
    if missing_names:
        raise ValueError(f"DataFrame 缺少参数列: {missing_names}.")
    return df.loc[:, names].to_numpy(dtype=float).T


def matrix_to_dataframe(matrix, parameter_names):
    """将 p x Ne 参数矩阵转为参数 DataFrame."""

    matrix_array = np.asarray(matrix, dtype=float)
    if matrix_array.ndim != 2:
        raise ValueError(f"matrix 必须是二维矩阵, 当前 ndim={matrix_array.ndim}.")
    names = _parameter_name_list(parameter_names)
    if matrix_array.shape[0] != len(names):
        raise ValueError(
            "parameter_names 长度必须等于 matrix 行数, "
            f"当前分别为 {len(names)} 和 {matrix_array.shape[0]}."
        )
    return pd.DataFrame(matrix_array.T, columns=names)


def _parameter_limits(parameter, index):
    name = _read_parameter_field(parameter, "name", index)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"parameters 第 {index} 项 name 必须是非空字符串.")
    lower = _as_float(_read_parameter_field(parameter, "lower", index), "lower", index)
    upper = _as_float(_read_parameter_field(parameter, "upper", index), "upper", index)
    if not np.all(np.isfinite([lower, upper])):
        raise ValueError(f"parameters 第 {index} 项 lower/upper 必须是有限数值.")
    if lower > upper:
        raise ValueError(f"parameters 第 {index} 项 lower 不能大于 upper.")
    return name.strip(), lower, upper


def _read_parameter_field(parameter, field_name, index):
    if isinstance(parameter, Mapping):
        try:
            return parameter[field_name]
        except KeyError as exc:
            raise ValueError(f"parameters 第 {index} 项缺少字段 {field_name}.") from exc
    try:
        return getattr(parameter, field_name)
    except AttributeError as exc:
        raise ValueError(f"parameters 第 {index} 项缺少属性 {field_name}.") from exc


def _as_float(value, field_name, index):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"parameters 第 {index} 项 {field_name} 必须可转换为 float."
        ) from exc


def _validate_ensemble_size(n_ensemble):
    if not isinstance(n_ensemble, Integral):
        raise TypeError("n_ensemble 必须是正整数.")
    if n_ensemble <= 0:
        raise ValueError("n_ensemble 必须大于 0.")
    return int(n_ensemble)


def _parameter_name_list(parameter_names):
    if isinstance(parameter_names, str):
        raise TypeError("parameter_names 必须是参数名序列, 不能是单个字符串.")
    names = list(parameter_names)
    if not names:
        raise ValueError("parameter_names 不能为空.")
    cleaned_names = []
    for index, name in enumerate(names, 1):
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"parameter_names 第 {index} 项必须是非空字符串.")
        cleaned_names.append(name.strip())
    return cleaned_names


def _coerce_rng(rng):
    if rng is None or isinstance(rng, (int, np.integer)):
        return np.random.default_rng(rng)
    if not hasattr(rng, "uniform"):
        raise TypeError("rng 必须是 numpy 随机数生成器或整数种子.")
    return rng


__all__ = [
    "dataframe_to_parameter_matrix",
    "matrix_to_dataframe",
    "sample_uniform_prior",
]
