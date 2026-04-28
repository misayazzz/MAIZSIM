"""使用 matplotlib 绘制 MAIZSIM 二维土壤水节点分布图."""

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CASE_DIR = ROOT_DIR.parent / "Wye07"
DEFAULT_OUTPUT_FILE = ROOT_DIR / "wye07_soil_water_nodes_profile.png"
DEFAULT_CASE_NAME = "Wye07"

FONT_DIR = Path("C:/Windows/Fonts")
SIMSUN_CANDIDATES = [FONT_DIR / "simsun.ttc", FONT_DIR / "simsun.ttf"]
TIMES_CANDIDATES = [FONT_DIR / "times.ttf", FONT_DIR / "timesbd.ttf"]


def format_number(value):
    """格式化图中文字数值, 输入为数值, 输出为紧凑字符串."""
    if value is None:
        return "NA"
    rounded = round(value)
    if math.isclose(value, rounded, rel_tol=0, abs_tol=1e-8):
        return f"{rounded:.0f}"
    return f"{value:g}"


def parse_arguments():
    """解析命令行参数, 输出算例路径和输出路径配置."""
    parser = argparse.ArgumentParser(description="Plot a MAIZSIM 2D soil grid profile.")
    parser.add_argument("--case-dir", default=str(DEFAULT_CASE_DIR), help="Directory containing .grd, .nod, .lyr, and .soi files.")
    parser.add_argument("--grid-file", default=None, help="Optional explicit .grd file path.")
    parser.add_argument("--node-file", default=None, help="Optional explicit .nod file path.")
    parser.add_argument("--layer-file", default=None, help="Optional explicit .lyr file path.")
    parser.add_argument("--soil-file", default=None, help="Optional explicit .soi file path.")
    parser.add_argument("--case-name", default=None, help="Optional case name used in console output.")
    parser.add_argument("--output", default=None, help="Optional output PNG path.")
    return parser.parse_args()


def resolve_path(value, base_dir):
    """解析路径参数, 输入为路径文本和基准目录, 输出为绝对 Path."""
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def find_unique_file(case_dir, suffix):
    """在算例目录中查找唯一指定后缀文件, 找不到或多个时抛出异常."""
    matches = sorted(case_dir.glob(f"*{suffix}"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"Missing {suffix} file in case directory: {case_dir}")
    names = ", ".join(match.name for match in matches)
    raise RuntimeError(f"Multiple {suffix} files found in {case_dir}: {names}")


def resolve_case_inputs(args):
    """根据命令行参数定位算例输入文件, 输出绘图配置字典."""
    case_dir = resolve_path(args.case_dir, ROOT_DIR)
    case_name = args.case_name or case_dir.name or DEFAULT_CASE_NAME
    output_file = resolve_path(args.output, ROOT_DIR) if args.output else ROOT_DIR / f"{case_name.lower()}_soil_water_nodes_profile.png"
    if case_dir == DEFAULT_CASE_DIR and args.output is None:
        output_file = DEFAULT_OUTPUT_FILE

    input_files = {
        "grid": resolve_path(args.grid_file, ROOT_DIR) if args.grid_file else find_unique_file(case_dir, ".grd"),
        "node": resolve_path(args.node_file, ROOT_DIR) if args.node_file else find_unique_file(case_dir, ".nod"),
        "layer": resolve_path(args.layer_file, ROOT_DIR) if args.layer_file else find_unique_file(case_dir, ".lyr"),
        "soil": resolve_path(args.soil_file, ROOT_DIR) if args.soil_file else find_unique_file(case_dir, ".soi"),
    }
    return {
        "case_dir": case_dir,
        "case_name": case_name,
        "output_file": output_file,
        "input_files": input_files,
    }


def find_font(candidates, label):
    """检查指定字体是否存在, 返回 FontProperties."""
    for candidate in candidates:
        if candidate.is_file():
            return FontProperties(fname=str(candidate))
    names = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(f"{label} font missing: {names}")


def read_lines(path):
    """读取文本文件, 输入为路径, 输出为逐行文本列表."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def parse_grid_file(path):
    """读取网格文件, 输出网格信息, 节点, 单元和边界."""
    lines = read_lines(path)
    header_index = next(index for index, line in enumerate(lines) if "KAT" in line and "NumNP" in line)
    header_values = lines[header_index + 1].split()
    grid_info = {
        "kat": int(header_values[0]),
        "node_count": int(header_values[1]),
        "element_count": int(header_values[2]),
        "boundary_count": int(header_values[3]),
        "ij": int(header_values[4]),
        "material_count": int(header_values[5]),
    }

    node_header = next(index for index, line in enumerate(lines) if "MatNum" in line and "x" in line)
    nodes = []
    for line in lines[node_header + 1: node_header + 1 + grid_info["node_count"]]:
        parts = line.split()
        nodes.append(
            {
                "node": int(parts[0]),
                "x": float(parts[1]),
                "y": float(parts[2]),
                "material": int(parts[3]),
            }
        )

    element_header = next(index for index, line in enumerate(lines) if "MatNumE" in line)
    elements = []
    for line in lines[element_header + 1: element_header + 1 + grid_info["element_count"]]:
        parts = line.split()
        elements.append(
            {
                "element": int(parts[0]),
                "nodes": [int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])],
                "material": int(parts[5]),
            }
        )

    boundary_header = next(index for index, line in enumerate(lines) if "CodeW" in line and "Width" in line)
    boundaries = []
    for line in lines[boundary_header + 1:]:
        if "Seepage face information" in line:
            break
        parts = line.split()
        if len(parts) >= 6:
            boundaries.append(
                {
                    "node": int(parts[0]),
                    "code_w": int(parts[1]),
                    "code_c": int(parts[2]),
                    "code_h": int(parts[3]),
                    "code_g": int(parts[4]),
                    "width": float(parts[5]),
                }
            )
    return grid_info, nodes, elements, boundaries


def parse_node_file(path):
    """读取节点文件, 输出每个节点的初始状态."""
    lines = read_lines(path)
    header_index = next(index for index, line in enumerate(lines) if "Node" in line and "HumusN" in line)
    field_names = [
        "node",
        "humus_n",
        "humus_c",
        "litter_n",
        "litter_c",
        "manure_n",
        "manure_c",
        "nh4",
        "no3",
        "tmpr",
        "h_new",
        "co2",
        "o2",
        "n2o",
        "rtwt",
    ]
    states = {}
    for line in lines[header_index + 1:]:
        parts = line.split()
        if len(parts) < len(field_names):
            continue
        values = {}
        for index, name in enumerate(field_names):
            if name == "node":
                values[name] = int(parts[index])
            else:
                values[name] = float(parts[index])
        states[values["node"]] = values
    return states


def parse_soil_file(path):
    """读取土壤文件, 输出每个材料层的水力参数."""
    lines = read_lines(path)
    materials = {}
    material_id = 1
    for line in lines:
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            numbers = [float(value) for value in parts[:13]]
        except ValueError:
            continue
        materials[material_id] = {
            "thr": numbers[0],
            "ths": numbers[1],
            "tha": numbers[2],
            "thm": numbers[3],
            "alpha": numbers[4],
            "n": numbers[5],
            "ks": numbers[6],
            "kk": numbers[7],
            "thk": numbers[8],
            "bulk_density": numbers[9],
            "organic_matter": numbers[10],
            "sand": numbers[11],
            "silt": numbers[12],
        }
        material_id += 1
    return materials


def parse_layer_file(path):
    """读取土层文件, 输出行距, 播深, 根系横向范围和土层底界."""
    lines = read_lines(path)
    row_spacing = None
    planting_depth = None
    root_x_limit = None
    layer_bottoms = []

    for index, line in enumerate(lines):
        if "Row Spacing" in line:
            row_spacing = float(lines[index + 1].split()[0])
        if "Planting Depth" in line:
            values = lines[index + 1].split()
            planting_depth = float(values[0])
            root_x_limit = float(values[1])

    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            bottom_depth = float(parts[0])
        except ValueError:
            continue
        if bottom_depth > 0 and parts[1].strip("'").lower() == "m":
            layer_bottoms.append(bottom_depth)

    return {
        "row_spacing": row_spacing,
        "planting_depth": planting_depth,
        "root_x_limit": root_x_limit,
        "layer_bottoms": layer_bottoms,
    }


def water_content_from_head(head, material):
    """根据 van Genuchten 方程由压力水头估算体积含水量."""
    if head >= 0:
        return material["ths"]
    n_value = material["n"]
    m_value = 1.0 - 1.0 / n_value
    saturation = (1.0 + (material["alpha"] * abs(head)) ** n_value) ** (-m_value)
    return material["thr"] + (material["ths"] - material["thr"]) * saturation


def load_case_data(input_files, case_name):
    """读取算例输入文件, 输出绘图所需的数据."""
    grid_info, nodes, elements, boundaries = parse_grid_file(input_files["grid"])
    node_states = parse_node_file(input_files["node"])
    materials = parse_soil_file(input_files["soil"])
    layer_info = parse_layer_file(input_files["layer"])

    max_y = max(node["y"] for node in nodes)
    for node in nodes:
        state = node_states[node["node"]]
        node["depth"] = max_y - node["y"]
        node["h_new"] = state["h_new"]
        node["theta"] = water_content_from_head(state["h_new"], materials[node["material"]])
    return {
        "case_name": case_name,
        "grid_info": grid_info,
        "nodes": nodes,
        "elements": elements,
        "boundaries": boundaries,
        "materials": materials,
        "layer_info": layer_info,
    }


def apply_axis_style(axis, font_properties):
    """统一坐标轴样式, 使用朝内主刻度并隐藏次刻度."""
    axis.minorticks_off()
    axis.tick_params(direction="in", length=3.2, width=0.75, labelsize=7)
    for label in axis.get_xticklabels():
        label.set_fontproperties(font_properties)
        label.set_fontsize(7)
    for label in axis.get_yticklabels():
        label.set_fontproperties(font_properties)
        label.set_fontsize(7)
    for spine in axis.spines.values():
        spine.set_linewidth(0.8)


def add_panel_label(axis, label, font_properties):
    """在子图左上角添加期刊常用分面板字母."""
    axis.text(
        -0.11,
        1.03,
        label,
        transform=axis.transAxes,
        fontproperties=font_properties,
        fontsize=8,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def is_close(value, target):
    """判断两个坐标值是否近似相等, 输入为两个数值, 输出为布尔值."""
    return math.isclose(value, target, rel_tol=0, abs_tol=1e-7)


def nice_step(value):
    """根据目标间距生成易读刻度步长, 输入为原始步长, 输出为美化步长."""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / 10**exponent
    if fraction <= 1:
        nice_fraction = 1
    elif fraction <= 2:
        nice_fraction = 2
    elif fraction <= 5:
        nice_fraction = 5
    else:
        nice_fraction = 10
    return nice_fraction * 10**exponent


def build_horizontal_ticks(min_x, max_x):
    """根据横向范围生成坐标刻度, 输入为范围, 输出为刻度列表."""
    span = max_x - min_x
    if span <= 0:
        return [min_x]
    step = nice_step(span / 4)
    start = math.ceil(min_x / step) * step
    ticks = []
    value = start
    while value <= max_x + 1e-8:
        if value >= min_x - 1e-8:
            ticks.append(round(value, 8))
        value += step
    if not any(is_close(tick, min_x) for tick in ticks):
        ticks.insert(0, min_x)
    if not any(is_close(tick, max_x) for tick in ticks):
        ticks.append(max_x)
    return ticks


def build_depth_ticks(layer_bottoms, max_depth):
    """根据土层底界和最大深度生成深度刻度."""
    ticks = [0.0]
    for bottom_depth in layer_bottoms[:-1]:
        if 0 < bottom_depth < max_depth and not any(is_close(tick, bottom_depth) for tick in ticks):
            ticks.append(bottom_depth)
    step = nice_step(max_depth / 3)
    value = step
    while value < max_depth:
        if not any(abs(tick - value) < step * 0.35 for tick in ticks):
            ticks.append(value)
        value += step
    if not any(is_close(tick, max_depth) for tick in ticks):
        ticks.append(max_depth)
    return sorted(ticks)


def build_layer_colors(data):
    """根据材料编号和土层数生成颜色映射."""
    nodes = data["nodes"]
    layer_count = len(data["layer_info"]["layer_bottoms"])
    max_material_id = max(node["material"] for node in nodes)
    color_count = max(max_material_id, layer_count)
    palette_name = "Set2" if color_count <= 8 else "husl"
    palette = sns.color_palette(palette_name, n_colors=color_count)
    return {material_id: palette[material_id - 1] for material_id in range(1, color_count + 1)}


def draw_soil_layers(axis, layer_info, layer_colors, times_font):
    """绘制土层背景和材料标签."""
    layer_tops = [0] + layer_info["layer_bottoms"][:-1]
    layer_bottoms = layer_info["layer_bottoms"]
    label_transform = blended_transform_factory(axis.transAxes, axis.transData)
    for material_id, top_depth in enumerate(layer_tops, start=1):
        bottom_depth = layer_bottoms[material_id - 1]
        axis.axhspan(top_depth, bottom_depth, color=layer_colors[material_id], alpha=0.20, linewidth=0)
        axis.axhline(top_depth, color="#4b5563", linewidth=0.55, alpha=0.55)
        y_mid = (top_depth + bottom_depth) / 2
        axis.text(
            1.006,
            y_mid,
            f"M{material_id}\n{top_depth:.0f}-{bottom_depth:.0f}",
            transform=label_transform,
            fontproperties=times_font,
            fontsize=6.3,
            ha="left",
            va="center",
            linespacing=1.1,
            clip_on=False,
        )


def draw_main_panel(axis, data, water_cmap, layer_colors, times_font):
    """绘制主面板, 包括土壤剖面节点, 水分颜色和边界."""
    nodes = data["nodes"]
    boundaries = data["boundaries"]
    layer_info = data["layer_info"]
    min_x = min(node["x"] for node in nodes)
    max_x = max(node["x"] for node in nodes)
    min_depth = min(node["depth"] for node in nodes)
    max_depth = max(node["depth"] for node in nodes)
    x_margin = max((max_x - min_x) * 0.03, 1.0)
    y_margin = max((max_depth - min_depth) * 0.02, 3.0)
    x_ticks = build_horizontal_ticks(min_x, max_x)
    y_ticks = build_depth_ticks(layer_info["layer_bottoms"], max_depth)
    boundary_size = 34
    boundary_width = 0.8
    sowing_size = 32
    sowing_width = 0.5
    root_size = 42
    root_marker_width = 0.4
    root_line_width = 0.75
    root_line_style = (0, (3, 2))

    draw_soil_layers(axis, layer_info, layer_colors, times_font)

    x_values = np.array([node["x"] for node in nodes])
    depth_values = np.array([node["depth"] for node in nodes])
    theta_values = np.array([node["theta"] for node in nodes])
    scatter = axis.scatter(
        x_values,
        depth_values,
        c=theta_values,
        cmap=water_cmap,
        s=17,
        edgecolors="white",
        linewidths=0.35,
        zorder=4,
    )

    boundary_by_node = {boundary["node"]: boundary for boundary in boundaries}
    surface_nodes = [
        node for node in nodes
        if node["node"] in boundary_by_node and is_close(node["depth"], min_depth)
    ]
    bottom_nodes = [
        node for node in nodes
        if node["node"] in boundary_by_node and is_close(node["depth"], max_depth)
    ]
    axis.scatter(
        [node["x"] for node in surface_nodes],
        [node["depth"] for node in surface_nodes],
        facecolors="none",
        edgecolors="#b91c1c",
        s=boundary_size,
        linewidths=boundary_width,
        zorder=5,
    )
    axis.scatter(
        [node["x"] for node in bottom_nodes],
        [node["depth"] for node in bottom_nodes],
        facecolors="none",
        edgecolors="#1d4ed8",
        s=boundary_size,
        linewidths=boundary_width,
        zorder=5,
    )

    planting_depth = layer_info["planting_depth"]
    root_x_limit = layer_info["root_x_limit"]
    if planting_depth is not None:
        axis.scatter(
            [min_x],
            [planting_depth],
            s=sowing_size,
            color="#7c2d12",
            edgecolors="#431407",
            linewidths=sowing_width,
            zorder=6,
        )
    if root_x_limit is not None:
        axis.plot(
            [root_x_limit, root_x_limit],
            [min_depth, max_depth],
            color="#166534",
            linestyle=root_line_style,
            linewidth=root_line_width,
            zorder=3.5,
        )
        axis.scatter(
            [root_x_limit],
            [min_depth],
            marker="v",
            s=root_size,
            color="#166534",
            edgecolors="white",
            linewidths=root_marker_width,
            zorder=6,
        )

    axis.set_xlim(min_x - x_margin, max_x + x_margin)
    axis.set_ylim(max_depth + y_margin, min_depth - y_margin)
    axis.set_xlabel("Horizontal distance/cm", fontproperties=times_font, fontsize=8)
    axis.set_ylabel("Depth/cm", fontproperties=times_font, fontsize=8)
    axis.set_xticks(x_ticks)
    axis.set_xticklabels([format_number(tick) for tick in x_ticks])
    axis.set_yticks(y_ticks)
    axis.set_yticklabels([format_number(tick) for tick in y_ticks])
    axis.set_title("2D soil grid and initial water content", fontproperties=times_font, fontsize=8, pad=4)
    apply_axis_style(axis, times_font)
    add_panel_label(axis, "(a)", times_font)

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="none",
            markeredgecolor="#b91c1c",
            markeredgewidth=boundary_width,
            markersize=math.sqrt(boundary_size),
            label="Surface boundary",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="none",
            markeredgecolor="#1d4ed8",
            markeredgewidth=boundary_width,
            markersize=math.sqrt(boundary_size),
            label="Bottom seepage face",
        ),
    ]
    if planting_depth is not None:
        legend_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#7c2d12",
                markeredgecolor="#431407",
                markeredgewidth=sowing_width,
                markersize=math.sqrt(sowing_size),
                label=f"Sowing at {format_number(planting_depth)} cm",
            )
        )
    if root_x_limit is not None:
        legend_handles.append(
            Line2D(
                [0],
                [0],
                marker="v",
                color="none",
                markerfacecolor="#166534",
                markeredgecolor="white",
                markeredgewidth=root_marker_width,
                markersize=math.sqrt(root_size),
                label=f"Root uptake limit at {format_number(root_x_limit)} cm",
            )
        )
    return scatter, legend_handles


def draw_horizontal_panel(axis, data, times_font):
    """绘制横向节点位置分布."""
    nodes = data["nodes"]
    layer_info = data["layer_info"]
    x_values = sorted({node["x"] for node in nodes})
    min_x = min(x_values)
    max_x = max(x_values)
    x_ticks = build_horizontal_ticks(min_x, max_x)
    half_row_spacing = layer_info["row_spacing"] / 2 if layer_info["row_spacing"] is not None else None
    left_label = "Plant row" if is_close(min_x, 0) else "Left boundary"
    right_label = "Inter-row midpoint" if half_row_spacing is not None and is_close(max_x, half_row_spacing) else "Right boundary"
    axis.axhline(0, color="#111827", linewidth=0.75)
    for x_value in x_values:
        axis.plot([x_value, x_value], [0, 0.22], color="#9ca3af", linewidth=0.45)
        axis.scatter([x_value], [0], s=24, color="#315f9d", edgecolors="white", linewidths=0.35, zorder=3)
    axis.text(min_x, 0.29, left_label, fontproperties=times_font, fontsize=6.5, ha="left")
    axis.text(max_x, 0.29, right_label, fontproperties=times_font, fontsize=6.5, ha="right")
    axis.set_xlim(min_x - 1.0, max_x + 1.0)
    axis.set_ylim(-0.13, 0.40)
    axis.set_xlabel("Horizontal distance/cm", fontproperties=times_font, fontsize=7.5, labelpad=1)
    axis.set_yticks([])
    axis.set_xticks(x_ticks)
    axis.set_xticklabels([format_number(tick) for tick in x_ticks])
    axis.set_title(f"Horizontal node positions (n={len(x_values)})", fontproperties=times_font, fontsize=7.8, pad=4)
    axis.spines["left"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["top"].set_visible(False)
    axis.spines["bottom"].set_position(("data", -0.045))
    apply_axis_style(axis, times_font)
    axis.tick_params(axis="x", pad=1)
    add_panel_label(axis, "(b)", times_font)


def draw_vertical_panel(axis, data, layer_colors, times_font):
    """绘制土层划分和纵向节点层数标注."""
    nodes = data["nodes"]
    layer_info = data["layer_info"]
    layer_tops = [0] + layer_info["layer_bottoms"][:-1]
    layer_bottoms = layer_info["layer_bottoms"]
    max_layer_depth = max(layer_bottoms)
    y_ticks = build_depth_ticks(layer_bottoms, max_layer_depth)
    vertical_node_counts = {
        material_id: len({node["depth"] for node in nodes if node["material"] == material_id})
        for material_id in range(1, len(layer_bottoms) + 1)
    }
    block_left = 0.18
    block_width = 0.42
    label_x = block_left + block_width + 0.10
    title_transform = blended_transform_factory(axis.transData, axis.transAxes)

    for material_id, top_depth in enumerate(layer_tops, start=1):
        bottom_depth = layer_bottoms[material_id - 1]
        axis.add_patch(
            Rectangle(
                (block_left, top_depth),
                block_width,
                bottom_depth - top_depth,
                facecolor=(*layer_colors[material_id], 0.62),
                edgecolor="#374151",
                linewidth=0.58,
            )
        )
        y_mid = (top_depth + bottom_depth) / 2
        axis.text(
            label_x,
            y_mid,
            f"M{material_id}: n={vertical_node_counts[material_id]}",
            fontproperties=times_font,
            fontsize=5.9,
            va="center",
            ha="left",
            clip_on=False,
        )
    axis.set_xlim(0, 1.25)
    axis.set_ylim(max_layer_depth + 3, -3)
    axis.set_xticks([])
    axis.set_yticks(y_ticks)
    axis.set_yticklabels([format_number(tick) for tick in y_ticks])
    axis.set_ylabel("Depth/cm", fontproperties=times_font, fontsize=7.5)
    axis.text(
        block_left + block_width / 2,
        1.035,
        "Soil layers",
        transform=title_transform,
        fontproperties=times_font,
        fontsize=7.8,
        ha="center",
        va="bottom",
        clip_on=False,
    )
    axis.spines["right"].set_visible(False)
    axis.spines["top"].set_visible(False)
    axis.spines["bottom"].set_visible(False)
    apply_axis_style(axis, times_font)
    add_panel_label(axis, "(c)", times_font)


def plot_figure(config):
    """生成并保存二维土壤水节点分布图, 输入为绘图配置, 输出为 PNG 路径."""
    find_font(SIMSUN_CANDIDATES, "SimSun")
    times_font = find_font(TIMES_CANDIDATES, "Times New Roman")
    data = load_case_data(config["input_files"], config["case_name"])

    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    water_cmap = sns.color_palette("crest", as_cmap=True)
    layer_colors = build_layer_colors(data)

    figure = plt.figure(figsize=(7.25, 4.8), facecolor="white")
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=[2.75, 1.0],
        height_ratios=[1.0, 1.22],
        left=0.075,
        right=0.965,
        bottom=0.18,
        top=0.90,
        wspace=0.08,
        hspace=0.52,
    )
    main_axis = figure.add_subplot(grid[:, 0])
    horizontal_axis = figure.add_subplot(grid[0, 1])
    vertical_axis = figure.add_subplot(grid[1, 1])

    scatter, legend_handles = draw_main_panel(main_axis, data, water_cmap, layer_colors, times_font)
    draw_horizontal_panel(horizontal_axis, data, times_font)
    draw_vertical_panel(vertical_axis, data, layer_colors, times_font)

    colorbar = figure.colorbar(scatter, ax=main_axis, shrink=0.52, pad=0.078, aspect=18)
    colorbar.set_label(r"$\theta$/(cm$^3\cdot$cm$^{-3}$)", fontproperties=times_font, fontsize=8)
    colorbar.ax.tick_params(direction="in", length=0, width=0, labelsize=7)
    for label in colorbar.ax.get_yticklabels():
        label.set_fontproperties(times_font)
        label.set_fontsize(7)

    figure.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.42, 0.035),
        ncol=min(len(legend_handles), 4),
        prop=times_font,
        fontsize=6.5,
        frameon=False,
        handlelength=1.0,
        columnspacing=1.2,
    )

    output_file = config["output_file"]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_file, dpi=600, bbox_inches="tight")
    plt.close(figure)
    return output_file


def main():
    """运行绘图流程并打印输出路径."""
    args = parse_arguments()
    config = resolve_case_inputs(args)
    output_file = plot_figure(config)
    print(f"Generated PNG figure: {output_file}")


if __name__ == "__main__":
    main()
