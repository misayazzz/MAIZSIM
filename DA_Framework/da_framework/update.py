"""IES update and parameter bounds utilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParameterBounds:
    """单个参数的上下界."""

    name: str
    lower: float
    upper: float


@dataclass(frozen=True)
class IESUpdateResult:
    """单次 IES 更新的核心结果."""

    updated_parameters: np.ndarray
    kalman_gain: np.ndarray
    innovations: np.ndarray
    forecast_mean: np.ndarray
    simulated_mean: np.ndarray
    bound_hits: np.ndarray


def halfway_back_to_bounds(values, forecast_values, bounds):
    """把越界参数按半程回拉规则拉回边界附近."""

    bounded_values = _as_2d_float_array(values, "values").copy()
    forecast_array = _as_2d_float_array(forecast_values, "forecast_values")
    if bounded_values.shape != forecast_array.shape:
        raise ValueError(
            "values 和 forecast_values 形状必须一致, "
            f"当前分别为 {bounded_values.shape} 和 {forecast_array.shape}."
        )

    lower, upper = _bounds_limits(bounds, "bounds")
    lower_hits = bounded_values < lower
    upper_hits = bounded_values > upper
    hit_mask = lower_hits | upper_hits

    bounded_values[lower_hits] = (forecast_array[lower_hits] + lower) / 2.0
    bounded_values[upper_hits] = (forecast_array[upper_hits] + upper) / 2.0
    return bounded_values, hit_mask


def apply_parameter_bounds(values, forecast_values, parameter_names, bounds_by_name):
    """按参数名逐行应用边界半程回拉."""

    bounded_values = _as_2d_float_array(values, "values").copy()
    forecast_array = _as_2d_float_array(forecast_values, "forecast_values")
    if bounded_values.shape != forecast_array.shape:
        raise ValueError(
            "values 和 forecast_values 形状必须一致, "
            f"当前分别为 {bounded_values.shape} 和 {forecast_array.shape}."
        )

    names = _parameter_name_list(parameter_names, bounded_values.shape[0])
    hit_mask = np.zeros_like(bounded_values, dtype=bool)
    if bounds_by_name is None:
        return bounded_values, hit_mask
    if not isinstance(bounds_by_name, Mapping):
        raise TypeError("bounds_by_name 必须是以参数名为键的映射.")

    for row_index, name in enumerate(names):
        bounds = bounds_by_name.get(name)
        if bounds is None:
            continue
        row_values, row_hits = halfway_back_to_bounds(
            bounded_values[row_index : row_index + 1, :],
            forecast_array[row_index : row_index + 1, :],
            bounds,
        )
        bounded_values[row_index, :] = row_values[0, :]
        hit_mask[row_index, :] = row_hits[0, :]
    return bounded_values, hit_mask


def ies_update(
    x_forecast,
    y_forecast,
    observations,
    observation_std,
    parameter_names,
    bounds_by_name=None,
    rng=None,
    n_iter_scale=1.0,
    perturb_observations=True,
):
    """执行一次 Ensemble Smoother 参数更新."""

    x_array = _as_2d_float_array(x_forecast, "x_forecast")
    y_array = _as_2d_float_array(y_forecast, "y_forecast")
    obs_array = _as_1d_float_array(observations, "observations")
    std_array = _as_1d_float_array(observation_std, "observation_std")

    n_parameters, n_ensemble = x_array.shape
    n_observations, y_ensemble = y_array.shape
    if n_ensemble < 2:
        raise ValueError(f"x_forecast 至少需要 2 个集合成员, 当前 Ne={n_ensemble}.")
    if y_ensemble != n_ensemble:
        raise ValueError(
            "x_forecast 和 y_forecast 的集合成员数必须一致, "
            f"当前分别为 {n_ensemble} 和 {y_ensemble}."
        )
    if obs_array.shape[0] != n_observations:
        raise ValueError(
            "observations 长度必须等于 y_forecast 的观测维度, "
            f"当前分别为 {obs_array.shape[0]} 和 {n_observations}."
        )
    if std_array.shape[0] != n_observations:
        raise ValueError(
            "observation_std 长度必须等于 y_forecast 的观测维度, "
            f"当前分别为 {std_array.shape[0]} 和 {n_observations}."
        )
    if np.any(std_array <= 0.0):
        raise ValueError("observation_std 必须全部大于 0.")

    iter_scale = float(n_iter_scale)
    if not np.isfinite(iter_scale) or iter_scale <= 0.0:
        raise ValueError("n_iter_scale 必须是大于 0 的有限数值.")

    names = _parameter_name_list(parameter_names, n_parameters)
    scaled_std = std_array * np.sqrt(iter_scale)

    forecast_mean = x_array.mean(axis=1)
    simulated_mean = y_array.mean(axis=1)
    x_anomalies = x_array - forecast_mean[:, None]
    y_anomalies = y_array - simulated_mean[:, None]

    cxy = x_anomalies @ y_anomalies.T / (n_ensemble - 1)
    cyy = y_anomalies @ y_anomalies.T / (n_ensemble - 1)
    observation_error = np.diag(scaled_std**2)
    kalman_gain = _compute_kalman_gain(cxy, cyy + observation_error)

    if perturb_observations:
        generator = _coerce_rng(rng)
        noise = generator.normal(
            loc=0.0,
            scale=scaled_std[:, None],
            size=(n_observations, n_ensemble),
        )
    else:
        noise = np.zeros((n_observations, n_ensemble), dtype=float)

    innovations = obs_array[:, None] + noise - y_array
    updated_parameters = x_array + kalman_gain @ innovations
    updated_parameters, bound_hits = apply_parameter_bounds(
        updated_parameters,
        x_array,
        names,
        bounds_by_name,
    )

    return IESUpdateResult(
        updated_parameters=updated_parameters,
        kalman_gain=kalman_gain,
        innovations=innovations,
        forecast_mean=forecast_mean,
        simulated_mean=simulated_mean,
        bound_hits=bound_hits,
    )


def _compute_kalman_gain(cxy, system_matrix):
    """计算 Cxy @ inv(Cyy + R), 奇异时退回伪逆."""

    try:
        return np.linalg.solve(system_matrix.T, cxy.T).T
    except np.linalg.LinAlgError:
        try:
            return cxy @ np.linalg.pinv(system_matrix)
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                "无法计算 Kalman gain: Cyy + R 奇异, 且 np.linalg.pinv 失败."
            ) from exc


def _as_2d_float_array(values, label):
    array = np.asarray(values, dtype=float)
    if array.ndim != 2:
        raise ValueError(f"{label} 必须是二维矩阵, 当前 ndim={array.ndim}.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} 包含 NaN 或 inf.")
    return array


def _as_1d_float_array(values, label):
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{label} 必须是一维向量, 当前 ndim={array.ndim}.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} 包含 NaN 或 inf.")
    return array


def _bounds_limits(bounds, label):
    try:
        if isinstance(bounds, Mapping):
            lower = float(bounds["lower"])
            upper = float(bounds["upper"])
        else:
            lower = float(bounds.lower)
            upper = float(bounds.upper)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须提供可转换为 float 的 lower 和 upper.") from exc

    if not np.all(np.isfinite([lower, upper])):
        raise ValueError(f"{label} 的 lower 和 upper 必须是有限数值.")
    if lower > upper:
        raise ValueError(f"{label} 的 lower 不能大于 upper.")
    return lower, upper


def _parameter_name_list(parameter_names, expected_length):
    if isinstance(parameter_names, str):
        raise TypeError("parameter_names 必须是参数名序列, 不能是单个字符串.")
    names = list(parameter_names)
    if len(names) != expected_length:
        raise ValueError(
            "parameter_names 长度必须等于参数矩阵行数, "
            f"当前分别为 {len(names)} 和 {expected_length}."
        )
    cleaned_names = []
    for index, name in enumerate(names, 1):
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"parameter_names 第 {index} 项必须是非空字符串.")
        cleaned_names.append(name.strip())
    return cleaned_names


def _coerce_rng(rng):
    if rng is None or isinstance(rng, (int, np.integer)):
        return np.random.default_rng(rng)
    if not hasattr(rng, "normal"):
        raise TypeError("rng 必须是 numpy 随机数生成器或整数种子.")
    return rng


__all__ = [
    "IESUpdateResult",
    "ParameterBounds",
    "apply_parameter_bounds",
    "halfway_back_to_bounds",
    "ies_update",
]
