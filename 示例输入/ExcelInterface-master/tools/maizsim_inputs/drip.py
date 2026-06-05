"""Drip irrigation input validation and .drp writer."""

from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from datetime import timedelta
from pathlib import Path
import re
import warnings

from .errors import ConfigError
from .run_files import RUN_FILE_NAME
from .shared_inputs import read_text_with_encoding


DRIP_HEADER = "*****Script for Drip application module  ******* wAppl is cm water per hour; Mode4/5 use DripSourceWidth measure"
DRIP_COUNT_HEADER = "Number of Drip irrigations(max=75)  "
NO_DRIP_LINES = [
    DRIP_HEADER,
    DRIP_COUNT_HEADER,
    " 0 ",
    "No drip irrigation",
]
MAX_DRIP_EVENTS = 75
MAX_DRIP_NODES = 150
MODE4_SMALL_SOURCE_WIDTH_RATIO = 0.5
DRIP_FILE_LINE_INDEX = 11
PRESSURE_MODE_FIELDS = ("dripmode", "pressuremode")
PRESSURE_HEAD_FIELDS = ("driphin", "inlethead", "inletpressurehead")
PRESSURE_EXP_FIELDS = ("dripexp", "pressureexponent")
PRESSURE_PC_MIN_FIELDS = ("drippcmin", "pcmin", "pressurecompensationmin")
PRESSURE_PC_MAX_FIELDS = ("drippcmax", "pcmax", "pressurecompensationmax")
WET_WIDTH_MAX_FIELDS = (
    "dripwetwidthmax",
    "dripwetwidthmaxcm",
    "wetwidthmax",
    "wetwidthmaxcm",
)
SPREAD_MODE_FIELDS = (
    "dripspreadmode",
    "spreadmode",
    "wettingmode",
)
SOURCE_WIDTH_FIELDS = (
    "dripsourcewidth",
    "dripsourcewidthcm",
    "sourcewidth",
    "sourcewidthcm",
)


def is_blank(value):
    """Return True for empty Excel-style values."""
    return value is None or str(value).strip() == ""


def row_context(sheet_name, run_id, record):
    """Build a compact context label for validation errors."""
    row_number = record.get("__row_number__", "?")
    return f"{sheet_name}.ID={run_id} 第 {row_number} 行"


def get_cell(record, key, context, field_name=None):
    """Read a normalized workbook cell and fail when it is blank."""
    value = record.get(key)
    if is_blank(value):
        label = field_name or key
        raise ConfigError(f"{context} 缺少 {label}.")
    return value


def parse_float(value, context, field_name):
    """Parse a numeric Excel cell."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{context} 的 {field_name} 必须是数值: {value}") from exc
    return number


def parse_positive_float(value, context, field_name):
    """Parse a positive numeric Excel cell."""
    number = parse_float(value, context, field_name)
    if number <= 0:
        raise ConfigError(f"{context} 的 {field_name} 必须大于 0: {value}")
    return number


def get_optional_cell(record, keys):
    """Return the first non-blank optional cell from a normalized record."""
    for key in keys:
        value = record.get(key)
        if not is_blank(value):
            return value
    return None


def parse_optional_float(record, keys, context, field_name, default):
    """Parse an optional numeric Excel cell."""
    value = get_optional_cell(record, keys)
    if value is None:
        return default
    return parse_float(value, context, field_name)


def parse_optional_int(record, keys, context, field_name, default):
    """Parse an optional integer Excel cell."""
    value = get_optional_cell(record, keys)
    if value is None:
        return default
    number = parse_float(value, context, field_name)
    if not number.is_integer():
        raise ConfigError(f"{context} 的 {field_name} 必须是整数: {value}")
    return int(number)


def parse_date(value, context, field_name):
    """Parse a date cell to datetime.date."""
    if isinstance(value, DateTime):
        return value.date()
    if isinstance(value, Date):
        return value
    if isinstance(value, (int, float)):
        return Date(1899, 12, 30) + timedelta(days=int(value))

    text = str(value).strip().strip("'\"")
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return DateTime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ConfigError(f"{context} 的 {field_name} 必须是日期: {value}")


def parse_time_hour(value, context, field_name):
    """Parse an Excel time cell to hour-of-day as a float."""
    if isinstance(value, DateTime):
        value = value.time()
    if isinstance(value, Time):
        return value.hour + value.minute / 60 + value.second / 3600 + value.microsecond / 3600000000
    if isinstance(value, timedelta):
        return value.total_seconds() / 3600

    if isinstance(value, (int, float)):
        number = float(value)
        if 0 <= number < 1:
            hour = number * 24
        else:
            hour = number
    else:
        text = str(value).strip()
        if ":" in text:
            parts = text.split(":")
            if len(parts) not in (2, 3):
                raise ConfigError(f"{context} 的 {field_name} 时间格式无效: {value}")
            try:
                hour = float(parts[0]) + float(parts[1]) / 60
                if len(parts) == 3:
                    hour += float(parts[2]) / 3600
            except ValueError as exc:
                raise ConfigError(f"{context} 的 {field_name} 时间格式无效: {value}") from exc
        else:
            hour = parse_float(text, context, field_name)
            if 0 <= hour < 1:
                hour *= 24

    if hour < 0 or hour > 24:
        raise ConfigError(f"{context} 的 {field_name} 必须在 0 到 24 小时之间: {value}")
    return hour


def parse_node_token(token, context):
    """Parse one node identifier and reject non-integers."""
    try:
        number = float(token)
    except ValueError as exc:
        raise ConfigError(f"{context} 的 nodes 包含非整数节点: {token}") from exc
    if not number.is_integer():
        raise ConfigError(f"{context} 的 nodes 包含非整数节点: {token}")
    node = int(number)
    if node <= 0:
        raise ConfigError(f"{context} 的 nodes 必须是正整数节点: {token}")
    return node


def parse_nodes_value(value, context):
    """Parse a DripNodes.nodes cell to a list of integer node IDs."""
    if is_blank(value):
        raise ConfigError(f"{context} 的 nodes 不能为空.")
    if isinstance(value, (int, float)):
        return [parse_node_token(str(value), context)]

    tokens = [token for token in re.split(r"[\s,;]+", str(value).strip()) if token]
    if not tokens:
        raise ConfigError(f"{context} 的 nodes 不能为空.")
    return [parse_node_token(token, context) for token in tokens]


def collect_explicit_nodes(run_id, drip_node_records):
    """Collect explicit DripNodes.nodes values for a run."""
    nodes = []
    seen = set()
    for record in drip_node_records:
        context = row_context("DripNodes", run_id, record)
        for node in parse_nodes_value(record.get("nodes"), context):
            if node not in seen:
                seen.add(node)
                nodes.append(node)

    if len(nodes) > MAX_DRIP_NODES:
        raise ConfigError(f"DripNodes.ID={run_id} 节点数超过 {MAX_DRIP_NODES}: {len(nodes)}")
    return nodes


def normalize_drip_record(run_id, record, require_distance):
    """Validate one Drip row and return normalized values used by the writer."""
    context = row_context("Drip", run_id, record)
    event_date = parse_date(get_cell(record, "date", context, "date"), context, "date")
    start_hour = parse_time_hour(get_cell(record, "starttime", context, "StartTime"), context, "StartTime")
    stop_hour = parse_time_hour(get_cell(record, "stoptime", context, "StopTime"), context, "StopTime")
    if start_hour == stop_hour:
        raise ConfigError(f"{context} 的 StartTime 和 StopTime 不能相同.")
    stop_date = event_date + timedelta(days=1) if stop_hour < start_hour else event_date

    pressure_mode = parse_optional_int(record, PRESSURE_MODE_FIELDS, context, "DripMode", 0)
    pressure_head = parse_optional_float(record, PRESSURE_HEAD_FIELDS, context, "DripHIn", 0.0)
    pressure_exp = parse_optional_float(record, PRESSURE_EXP_FIELDS, context, "DripExp", 1.0)
    pressure_pc_min = parse_optional_float(record, PRESSURE_PC_MIN_FIELDS, context, "DripPcMin", 0.0)
    pressure_pc_max = parse_optional_float(record, PRESSURE_PC_MAX_FIELDS, context, "DripPcMax", 0.0)
    wet_width_max = parse_optional_float(record, WET_WIDTH_MAX_FIELDS, context, "DripWetWidthMax", 0.0)
    source_width = parse_optional_float(record, SOURCE_WIDTH_FIELDS, context, "DripSourceWidth", 0.0)
    spread_mode_value = get_optional_cell(record, SPREAD_MODE_FIELDS)
    if spread_mode_value is None and source_width > 0.0:
        spread_mode = 4
        warnings.warn(
            f"{context} 填写了 DripSourceWidth 但未填写 DripSpreadMode，已按 DripSpreadMode=4 写出.",
            UserWarning,
            stacklevel=2,
        )
    elif spread_mode_value is None:
        spread_mode = 0
    else:
        spread_mode = parse_optional_int(record, SPREAD_MODE_FIELDS, context, "DripSpreadMode", 0)
    if pressure_mode not in (0, 1, 2, 3):
        raise ConfigError(f"{context} 的 DripMode 必须是 0、1、2 或 3: {pressure_mode}")
    if spread_mode not in (0, 1, 2, 3, 4, 5):
        raise ConfigError(f"{context} 的 DripSpreadMode 必须是 0、1、2、3、4 或 5: {spread_mode}")
    if pressure_mode in (1, 2) and pressure_head <= 0:
        raise ConfigError(f"{context} 的 DripHIn 在 DripMode=1/2 时必须大于 0.")
    if pressure_exp <= 0:
        raise ConfigError(f"{context} 的 DripExp 必须大于 0: {pressure_exp}")
    if pressure_pc_min < 0 or pressure_pc_max < 0:
        raise ConfigError(f"{context} 的 DripPcMin/DripPcMax 不能为负数.")
    if wet_width_max < 0:
        raise ConfigError(f"{context} 的 DripWetWidthMax 不能为负数.")
    if source_width < 0:
        raise ConfigError(f"{context} 的 DripSourceWidth 不能为负数.")
    if spread_mode in (4, 5) and source_width <= 0:
        raise ConfigError(f"{context} 的 DripSourceWidth 在 DripSpreadMode=4/5 时必须大于 0.")
    if spread_mode == 4 and wet_width_max > 0:
        warnings.warn(
            f"{context} 的 DripSpreadMode=4 会忽略 DripWetWidthMax；请用 DripSourceWidth 表示固定地表源宽.",
            UserWarning,
            stacklevel=2,
        )
    if spread_mode == 5 and 0 < wet_width_max <= source_width:
        warnings.warn(
            (
                f"{context} 的 DripSpreadMode=5 设置了 DripWetWidthMax={wet_width_max:g} cm, "
                f"不大于 DripSourceWidth={source_width:g} cm；该算例会接近固定宽度源，"
                "建议把 DripWetWidthMax 设为更大的最大湿润斑宽度."
            ),
            UserWarning,
            stacklevel=2,
        )

    event = {
        "date": event_date,
        "start_hour": start_hour,
        "stop_date": stop_date,
        "stop_hour": stop_hour,
        "rate": parse_positive_float(get_cell(record, "ratecmhr", context, "rate(cm/hr)"), context, "rate(cm/hr)"),
        "distance": None,
        "row_number": record.get("__row_number__"),
        "pressure_mode": pressure_mode,
        "pressure_head": pressure_head,
        "pressure_exp": pressure_exp,
        "pressure_pc_min": pressure_pc_min,
        "pressure_pc_max": pressure_pc_max,
        "wet_width_max": wet_width_max,
        "spread_mode": spread_mode,
        "source_width": source_width,
    }
    if require_distance:
        event["distance"] = parse_float(get_cell(record, "distance", context, "Distance"), context, "Distance")
    return event


def validate_drip_records_for_run(run_id, drip_records, drip_node_records):
    """Validate Drip and DripNodes syntax that does not require a generated grid."""
    explicit_nodes = collect_explicit_nodes(run_id, drip_node_records)
    if len(drip_records) > MAX_DRIP_EVENTS:
        raise ConfigError(f"Drip.ID={run_id} 事件数超过 {MAX_DRIP_EVENTS}: {len(drip_records)}")
    require_distance = not explicit_nodes
    return [normalize_drip_record(run_id, record, require_distance) for record in drip_records]


def parse_grid_file(grid_file):
    """Parse node coordinates and boundary water codes from a generated .grd file."""
    if not grid_file.is_file():
        raise ConfigError(f"grid 文件不存在, 无法生成滴灌节点: {grid_file}")
    lines = grid_file.read_text(encoding="utf-8").splitlines()
    try:
        header_index = next(index for index, line in enumerate(lines) if "KAT" in line and "NumNP" in line)
        header_values = lines[header_index + 1].split()
        node_count = int(header_values[1])
        kat = int(header_values[0])
        boundary_count = int(header_values[3])

        node_header = next(index for index, line in enumerate(lines) if "MatNum" in line and "x" in line)
        nodes = {}
        for line in lines[node_header + 1: node_header + 1 + node_count]:
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"invalid node line: {line}")
            nodes[int(parts[0])] = {
                "x": float(parts[1]),
                "y": float(parts[2]),
            }

        boundary_header = next(index for index, line in enumerate(lines) if "CodeW" in line and "Width" in line)
        boundaries = {}
        for line in lines[boundary_header + 1: boundary_header + 1 + boundary_count]:
            parts = line.split()
            if len(parts) < 6:
                raise ValueError(f"invalid boundary line: {line}")
            node = int(parts[0])
            boundaries[node] = {
                "node": node,
                "code_w": int(parts[1]),
                "x": nodes[node]["x"],
                "y": nodes[node]["y"],
                "width": float(parts[5]),
            }
    except (StopIteration, IndexError, KeyError, ValueError) as exc:
        raise ConfigError(f"无法解析 grid 文件用于滴灌节点映射: {grid_file}. {exc}") from exc

    surface_nodes = [boundary for boundary in boundaries.values() if abs(boundary["code_w"]) == 4]
    if not surface_nodes:
        raise ConfigError(f"grid 文件没有 abs(CodeW)==4 的地表边界节点: {grid_file}")
    return {
        "nodes": nodes,
        "kat": kat,
        "boundaries": boundaries,
        "surface_nodes": surface_nodes,
    }


def validate_explicit_nodes(run_id, explicit_nodes, grid_data):
    """Ensure explicit nodes exist and are surface water boundary nodes."""
    for node in explicit_nodes:
        boundary = grid_data["boundaries"].get(node)
        if boundary is None:
            raise ConfigError(f"DripNodes.ID={run_id} 的节点 {node} 不在 grid 边界节点列表中.")
        if abs(boundary["code_w"]) != 4:
            raise ConfigError(f"DripNodes.ID={run_id} 的节点 {node} 不是 abs(CodeW)==4 的地表边界节点.")


def map_distance_to_surface_node(distance, surface_nodes):
    """Map Distance to the nearest surface boundary node by x coordinate."""
    return min(surface_nodes, key=lambda node: (abs(node["x"] - distance), node["node"]))["node"]


def warn_on_mode4_grid_scale(run_id, event, grid_data):
    """Warn when a Mode4 source is much narrower than its boundary segment."""
    if event.get("spread_mode") != 4:
        return
    source_width = float(event.get("source_width", 0.0))
    for node in event["nodes"]:
        boundary = grid_data["boundaries"].get(node)
        if boundary is None:
            continue
        boundary_width = float(boundary["width"])
        if boundary_width <= 0.0:
            continue
        if source_width < MODE4_SMALL_SOURCE_WIDTH_RATIO * boundary_width:
            warnings.warn(
                (
                    f"Drip.ID={run_id} 节点 {node} 的 DripSourceWidth={source_width:g} cm "
                    f"小于边界 Width={boundary_width:g} cm 的 "
                    f"{MODE4_SMALL_SOURCE_WIDTH_RATIO:g} 倍；Mode4水量守恒但局部通量会被摊到完整边界段，"
                    "建议加密滴头附近地表网格或拆分边界段."
                ),
                UserWarning,
                stacklevel=2,
            )


def format_date(value):
    """Format date for MAIZSIM's mm/dd/yyyy parser."""
    return f"{value.month}/{value.day}/{value.year}"


def format_number(value):
    """Format numeric .drp values compactly and reproducibly."""
    return f"{value:g}"


def resolve_drip_output_path(run_dir, run_id):
    """Resolve the .drp path from run.dat, falling back to <run_id>.drp."""
    run_file = run_dir / RUN_FILE_NAME
    if run_file.is_file():
        text_info = read_text_with_encoding(run_file)
        lines = text_info["text"].splitlines()
        if len(lines) > DRIP_FILE_LINE_INDEX:
            raw_value = lines[DRIP_FILE_LINE_INDEX].strip().strip("'\"")
            if raw_value:
                drip_path = Path(raw_value)
                if not drip_path.is_absolute():
                    drip_path = run_dir / drip_path
                return drip_path.resolve()
    return (run_dir / f"{run_id}.drp").resolve()


def write_drip_file(path, events):
    """Write a MAIZSIM .drp file."""
    if not events:
        path.write_text("\n".join(NO_DRIP_LINES) + "\n", encoding="utf-8")
        return

    lines = [
        DRIP_HEADER,
        DRIP_COUNT_HEADER,
        f" {len(events)} ",
        (
            "Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes "
            "DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax "
            "DripSpreadMode DripSourceWidth"
        ),
    ]
    for event in events:
        nodes = event["nodes"]
        fields = [
            format_date(event["date"]),
            format_number(event["start_hour"]),
            format_date(event["stop_date"]),
            format_number(event["stop_hour"]),
            format_number(event["rate"]),
            str(len(nodes)),
        ]
        if (
            event.get("pressure_mode", 0) != 0
            or event.get("wet_width_max", 0.0) > 0.0
            or event.get("spread_mode", 0) != 0
            or event.get("source_width", 0.0) > 0.0
        ):
            fields.extend(
                [
                    str(event["pressure_mode"]),
                    format_number(event["pressure_head"]),
                    format_number(event["pressure_exp"]),
                    format_number(event["pressure_pc_min"]),
                    format_number(event["pressure_pc_max"]),
                ]
            )
            if (
                event.get("wet_width_max", 0.0) > 0.0
                or event.get("spread_mode", 0) != 0
                or event.get("source_width", 0.0) > 0.0
            ):
                fields.append(format_number(event["wet_width_max"]))
            if event.get("spread_mode", 0) != 0 or event.get("source_width", 0.0) > 0.0:
                fields.append(str(event["spread_mode"]))
            if event.get("source_width", 0.0) > 0.0:
                fields.append(format_number(event["source_width"]))
        lines.append(
            " ".join(fields)
        )
        lines.append("Drip application nodes")
        lines.append(" " + " ".join(str(node) for node in nodes))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_drip_events(run, grid_file):
    """Build writable drip events for a run using explicit nodes or Distance mapping."""
    run_id = run["id"]
    drip_records = run.get("drip_records", [])
    drip_node_records = run.get("drip_node_records", [])
    explicit_nodes = collect_explicit_nodes(run_id, drip_node_records)
    normalized_events = validate_drip_records_for_run(run_id, drip_records, drip_node_records)
    if not normalized_events:
        return []

    grid_data = parse_grid_file(grid_file)
    if explicit_nodes:
        validate_explicit_nodes(run_id, explicit_nodes, grid_data)
        for event in normalized_events:
            event["nodes"] = list(explicit_nodes)
            warn_on_mode4_grid_scale(run_id, event, grid_data)
    else:
        for event in normalized_events:
            event["nodes"] = [map_distance_to_surface_node(event["distance"], grid_data["surface_nodes"])]
            warn_on_mode4_grid_scale(run_id, event, grid_data)
    return normalized_events


def write_run_drip_file(run, grid_result):
    """Generate or overwrite one run's .drp file after soil/grid generation."""
    run_id = run["id"]
    run_dir = grid_result["run_dir"]
    grid_file = grid_result["grid_file"]
    events = build_drip_events(run, grid_file)
    output_path = resolve_drip_output_path(run_dir, run_id)
    write_drip_file(output_path, events)
    return {
        "id": run_id,
        "path": output_path,
        "event_count": len(events),
    }


def write_drip_files(runs, grid_results):
    """Generate or overwrite .drp files for all selected runs."""
    grid_by_id = {result["id"]: result for result in grid_results}
    results = []
    for run in runs:
        run_id = run["id"]
        if run_id not in grid_by_id:
            raise ConfigError(f"{run_id} 缺少 soil/grid 生成结果, 无法写出 .drp.")
        results.append(write_run_drip_file(run, grid_by_id[run_id]))
    return results
