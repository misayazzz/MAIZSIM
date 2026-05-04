"""Morris 采样和样本表构建."""

from SALib.sample import morris
import pandas as pd

from .config import SensitivityConfigError


def values_from_row(parameters, sample_row):
    """从样本记录读取实际写入值."""
    result = {}
    for parameter in parameters:
        name = parameter["name"]
        result[name] = sample_row[f"actual_{name}"]
    return result


def at_or_above(value, threshold, tolerance):
    """按容差判断数值是否达到下限阈值."""
    return value >= threshold - tolerance


def at_or_below(value, threshold, tolerance):
    """按容差判断数值是否达到上限阈值."""
    return value <= threshold + tolerance


def below(value, threshold, tolerance):
    """判断数值是否严格低于阈值."""
    return value < threshold


def high_risk_reason(values, tolerance):
    """判断样本是否命中已知高危参数组合.

    输入为一个样本的实际写入参数字典, 输出为空字符串或高危原因. 规则来自
    SingleLayerLoam2D 失败探针结果. 缺少相关参数时跳过对应规则.
    """
    reasons = []
    alfa = values.get("Alfa")
    n_value = values.get("n")
    ks_value = values.get("Ks")
    theta_s = values.get("thetaS")
    diffx = values.get("Diffx")
    diffz = values.get("Diffz")

    if n_value is not None and below(n_value, 1.40, tolerance):
        reasons.append("n < 1.40")
    if ks_value is not None and at_or_below(ks_value, 10.0, tolerance):
        reasons.append("Ks <= 10")
    if (
        alfa is not None
        and n_value is not None
        and at_or_above(alfa, 0.032, tolerance)
        and at_or_below(n_value, 1.20, tolerance)
    ):
        reasons.append("Alfa >= 0.032 and n <= 1.20")
    if (
        alfa is not None
        and n_value is not None
        and at_or_above(alfa, 0.040, tolerance)
        and at_or_below(n_value, 1.20, tolerance)
    ):
        reasons.append("Alfa >= 0.040 and n <= 1.20")
    if (
        alfa is not None
        and n_value is not None
        and at_or_above(alfa, 0.050, tolerance)
        and at_or_below(n_value, 1.30, tolerance)
    ):
        reasons.append("Alfa >= 0.050 and n <= 1.30")
    if (
        ks_value is not None
        and alfa is not None
        and n_value is not None
        and at_or_below(ks_value, 10.0, tolerance)
        and at_or_above(alfa, 0.050, tolerance)
        and at_or_above(n_value, 1.72, tolerance)
    ):
        reasons.append("Ks <= 10 and Alfa >= 0.050 and n >= 1.72")
    if (
        ks_value is not None
        and alfa is not None
        and diffz is not None
        and at_or_below(ks_value, 10.0, tolerance)
        and at_or_above(alfa, 0.050, tolerance)
        and at_or_below(diffz, 1.0, tolerance)
    ):
        reasons.append("Ks <= 10 and Alfa >= 0.050 and Diffz <= 1.0")
    if (
        ks_value is not None
        and theta_s is not None
        and diffx is not None
        and diffz is not None
        and at_or_below(ks_value, 10.0, tolerance)
        and at_or_above(theta_s, 0.40, tolerance)
        and at_or_above(diffx, 10.0, tolerance)
        and at_or_below(diffz, 0.5, tolerance)
    ):
        reasons.append("Ks <= 10 and thetaS >= 0.40 and Diffx >= 10 and Diffz <= 0.5")
    return "; ".join(reasons)


def blocked_sample_rows(parameters, sample_table, tolerance):
    """返回命中高危规则的样本行."""
    rows = []
    for _, sample_row in sample_table.iterrows():
        values = values_from_row(parameters, sample_row)
        reason = high_risk_reason(values, tolerance)
        if reason:
            rows.append(
                {
                    "sample_id": int(sample_row["sample_id"]),
                    "trajectory_id": int(sample_row["trajectory_id"]),
                    "step_id": int(sample_row["step_id"]),
                    "changed_parameter": sample_row["changed_parameter"],
                    "risk_reason": reason,
                }
            )
    return rows


def build_problem(parameters):
    """根据参数配置构建 SALib problem."""
    return {
        "num_vars": len(parameters),
        "names": [parameter["name"] for parameter in parameters],
        "bounds": [[parameter["lower"], parameter["upper"]] for parameter in parameters],
    }


def generate_samples(parameters, trajectories, num_levels, seed):
    """生成 Morris 样本矩阵."""
    problem = build_problem(parameters)
    raw_matrix = morris.sample(
        problem,
        trajectories,
        num_levels=num_levels,
        optimal_trajectories=None,
        seed=seed,
    )
    return problem, raw_matrix


def generate_accepted_samples(parameters, trajectories, num_levels, seed, max_attempts, tolerance):
    """生成不含高危组合的 Morris 样本矩阵.

    每次采样后检查整套 Morris 设计. 只要任一样本命中高危组合, 就拒绝整套
    设计并用递增 seed 重新采样, 避免单点替换破坏 Morris 轨迹结构.
    """
    rejection_rows = []
    last_blocked_rows = []
    for attempt in range(1, max_attempts + 1):
        attempt_seed = seed + attempt - 1
        problem, raw_matrix = generate_samples(parameters, trajectories, num_levels, attempt_seed)
        sample_table = build_sample_table(parameters, raw_matrix)
        trajectory_issue = actual_trajectory_issue(parameters, sample_table)
        if trajectory_issue:
            blocked_rows = [trajectory_issue]
        else:
            blocked_rows = blocked_sample_rows(parameters, sample_table, tolerance)
        if not blocked_rows:
            summary = {
                "base_seed": seed,
                "accepted_seed": attempt_seed,
                "attempts": attempt,
                "rejected_designs": attempt - 1,
                "max_attempts": max_attempts,
                "rejection_tolerance": tolerance,
            }
            return problem, raw_matrix, sample_table, summary, rejection_rows

        last_blocked_rows = blocked_rows
        first_blocked = blocked_rows[0]
        rejection_rows.append(
            {
                "attempt": attempt,
                "seed": attempt_seed,
                "blocked_samples": len(blocked_rows),
                "first_sample_id": first_blocked["sample_id"],
                "first_trajectory_id": first_blocked["trajectory_id"],
                "first_step_id": first_blocked["step_id"],
                "first_changed_parameter": first_blocked["changed_parameter"],
                "first_risk_reason": first_blocked["risk_reason"],
            }
        )

    first_reason = ""
    if last_blocked_rows:
        first_reason = last_blocked_rows[0]["risk_reason"]
    raise SensitivityConfigError(
        f"超过最大拒绝采样次数仍未生成安全 Morris 样本: max_attempts={max_attempts}, "
        f"last_first_reason={first_reason}"
    )


def actual_value(parameter, value):
    """把采样值转换为实际写入值."""
    if parameter["value_type"] == "integer":
        return int(round(value))
    return float(value)


def changed_parameter_name(parameters, previous_row, current_row):
    """识别 Morris 轨迹中当前步改变的参数."""
    if previous_row is None:
        return ""
    names = []
    for index, parameter in enumerate(parameters):
        if previous_row[index] != current_row[index]:
            names.append(parameter["name"])
    return "|".join(names)


def changed_parameter_name_from_values(parameters, previous_values, current_values):
    """根据实际写入值识别当前步改变的参数."""
    if previous_values is None:
        return ""
    names = []
    for parameter, previous_value, current_value in zip(parameters, previous_values, current_values):
        if previous_value != current_value:
            names.append(parameter["name"])
    return "|".join(names)


def build_sample_table(parameters, raw_matrix):
    """生成样本记录表, 同时保留原始采样值和实际写入值."""
    dimension = len(parameters)
    rows = []
    previous_actual_values = None
    for row_index, raw_row in enumerate(raw_matrix):
        trajectory_id = row_index // (dimension + 1)
        step_id = row_index % (dimension + 1)
        previous_row = None
        if step_id > 0:
            previous_row = raw_matrix[row_index - 1]
        else:
            previous_actual_values = None

        actual_values = []
        for index, parameter in enumerate(parameters):
            actual_values.append(actual_value(parameter, float(raw_row[index])))

        row = {
            "sample_id": row_index + 1,
            "trajectory_id": trajectory_id + 1,
            "step_id": step_id,
            "changed_parameter": changed_parameter_name_from_values(
                parameters,
                previous_actual_values,
                actual_values,
            ),
            "raw_changed_parameter": changed_parameter_name(parameters, previous_row, raw_row),
        }
        for index, parameter in enumerate(parameters):
            name = parameter["name"]
            raw_value = float(raw_row[index])
            row[f"raw_{name}"] = raw_value
            row[f"actual_{name}"] = actual_values[index]
        rows.append(row)
        previous_actual_values = actual_values
    return pd.DataFrame(rows)


def actual_parameter_values(parameters, sample_row):
    """从样本记录中读取实际写入参数值."""
    return values_from_row(parameters, sample_row)


def analysis_matrix_from_sample_table(parameters, sample_table):
    """从样本表构建实际写入值矩阵."""
    column_names = [f"actual_{parameter['name']}" for parameter in parameters]
    return sample_table[column_names].to_numpy(dtype=float)


def actual_trajectory_issue(parameters, sample_table):
    """返回实际写入值轨迹结构问题."""
    dimension = len(parameters)
    actual_matrix = analysis_matrix_from_sample_table(parameters, sample_table)
    for row_index in range(len(sample_table)):
        step_id = row_index % (dimension + 1)
        if step_id == 0:
            continue
        changed_count = int((actual_matrix[row_index] != actual_matrix[row_index - 1]).sum())
        if changed_count != 1:
            sample_row = sample_table.iloc[row_index]
            return {
                "sample_id": int(sample_row["sample_id"]),
                "trajectory_id": int(sample_row["trajectory_id"]),
                "step_id": int(sample_row["step_id"]),
                "changed_parameter": sample_row["raw_changed_parameter"],
                "risk_reason": f"实际写入值破坏 Morris 单参数步进结构: changed_count={changed_count}",
            }
    return None


def validate_actual_trajectory(parameters, sample_table):
    """校验实际写入值仍保持 Morris 单参数步进结构."""
    issue = actual_trajectory_issue(parameters, sample_table)
    if issue:
        raise SensitivityConfigError(
            f"{issue['risk_reason']}: sample_id={issue['sample_id']}"
        )
