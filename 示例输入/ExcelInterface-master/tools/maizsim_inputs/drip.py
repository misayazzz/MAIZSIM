"""Drip irrigation input validation and .drp writer."""

from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from datetime import timedelta
from pathlib import Path
import re

from .errors import ConfigError
from .run_files import RUN_FILE_NAME
from .shared_inputs import read_text_with_encoding


DRIP_HEADER = "***** Fixed-contact finite-supply equivalent drip-line source for a Cartesian half-domain"
DRIP_COUNT_HEADER = "Number of Drip irrigations(max=75)  "
NO_DRIP_LINES = [
    DRIP_HEADER,
    DRIP_COUNT_HEADER,
    " 0 ",
    "No drip irrigation",
]
MAX_DRIP_EVENTS = 75
MAX_DRIP_NODES = 1
DRIP_FILE_LINE_INDEX = 11
EMITTER_FLOW_FIELDS = ("emitterflowlph", "dripemitterflowlph", "flowlph")
EMITTER_SPACING_FIELDS = (
    "emitterspacingcm",
    "dripemitterspacingcm",
    "spacingcm",
)
CONTACT_WIDTH_FIELDS = (
    "contactwidthcm",
    "dripcontactwidthcm",
    "sourcecontactwidthcm",
)
REMOVED_MODE_FIELDS = (
    "ratecmhr",
    "dripmode",
    "pressuremode",
    "driphin",
    "dripexp",
    "drippcmin",
    "drippcmax",
    "dripwetwidthmax",
    "dripspreadmode",
    "dripsourcewidth",
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


def normalize_drip_record(run_id, record):
    """Validate one Drip row and return normalized values used by the writer."""
    context = row_context("Drip", run_id, record)
    event_date = parse_date(get_cell(record, "date", context, "date"), context, "date")
    start_hour = parse_time_hour(get_cell(record, "starttime", context, "StartTime"), context, "StartTime")
    stop_hour = parse_time_hour(get_cell(record, "stoptime", context, "StopTime"), context, "StopTime")
    if start_hour == stop_hour:
        raise ConfigError(f"{context} 的 StartTime 和 StopTime 不能相同.")
    stop_date = event_date + timedelta(days=1) if stop_hour < start_hour else event_date

    removed = [field for field in REMOVED_MODE_FIELDS if not is_blank(record.get(field))]
    if removed:
        fields = ", ".join(removed)
        raise ConfigError(f"{context} 使用了已删除的滴灌字段: {fields}.")

    emitter_flow = get_optional_cell(record, EMITTER_FLOW_FIELDS)
    emitter_spacing = get_optional_cell(record, EMITTER_SPACING_FIELDS)
    contact_width = get_optional_cell(record, CONTACT_WIDTH_FIELDS)
    if emitter_flow is None:
        raise ConfigError(f"{context} 缺少 EmitterFlowLph.")
    if emitter_spacing is None:
        raise ConfigError(f"{context} 缺少 EmitterSpacingCm.")
    if contact_width is None:
        raise ConfigError(f"{context} 缺少 ContactWidthCm.")

    event = {
        "date": event_date,
        "start_hour": start_hour,
        "stop_date": stop_date,
        "stop_hour": stop_hour,
        "emitter_flow_lph": parse_positive_float(
            emitter_flow, context, "EmitterFlowLph"
        ),
        "emitter_spacing_cm": parse_positive_float(
            emitter_spacing, context, "EmitterSpacingCm"
        ),
        "contact_width_cm": parse_positive_float(
            contact_width, context, "ContactWidthCm"
        ),
        "row_number": record.get("__row_number__"),
    }
    return event


def validate_drip_records_for_run(run_id, drip_records, drip_node_records):
    """Validate Drip and DripNodes syntax that does not require a generated grid."""
    explicit_nodes = collect_explicit_nodes(run_id, drip_node_records)
    if len(drip_records) > MAX_DRIP_EVENTS:
        raise ConfigError(f"Drip.ID={run_id} 事件数超过 {MAX_DRIP_EVENTS}: {len(drip_records)}")
    return [normalize_drip_record(run_id, record) for record in drip_records]


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
            "Start_Date Start_hour Stop_Date Stop_hour EmitterFlowLph "
            "EmitterSpacingCm ContactWidthCm Num_nodes"
        ),
    ]
    for event in events:
        nodes = event["nodes"]
        fields = [
            format_date(event["date"]),
            format_number(event["start_hour"]),
            format_date(event["stop_date"]),
            format_number(event["stop_hour"]),
            format_number(event["emitter_flow_lph"]),
            format_number(event["emitter_spacing_cm"]),
            format_number(event["contact_width_cm"]),
            str(len(nodes)),
        ]
        lines.append(
            " ".join(fields)
        )
        lines.append("Drip application nodes")
        lines.append(" " + " ".join(str(node) for node in nodes))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_line_source_contract(events, grid_data):
    """Enforce one fixed x=0 line source and non-overlapping events."""
    if not events:
        return
    if grid_data["kat"] != 2:
        raise ConfigError("固定接触等效滴灌线源只支持笛卡尔 KAT=2 网格.")
    for event in events:
        if len(event["nodes"]) != 1:
            raise ConfigError("每个滴灌事件必须且只能包含一个 x=0 地表节点.")
        node = event["nodes"][0]
        if abs(grid_data["nodes"][node]["x"]) > 1.0e-6:
            raise ConfigError("等效滴灌带必须位于 x=0.")
    emitter_nodes = {event["nodes"][0] for event in events}
    if len(emitter_nodes) != 1:
        raise ConfigError("所有滴灌事件必须使用同一个 x=0 地表节点.")
    spacings = {event["emitter_spacing_cm"] for event in events}
    contact_widths = {event["contact_width_cm"] for event in events}
    if len(spacings) != 1:
        raise ConfigError("同一算例的 EmitterSpacingCm 必须固定.")
    if len(contact_widths) != 1:
        raise ConfigError("同一算例的 ContactWidthCm 必须固定.")
    surface_x_max = max(node["x"] for node in grid_data["surface_nodes"])
    if next(iter(contact_widths)) > surface_x_max:
        raise ConfigError("ContactWidthCm 超出笛卡尔半域地表范围.")
    for event_index, event in enumerate(events):
        event_start = DateTime.combine(event["date"], Time()) + timedelta(
            hours=event["start_hour"]
        )
        event_stop = DateTime.combine(event["stop_date"], Time()) + timedelta(
            hours=event["stop_hour"]
        )
        for earlier in events[:event_index]:
            earlier_start = DateTime.combine(earlier["date"], Time()) + timedelta(
                hours=earlier["start_hour"]
            )
            earlier_stop = DateTime.combine(earlier["stop_date"], Time()) + timedelta(
                hours=earlier["stop_hour"]
            )
            if event_start < earlier_stop and earlier_start < event_stop:
                raise ConfigError("固定接触滴灌事件不能相互重叠.")


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
    else:
        for event in normalized_events:
            event["nodes"] = [
                map_distance_to_surface_node(0.0, grid_data["surface_nodes"])
            ]
    validate_line_source_contract(normalized_events, grid_data)
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
