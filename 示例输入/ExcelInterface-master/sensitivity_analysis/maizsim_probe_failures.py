"""靶向探索 MAIZSIM 参数组合的数值失败和慢运行边界."""

from datetime import datetime
from pathlib import Path
import argparse
import sys

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from maizsim_sensitivity.config import SensitivityConfigError
from maizsim_sensitivity.config import read_config
from maizsim_sensitivity.files import ensure_new_analysis_dir
from maizsim_sensitivity.files import prepare_sample_dir
from maizsim_sensitivity.files import write_parameters
from maizsim_sensitivity.runner import run_samples


DEFAULT_BOUNDS = SCRIPT_DIR.parent / "Example input" / "SingleLayerLoam2D" / "sensitivity_parameter_bounds.toml"


def parse_args(arguments=None):
    """解析命令行参数."""
    parser = argparse.ArgumentParser(description="Probe MAIZSIM parameter failure boundaries.")
    parser.add_argument(
        "--bounds",
        default=str(DEFAULT_BOUNDS),
        help="Path to sensitivity_parameter_bounds.toml.",
    )
    parser.add_argument(
        "--analysis-id",
        help="Output directory name under run_root.",
    )
    parser.add_argument(
        "--output-root",
        help="Output root for failure probe results. Default is the failure_probes sibling of sensitivity_runs.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=20,
        help="Parallel worker count.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=240,
        help="Per-case model timeout in seconds.",
    )
    parser.add_argument(
        "--slow-seconds",
        type=float,
        default=120.0,
        help="Successful cases at or above this duration are marked slow.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N generated cases for quick checks.",
    )
    parser.add_argument(
        "--case-set",
        choices=["targeted", "p0p1", "crop"],
        default="targeted",
        help="Probe case matrix to run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate cases without copying directories or running the model.",
    )
    return parser.parse_args(arguments)


def analysis_id_for_args(args):
    """生成诊断分析 ID."""
    if args.analysis_id:
        return args.analysis_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"failure_probe_{timestamp}"


def output_root_for_args(config, args):
    """解析探针输出根目录."""
    if args.output_root:
        path = Path(args.output_root).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (config["project_dir"] / path).resolve()
    return (config["run_root"].parent / "failure_probes").resolve()


def current_values(parameters):
    """从参数配置读取基线当前值."""
    values = {}
    for parameter in parameters:
        values[parameter["name"]] = parameter["current"]
    return values


def add_case(cases, base_values, case_name, group, hypothesis, overrides):
    """向诊断矩阵添加一个参数组合."""
    values = dict(base_values)
    values.update(overrides)
    row = {
        "case_name": case_name,
        "probe_group": group,
        "hypothesis": hypothesis,
    }
    row.update(values)
    cases.append(row)


def add_alpha_n_grid(cases, base_values):
    """添加 Alfa 与 n 的交互诊断矩阵."""
    background = {
        "JuvenileLeaves": 16,
        "Rmax_LTAR": 0.526667,
        "Rmax_LTIR": 0.933333,
        "PhyllFrmTassel": 5.0,
        "StayGreen": 8.0,
        "LM_min": 130.0,
        "Diffx": 2.4,
        "Diffz": 1.333333,
        "thetaR": 0.066667,
        "thetaS": 0.40,
        "Ks": 23.333333,
    }
    alfa_values = [0.015, 0.032, 0.036, 0.040, 0.045, 0.055, 0.075]
    n_values = [1.2, 1.3, 1.4, 1.56, 1.72, 1.866667]
    for alfa in alfa_values:
        for n_value in n_values:
            add_case(
                cases,
                base_values,
                f"alpha_n_lowdiff_a{alfa:g}_n{n_value:g}",
                "alpha_n_lowdiff",
                "检查低 Diffx 背景下 Alfa 与 n 的交互失效边界.",
                {**background, "Alfa": alfa, "n": n_value},
            )


def add_low_ks_theta_diff_grid(cases, base_values):
    """添加低 Ks 背景下 thetaS 与 Diffx 的交互诊断矩阵."""
    background = {
        "JuvenileLeaves": 21,
        "Rmax_LTAR": 0.526667,
        "Rmax_LTIR": 0.8,
        "PhyllFrmTassel": 5.0,
        "StayGreen": 2.0,
        "LM_min": 130.0,
        "Diffz": 0.5,
        "thetaR": 0.066667,
        "Alfa": 0.055,
        "n": 1.866667,
        "Ks": 5.0,
    }
    theta_s_values = [0.35, 0.40, 0.43, 0.45, 0.50]
    diffx_values = [2.4, 10.0, 17.466667, 20.0]
    for theta_s in theta_s_values:
        for diffx in diffx_values:
            add_case(
                cases,
                base_values,
                f"lowks_theta_diff_t{theta_s:g}_dx{diffx:g}",
                "lowks_theta_diff",
                "检查低 Ks 高 Alfa 背景下 thetaS 与 Diffx 的交互失效边界.",
                {**background, "thetaS": theta_s, "Diffx": diffx},
            )


def add_ks_theta_grid(cases, base_values):
    """添加 Ks 与 thetaS 的交互诊断矩阵."""
    background = {
        "JuvenileLeaves": 21,
        "Rmax_LTAR": 0.526667,
        "Rmax_LTIR": 0.8,
        "PhyllFrmTassel": 5.0,
        "StayGreen": 2.0,
        "LM_min": 130.0,
        "Diffx": 17.466667,
        "Diffz": 0.5,
        "thetaR": 0.066667,
        "Alfa": 0.055,
        "n": 1.866667,
    }
    ks_values = [5.0, 10.0, 15.0, 20.0, 24.96]
    theta_s_values = [0.35, 0.40, 0.45, 0.50]
    for ks_value in ks_values:
        for theta_s in theta_s_values:
            add_case(
                cases,
                base_values,
                f"ks_theta_ks{ks_value:g}_t{theta_s:g}",
                "ks_theta",
                "检查高 Alfa 高 n 背景下 Ks 与 thetaS 的交互失效边界.",
                {**background, "Ks": ks_value, "thetaS": theta_s},
            )


def add_root_extreme_grid(cases, base_values):
    """添加局部安全土壤背景下根系扩散极值诊断矩阵."""
    diffx_values = [2.4, 10.0, 18.0, 20.0, 22.0, 25.0]
    diffz_values = [0.5, 0.9, 1.0, 1.333333, 3.0]
    for diffx in diffx_values:
        for diffz in diffz_values:
            add_case(
                cases,
                base_values,
                f"root_extreme_dx{diffx:g}_dz{diffz:g}",
                "root_extreme",
                "检查当前局部土壤边界下根系扩散极值是否单独触发慢运行.",
                {"Diffx": diffx, "Diffz": diffz},
            )


def add_water_content_grid(cases, base_values):
    """添加局部安全形状参数下含水量端点诊断矩阵."""
    theta_r_values = [0.04, 0.066667, 0.078, 0.10, 0.12]
    theta_s_values = [0.35, 0.40, 0.43, 0.45, 0.50]
    for theta_r in theta_r_values:
        for theta_s in theta_s_values:
            if theta_r >= theta_s:
                continue
            add_case(
                cases,
                base_values,
                f"water_content_tr{theta_r:g}_ts{theta_s:g}",
                "water_content",
                "检查当前 Alfa/n/Ks 背景下 thetaR 与 thetaS 端点是否单独触发慢运行.",
                {"thetaR": theta_r, "thetaS": theta_s},
            )


def build_probe_cases(parameters):
    """构建靶向失败边界诊断矩阵."""
    base_values = current_values(parameters)
    cases = []
    add_case(cases, base_values, "baseline_current", "baseline", "确认基线运行耗时和输出解析.", {})
    add_alpha_n_grid(cases, base_values)
    add_low_ks_theta_diff_grid(cases, base_values)
    add_ks_theta_grid(cases, base_values)
    add_root_extreme_grid(cases, base_values)
    add_water_content_grid(cases, base_values)
    frame = pd.DataFrame(cases)
    frame.insert(0, "case_id", range(1, len(frame) + 1))
    return frame


def add_p0p1_case(cases, base_values, case_name, group, hypothesis, soil_overrides):
    """添加固定作物基线的 P0/P1 诊断组合."""
    add_case(cases, base_values, case_name, group, hypothesis, soil_overrides)


def build_p0p1_cases(parameters):
    """构建固定作物基线的 P0/P1 失效边界诊断矩阵."""
    base_values = current_values(parameters)
    cases = []
    add_p0p1_case(cases, base_values, "C00_baseline", "control", "基线耗时参照.", {})

    alpha_n_cases = [
        ("T01_low_n_low_alfa", 0.0667, 0.400, 0.015, 1.20, 23.333, 2.4, 1.333),
        ("T02_known_timeout_anchor", 0.0667, 0.400, 0.055, 1.20, 23.333, 2.4, 1.333),
        ("T03_local_alfa_high_low_n", 0.0667, 0.400, 0.040, 1.20, 23.333, 2.4, 1.333),
        ("T04_alfa_045_low_n", 0.0667, 0.400, 0.045, 1.20, 23.333, 2.4, 1.333),
        ("T05_alfa_050_low_n", 0.0667, 0.400, 0.050, 1.20, 23.333, 2.4, 1.333),
        ("T06_high_alfa_n_140", 0.0667, 0.400, 0.055, 1.40, 23.333, 2.4, 1.333),
        ("T07_high_alfa_base_n", 0.0667, 0.400, 0.055, 1.56, 23.333, 2.4, 1.333),
        ("T08_high_alfa_n_130", 0.0667, 0.400, 0.055, 1.30, 23.333, 2.4, 1.333),
        ("T09_alfa_050_n_130", 0.0667, 0.400, 0.050, 1.30, 23.333, 2.4, 1.333),
    ]
    for case_name, theta_r, theta_s, alfa, n_value, ks_value, diffx, diffz in alpha_n_cases:
        add_p0p1_case(
            cases,
            base_values,
            case_name,
            "p0p1_alpha_n",
            "固定作物基线, 检查 Alfa 与 n 的失效边界.",
            {
                "thetaR": theta_r,
                "thetaS": theta_s,
                "Alfa": alfa,
                "n": n_value,
                "Ks": ks_value,
                "Diffx": diffx,
                "Diffz": diffz,
            },
        )

    low_ks_cases = [
        ("O01_low_ks_safe_anchor", 0.0667, 0.350, 0.055, 1.8667, 5.0, 17.4667, 0.5),
        ("O02_known_orthomin_anchor", 0.0667, 0.450, 0.055, 1.8667, 5.0, 17.4667, 0.5),
        ("O03_thetaS_040", 0.0667, 0.400, 0.055, 1.8667, 5.0, 17.4667, 0.5),
        ("O04_thetaS_043", 0.0667, 0.430, 0.055, 1.8667, 5.0, 17.4667, 0.5),
        ("O05_low_diffx", 0.0667, 0.450, 0.055, 1.8667, 5.0, 2.4, 0.5),
        ("O06_mid_diffx", 0.0667, 0.450, 0.055, 1.8667, 5.0, 10.0, 0.5),
        ("O07_raise_diffz", 0.0667, 0.450, 0.055, 1.8667, 5.0, 17.4667, 1.0),
        ("O08_raise_ks", 0.0667, 0.450, 0.055, 1.8667, 10.0, 17.4667, 0.5),
        ("O09_local_alfa_high", 0.0667, 0.450, 0.040, 1.8667, 5.0, 17.4667, 0.5),
        ("O10_local_n_high", 0.0667, 0.450, 0.055, 1.72, 5.0, 17.4667, 0.5),
    ]
    for case_name, theta_r, theta_s, alfa, n_value, ks_value, diffx, diffz in low_ks_cases:
        add_p0p1_case(
            cases,
            base_values,
            case_name,
            "p0p1_low_ks",
            "固定作物基线, 检查低 Ks 背景的 thetaS, Diffx, Diffz 失效边界.",
            {
                "thetaR": theta_r,
                "thetaS": theta_s,
                "Alfa": alfa,
                "n": n_value,
                "Ks": ks_value,
                "Diffx": diffx,
                "Diffz": diffz,
            },
        )

    root_cases = [
        ("R01_low_root_diff", 0.078, 0.430, 0.036, 1.56, 24.96, 2.4, 0.5),
        ("R02_high_x_low_z", 0.078, 0.430, 0.036, 1.56, 24.96, 17.4667, 0.5),
        ("R03_low_x_mid_z", 0.078, 0.430, 0.036, 1.56, 24.96, 2.4, 1.333),
        ("G01_local_worst_corner", 0.086, 0.473, 0.040, 1.40, 22.5, 18.0, 0.9),
    ]
    for case_name, theta_r, theta_s, alfa, n_value, ks_value, diffx, diffz in root_cases:
        add_p0p1_case(
            cases,
            base_values,
            case_name,
            "p0p1_root_local",
            "固定作物基线, 检查根系极端和局部边界角点.",
            {
                "thetaR": theta_r,
                "thetaS": theta_s,
                "Alfa": alfa,
                "n": n_value,
                "Ks": ks_value,
                "Diffx": diffx,
                "Diffz": diffz,
            },
        )

    frame = pd.DataFrame(cases)
    frame.insert(0, "case_id", range(1, len(frame) + 1))
    return frame


def crop_parameter_names(parameters):
    """读取作物物候和叶片参数名."""
    names = []
    for parameter in parameters:
        if parameter.get("category") == "crop_phenology_leaf":
            names.append(parameter["name"])
    return names


def parameter_lookup(parameters):
    """按参数名索引参数配置."""
    lookup = {}
    for parameter in parameters:
        lookup[parameter["name"]] = parameter
    return lookup


def bounds_for_names(lookup, names, lower_field, upper_field):
    """按指定字段读取一组上下界."""
    bounds = {}
    for name in names:
        bounds[name] = {
            "lower": lookup[name][lower_field],
            "upper": lookup[name][upper_field],
        }
    return bounds


def historical_crop_bounds():
    """返回宽边界 smoke 中出现过的作物参数端点."""
    return {
        "JuvenileLeaves": {"lower": 16, "upper": 21},
        "Rmax_LTAR": {"lower": 0.42, "upper": 0.58},
        "Rmax_LTIR": {"lower": 0.80, "upper": 1.00},
        "PhyllFrmTassel": {"lower": 2.666667, "upper": 5.0},
        "StayGreen": {"lower": 2.0, "upper": 8.0},
        "LM_min": {"lower": 103.333333, "upper": 130.0},
    }


def values_from_bounds(bounds, side):
    """从上下界字典抽取一组参数值."""
    values = {}
    for name, limits in bounds.items():
        values[name] = limits[side]
    return values


def add_single_crop_cases(cases, base_values, bounds, group, prefix, note):
    """添加作物参数单独端点探针."""
    for name, limits in bounds.items():
        for side in ["lower", "upper"]:
            add_case(
                cases,
                base_values,
                f"{prefix}_{name}_{side}",
                group,
                note,
                {name: limits[side]},
            )


def add_crop_corner_cases(cases, base_values, bounds, group, prefix, note):
    """添加作物参数组合角点探针."""
    lower_values = values_from_bounds(bounds, "lower")
    upper_values = values_from_bounds(bounds, "upper")
    add_case(cases, base_values, f"{prefix}_all_lower", group, note, lower_values)
    add_case(cases, base_values, f"{prefix}_all_upper", group, note, upper_values)
    add_case(
        cases,
        base_values,
        f"{prefix}_fast_small_canopy",
        group,
        note,
        {
            "JuvenileLeaves": lower_values["JuvenileLeaves"],
            "Rmax_LTAR": upper_values["Rmax_LTAR"],
            "Rmax_LTIR": upper_values["Rmax_LTIR"],
            "PhyllFrmTassel": lower_values["PhyllFrmTassel"],
            "StayGreen": lower_values["StayGreen"],
            "LM_min": lower_values["LM_min"],
        },
    )
    add_case(
        cases,
        base_values,
        f"{prefix}_slow_large_canopy",
        group,
        note,
        {
            "JuvenileLeaves": upper_values["JuvenileLeaves"],
            "Rmax_LTAR": lower_values["Rmax_LTAR"],
            "Rmax_LTIR": lower_values["Rmax_LTIR"],
            "PhyllFrmTassel": upper_values["PhyllFrmTassel"],
            "StayGreen": upper_values["StayGreen"],
            "LM_min": upper_values["LM_min"],
        },
    )
    add_case(
        cases,
        base_values,
        f"{prefix}_late_silk_high_rates",
        group,
        note,
        {
            "JuvenileLeaves": upper_values["JuvenileLeaves"],
            "Rmax_LTAR": upper_values["Rmax_LTAR"],
            "Rmax_LTIR": upper_values["Rmax_LTIR"],
            "PhyllFrmTassel": upper_values["PhyllFrmTassel"],
        },
    )
    add_case(
        cases,
        base_values,
        f"{prefix}_early_silk_low_rates",
        group,
        note,
        {
            "JuvenileLeaves": lower_values["JuvenileLeaves"],
            "Rmax_LTAR": lower_values["Rmax_LTAR"],
            "Rmax_LTIR": lower_values["Rmax_LTIR"],
            "PhyllFrmTassel": lower_values["PhyllFrmTassel"],
        },
    )
    add_case(
        cases,
        base_values,
        f"{prefix}_high_staygreen_low_lm",
        group,
        note,
        {
            "StayGreen": upper_values["StayGreen"],
            "LM_min": lower_values["LM_min"],
        },
    )
    add_case(
        cases,
        base_values,
        f"{prefix}_low_staygreen_high_lm",
        group,
        note,
        {
            "StayGreen": lower_values["StayGreen"],
            "LM_min": upper_values["LM_min"],
        },
    )


def add_crop_rate_grid(cases, base_values, bounds):
    """添加物候速率与吐丝阈值交互探针."""
    juvenile_values = [bounds["JuvenileLeaves"]["lower"], base_values["JuvenileLeaves"], bounds["JuvenileLeaves"]["upper"]]
    initiation_values = [bounds["Rmax_LTIR"]["lower"], base_values["Rmax_LTIR"], bounds["Rmax_LTIR"]["upper"]]
    phyll_values = [bounds["PhyllFrmTassel"]["lower"], base_values["PhyllFrmTassel"], bounds["PhyllFrmTassel"]["upper"]]
    for juvenile in juvenile_values:
        for initiation in initiation_values:
            for phyll in phyll_values:
                add_case(
                    cases,
                    base_values,
                    f"crop_rate_j{juvenile:g}_lir{initiation:g}_phy{phyll:g}",
                    "crop_rate_grid",
                    "固定土壤和根系扩散基线, 检查发育速率与吐丝阈值组合.",
                    {
                        "JuvenileLeaves": juvenile,
                        "Rmax_LTIR": initiation,
                        "PhyllFrmTassel": phyll,
                    },
                )


def add_crop_canopy_grid(cases, base_values, bounds):
    """添加叶片出现速率与冠层持续性交互探针."""
    appearance_values = [bounds["Rmax_LTAR"]["lower"], base_values["Rmax_LTAR"], bounds["Rmax_LTAR"]["upper"]]
    staygreen_values = [bounds["StayGreen"]["lower"], base_values["StayGreen"], bounds["StayGreen"]["upper"]]
    lm_values = [bounds["LM_min"]["lower"], base_values["LM_min"], bounds["LM_min"]["upper"]]
    for appearance in appearance_values:
        for staygreen in staygreen_values:
            for lm_value in lm_values:
                add_case(
                    cases,
                    base_values,
                    f"crop_canopy_ltar{appearance:g}_sg{staygreen:g}_lm{lm_value:g}",
                    "crop_canopy_grid",
                    "固定土壤和根系扩散基线, 检查叶片速率, StayGreen 和 LM_min 组合.",
                    {
                        "Rmax_LTAR": appearance,
                        "StayGreen": staygreen,
                        "LM_min": lm_value,
                    },
                )


def add_inherited_crop_failure_cases(cases, base_values):
    """重放宽边界失败链条中的作物组合, 但固定土壤为当前基线."""
    inherited_cases = [
        (
            "crop_inherited_sample024_background",
            {
                "JuvenileLeaves": 16,
                "Rmax_LTAR": 0.526667,
                "Rmax_LTIR": 0.933333,
                "PhyllFrmTassel": 5.0,
                "StayGreen": 8.0,
                "LM_min": 130.0,
            },
        ),
        (
            "crop_inherited_sample025_phyll",
            {
                "JuvenileLeaves": 16,
                "Rmax_LTAR": 0.526667,
                "Rmax_LTIR": 0.933333,
                "PhyllFrmTassel": 2.666667,
                "StayGreen": 8.0,
                "LM_min": 130.0,
            },
        ),
        (
            "crop_inherited_sample026_lm",
            {
                "JuvenileLeaves": 16,
                "Rmax_LTAR": 0.526667,
                "Rmax_LTIR": 0.933333,
                "PhyllFrmTassel": 2.666667,
                "StayGreen": 8.0,
                "LM_min": 103.333333,
            },
        ),
        (
            "crop_inherited_sample027_juvenile",
            {
                "JuvenileLeaves": 19,
                "Rmax_LTAR": 0.526667,
                "Rmax_LTIR": 0.933333,
                "PhyllFrmTassel": 2.666667,
                "StayGreen": 8.0,
                "LM_min": 103.333333,
            },
        ),
    ]
    for case_name, overrides in inherited_cases:
        add_case(
            cases,
            base_values,
            case_name,
            "crop_inherited_failure_replay",
            "固定当前土壤基线, 重放宽边界失败链条里的作物参数组合.",
            overrides,
        )


def add_crop_soil_case(cases, base_values, case_name, group, hypothesis, crop_values, root_values, soil_values):
    """添加作物, 根系和土壤背景配对诊断组合."""
    overrides = {}
    overrides.update(crop_values)
    overrides.update(root_values)
    overrides.update(soil_values)
    add_case(cases, base_values, case_name, group, hypothesis, overrides)


def add_crop_soil_interaction_cases(cases, base_values, local_bounds, wide_bounds):
    """添加作物组合与已知土壤风险背景的配对诊断矩阵."""
    crop_current = {
        "JuvenileLeaves": base_values["JuvenileLeaves"],
        "Rmax_LTAR": base_values["Rmax_LTAR"],
        "Rmax_LTIR": base_values["Rmax_LTIR"],
        "PhyllFrmTassel": base_values["PhyllFrmTassel"],
        "StayGreen": base_values["StayGreen"],
        "LM_min": base_values["LM_min"],
    }
    crop_local_lower = values_from_bounds(local_bounds, "lower")
    crop_local_upper = values_from_bounds(local_bounds, "upper")
    crop_wide_lower = values_from_bounds(wide_bounds, "lower")
    crop_wide_upper = values_from_bounds(wide_bounds, "upper")

    root_current = {"Diffx": base_values["Diffx"], "Diffz": base_values["Diffz"]}
    root_low = {"Diffx": 2.4, "Diffz": 0.5}
    root_high = {"Diffx": 25.0, "Diffz": 3.0}
    root_morris_slow = {"Diffx": 2.4, "Diffz": 1.333333}

    soil_current = {
        "thetaR": base_values["thetaR"],
        "thetaS": base_values["thetaS"],
        "Alfa": base_values["Alfa"],
        "n": base_values["n"],
        "Ks": base_values["Ks"],
    }
    soil_local_lower = {"thetaR": 0.070, "thetaS": 0.387, "Alfa": 0.032, "n": 1.40, "Ks": 22.5}
    soil_local_upper = {"thetaR": 0.086, "thetaS": 0.473, "Alfa": 0.040, "n": 1.72, "Ks": 27.5}
    soil_wide_lower = {"thetaR": 0.066667, "thetaS": 0.35, "Alfa": 0.015, "n": 1.20, "Ks": 5.0}
    soil_wide_upper = {"thetaR": 0.120, "thetaS": 0.50, "Alfa": 0.055, "n": 1.866667, "Ks": 60.0}
    soil_alpha_n_risk = {"thetaR": 0.066667, "thetaS": 0.40, "Alfa": 0.040, "n": 1.20, "Ks": 23.333333}
    soil_low_ks_risk = {"thetaR": 0.066667, "thetaS": 0.45, "Alfa": 0.055, "n": 1.866667, "Ks": 5.0}

    cases_to_add = [
        ("crop_pair_C0_R0_S0", crop_current, root_current, soil_current, "基线配对参照."),
        ("crop_pair_C0_R0_SL", crop_current, root_current, soil_local_lower, "当前局部土壤低边界配对."),
        ("crop_pair_C0_R0_SH", crop_current, root_current, soil_local_upper, "当前局部土壤高边界配对."),
        ("crop_pair_C0_R0_SWL", crop_current, root_current, soil_wide_lower, "早期宽土壤低角点配对."),
        ("crop_pair_C0_R0_SWH", crop_current, root_current, soil_wide_upper, "早期宽土壤高角点配对."),
        ("crop_pair_C0_R0_SAN", crop_current, root_current, soil_alpha_n_risk, "Alfa/n 慢运行土壤背景配对."),
        ("crop_pair_C0_RM_SAN", crop_current, root_morris_slow, soil_alpha_n_risk, "Alfa/n 慢运行土壤背景叠加历史根系背景."),
        ("crop_pair_C0_R0_SLK", crop_current, root_current, soil_low_ks_risk, "低 Ks 高 Alfa 高 n 土壤背景配对."),
        ("crop_pair_C0_RL_SLK", crop_current, root_low, soil_low_ks_risk, "低 Ks 高 Alfa 高 n 土壤背景叠加低根系扩散."),
        ("crop_pair_CL_R0_S0", crop_local_lower, root_current, soil_current, "当前局部作物低角点独立风险."),
        ("crop_pair_CH_R0_S0", crop_local_upper, root_current, soil_current, "当前局部作物高角点独立风险."),
        ("crop_pair_EWL_R0_S0", crop_wide_lower, root_current, soil_current, "早期宽作物低角点独立风险."),
        ("crop_pair_EWH_R0_S0", crop_wide_upper, root_current, soil_current, "早期宽作物高角点独立风险."),
        ("crop_pair_C0_RL_S0", crop_current, root_low, soil_current, "低根系扩散独立风险."),
        ("crop_pair_C0_RH_S0", crop_current, root_high, soil_current, "高根系扩散独立风险."),
        ("crop_pair_CL_RL_S0", crop_local_lower, root_low, soil_current, "当前局部低作物叠加低根系扩散."),
        ("crop_pair_CH_RH_S0", crop_local_upper, root_high, soil_current, "当前局部高作物叠加高根系扩散."),
        ("crop_pair_EWL_RL_S0", crop_wide_lower, root_low, soil_current, "早期宽低作物叠加低根系扩散."),
        ("crop_pair_EWH_RH_S0", crop_wide_upper, root_high, soil_current, "早期宽高作物叠加高根系扩散."),
        ("crop_pair_CL_RL_SAN", crop_local_lower, root_low, soil_alpha_n_risk, "低作物和低根系是否放大 Alfa/n 风险."),
        ("crop_pair_CH_RH_SAN", crop_local_upper, root_high, soil_alpha_n_risk, "高作物和高根系是否放大 Alfa/n 风险."),
        ("crop_pair_EWL_RM_SAN", crop_wide_lower, root_morris_slow, soil_alpha_n_risk, "宽低作物叠加历史慢运行根系和 Alfa/n 风险."),
        ("crop_pair_EWH_RM_SAN", crop_wide_upper, root_morris_slow, soil_alpha_n_risk, "宽高作物叠加历史慢运行根系和 Alfa/n 风险."),
        ("crop_pair_CL_RL_SLK", crop_local_lower, root_low, soil_low_ks_risk, "低作物和低根系是否放大低 Ks 风险."),
        ("crop_pair_CH_RH_SLK", crop_local_upper, root_high, soil_low_ks_risk, "高作物和高根系是否放大低 Ks 风险."),
        ("crop_pair_EWH_RL_SLK", crop_wide_upper, root_low, soil_low_ks_risk, "宽高作物叠加低根系和低 Ks 极端风险."),
    ]
    for case_name, crop_values, root_values, soil_values, hypothesis in cases_to_add:
        add_crop_soil_case(
            cases,
            base_values,
            case_name,
            "crop_soil_pair",
            hypothesis,
            crop_values,
            root_values,
            soil_values,
        )


def build_crop_cases(parameters):
    """构建作物参数独立探针和土壤背景配对诊断矩阵."""
    base_values = current_values(parameters)
    names = crop_parameter_names(parameters)
    lookup = parameter_lookup(parameters)
    local_bounds = bounds_for_names(lookup, names, "lower", "upper")
    wide_bounds = historical_crop_bounds()
    cases = []
    add_case(cases, base_values, "C00_crop_baseline_current", "crop_control", "固定土壤和根系扩散基线, 确认当前作物基线.", {})
    add_single_crop_cases(
        cases,
        base_values,
        local_bounds,
        "crop_local_single",
        "crop_local_single",
        "固定土壤和根系扩散基线, 检查当前局部边界的单作物参数端点.",
    )
    add_single_crop_cases(
        cases,
        base_values,
        wide_bounds,
        "crop_wide_single",
        "crop_wide_single",
        "固定土壤和根系扩散基线, 检查早期宽边界作物参数端点.",
    )
    add_crop_corner_cases(
        cases,
        base_values,
        local_bounds,
        "crop_local_corner",
        "crop_local_corner",
        "固定土壤和根系扩散基线, 检查当前局部边界作物组合角点.",
    )
    add_crop_corner_cases(
        cases,
        base_values,
        wide_bounds,
        "crop_wide_corner",
        "crop_wide_corner",
        "固定土壤和根系扩散基线, 检查早期宽边界作物组合角点.",
    )
    add_crop_rate_grid(cases, base_values, wide_bounds)
    add_crop_canopy_grid(cases, base_values, wide_bounds)
    add_inherited_crop_failure_cases(cases, base_values)
    add_crop_soil_interaction_cases(cases, base_values, local_bounds, wide_bounds)
    frame = pd.DataFrame(cases)
    frame.insert(0, "case_id", range(1, len(frame) + 1))
    return frame


def build_probe_jobs(config, analysis_dir, cases):
    """准备诊断样本目录和并行任务."""
    sample_root = analysis_dir / "samples"
    sample_root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for _, row in cases.iterrows():
        case_id = int(row["case_id"])
        sample_dir = sample_root / f"case_{case_id:06d}"
        values = {}
        for parameter in config["parameters"]:
            values[parameter["name"]] = row[parameter["name"]]
        prepare_sample_dir(config["baseline_run_dir"], sample_dir)
        write_parameters(sample_dir, values)
        jobs.append(
            {
                "sample_id": case_id,
                "trajectory_id": 0,
                "step_id": case_id,
                "changed_parameter": row["probe_group"],
                "sample_dir": sample_dir,
                "timeout_seconds": config["timeout_seconds"],
            }
        )
    return jobs


def status_detail(row, slow_seconds):
    """根据 manifest 行生成稳定性分类."""
    if row["status"] != "success":
        error = str(row.get("error", ""))
        if "ORTHOMIN" in error:
            return "failed_orthomin"
        if "超时" in error:
            return "failed_timeout"
        return "failed_other"
    elapsed = float(row["elapsed_seconds"])
    if elapsed >= slow_seconds:
        return "success_slow"
    return "success_fast"


def build_summary(cases, manifest_rows, output_rows, slow_seconds):
    """合并参数, 运行状态和输出指标."""
    manifest = pd.DataFrame(manifest_rows)
    outputs = pd.DataFrame(output_rows)
    summary = cases.merge(manifest, left_on="case_id", right_on="sample_id", how="left")
    if not outputs.empty:
        summary = summary.merge(outputs, left_on="case_id", right_on="sample_id", how="left", suffixes=("", "_output"))
    summary["status_detail"] = summary.apply(lambda row: status_detail(row, slow_seconds), axis=1)
    return summary


def write_csv(path, rows):
    """写入 CSV 文件."""
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def main(arguments=None):
    """执行靶向失败边界探索."""
    args = parse_args(arguments)
    try:
        if args.max_workers <= 0:
            raise SensitivityConfigError("--max-workers 必须是正整数.")
        if args.timeout_seconds <= 0:
            raise SensitivityConfigError("--timeout-seconds 必须是正整数.")

        config = read_config(Path(args.bounds))
        config["timeout_seconds"] = args.timeout_seconds
        analysis_id = analysis_id_for_args(args)
        analysis_dir = output_root_for_args(config, args) / analysis_id
        if args.case_set == "p0p1":
            cases = build_p0p1_cases(config["parameters"])
        elif args.case_set == "crop":
            cases = build_crop_cases(config["parameters"])
        else:
            cases = build_probe_cases(config["parameters"])
        if args.limit is not None:
            if args.limit <= 0:
                raise SensitivityConfigError("--limit 必须是正整数.")
            cases = cases.head(args.limit).copy()

        print(f"参数边界文件: {config['bounds_path']}")
        print(f"基线运行目录: {config['baseline_run_dir']}")
        print(f"诊断输出目录: {analysis_dir}")
        print(f"诊断组合数: {len(cases)}")
        print(f"并行 worker 数: {args.max_workers}")
        print(f"样本超时: {args.timeout_seconds} 秒, 慢运行阈值: {args.slow_seconds} 秒")

        if args.dry_run:
            print(f"dry-run 完成, 未创建诊断目录, 未复制样本目录, 未运行模型.")
            return 0

        ensure_new_analysis_dir(analysis_dir)
        cases.to_csv(analysis_dir / "probe_cases.csv", index=False, encoding="utf-8-sig")
        jobs = build_probe_jobs(config, analysis_dir, cases)
        manifest_rows, output_rows, failure_rows = run_samples(jobs, args.max_workers)
        write_csv(analysis_dir / "manifest.csv", manifest_rows)
        write_csv(analysis_dir / "outputs.csv", output_rows)
        write_csv(analysis_dir / "failures.csv", failure_rows)
        summary = build_summary(cases, manifest_rows, output_rows, args.slow_seconds)
        summary.to_csv(analysis_dir / "stability_summary.csv", index=False, encoding="utf-8-sig")

        counts = summary["status_detail"].value_counts().to_dict()
        print(f"诊断完成. status_detail={counts}")
        return 0
    except SensitivityConfigError as exc:
        sys.stderr.write(f"错误: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"未处理错误: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
