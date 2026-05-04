"""天气文件重写, 避免 Excel ACE 日期误判."""

from datetime import date
from datetime import datetime
from datetime import timedelta

import pandas as pd

from .errors import ConfigError
from .path_utils import resolve_run_dir


SOURCE_DATE_FORMATS = [
    "%m/%d/%Y",
    "%Y-%m-%d",
]


def normalize_column_name(value):
    """标准化 CSV 列名, 用于兼容大小写和首尾空格."""
    return str(value).strip().lower()


def is_enabled(value):
    """判断 Excel 配置中的 0/1 开关是否启用."""
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"true", "yes", "y"}


def require_column(columns, field_name, source_path):
    """按标准化名称读取 CSV 列, 缺失时抛出配置错误."""
    key = normalize_column_name(field_name)
    if key not in columns:
        available = ", ".join(columns.values())
        raise ConfigError(f"天气 CSV 缺少字段 {field_name}: {source_path}. 可用字段: {available}")
    return columns[key]


def find_weather_source(weather_csv_folder, source_name):
    """定位天气 CSV 文件, 并兼容 Windows 下常见的大小写差异."""
    source_path = weather_csv_folder / source_name
    if source_path.is_file():
        return source_path

    target = source_name.lower()
    for candidate in weather_csv_folder.iterdir():
        if candidate.is_file() and candidate.name.lower() == target:
            return candidate

    raise ConfigError(f"天气 CSV 文件不存在: {source_path}")


def parse_source_dates(values, source_path):
    """按显式格式解析源 CSV 日期, 防止 1/5/2007 被误读为 5/1/2007."""
    text_values = values.astype(str).str.strip()
    for date_format in SOURCE_DATE_FORMATS:
        parsed = pd.to_datetime(text_values, format=date_format, errors="coerce")
        if parsed.notna().all():
            return parsed.dt.date

    sample_values = ", ".join(text_values.dropna().head(5).tolist())
    formats = ", ".join(SOURCE_DATE_FORMATS)
    raise ConfigError(f"天气 CSV 日期格式无法解析: {source_path}. 已尝试: {formats}. 示例: {sample_values}")


def coerce_date(value, context):
    """把 Excel 日期值转为 date, 不接受无法确定格式的值."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    for date_format in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(text_value, date_format).date()
        except ValueError:
            continue
    raise ConfigError(f"{context} 日期无法解析: {value}")


def format_date(value):
    """按 MAIZSIM 天气文件格式输出日期."""
    return value.strftime("%m/%d/%Y")


def format_field(value):
    """把 CSV 字段转为 MAIZSIM 可读的紧凑文本."""
    if pd.isna(value):
        return ""
    text_value = str(value).strip()
    if not text_value:
        return ""
    try:
        number = float(text_value)
    except ValueError:
        return text_value
    if number.is_integer():
        return str(int(number))
    return f"{number:.10g}"


def clamp_relative_humidity(value, source_path):
    """把相对湿度限制在 0-100, 防止非物理 RH 写入模型天气文件."""
    if pd.isna(value):
        return value
    text_value = str(value).strip()
    if not text_value:
        return value
    try:
        number = float(text_value)
    except ValueError as exc:
        raise ConfigError(f"天气 CSV 的 RH 字段无法解析为数值: {value}. 来源: {source_path}") from exc
    return min(100.0, max(0.0, number))


def write_fields(file_handle, fields):
    """写出一行空格分隔字段."""
    line = " ".join(format_field(value) for value in fields).rstrip()
    file_handle.write(f"{line}\n")


def read_filtered_weather(paths, run):
    """读取并筛选单个 run 的天气 CSV 记录."""
    source_path = find_weather_source(paths["weather_csv_folder"], run["weather_source_name"])
    weather = pd.read_csv(source_path, dtype=str)
    weather.columns = [str(column).strip() for column in weather.columns]
    columns = {normalize_column_name(column): column for column in weather.columns}

    climate_column = require_column(columns, "ClimateID", source_path)
    weather_column = require_column(columns, "WeatherID", source_path)
    date_column = require_column(columns, "date", source_path)

    parsed_dates = parse_source_dates(weather[date_column], source_path)
    start_date = coerce_date(run["start_date"], f"{run['id']} start_date") - timedelta(days=2)
    end_date = coerce_date(run["end_date"], f"{run['id']} end_date") + timedelta(days=4)

    climate_values = weather[climate_column].astype(str).str.strip()
    weather_values = weather[weather_column].astype(str).str.strip()
    mask = (
        climate_values.eq(run["climate_id"])
        & weather_values.eq(run["weather_id"])
        & (parsed_dates >= start_date)
        & (parsed_dates <= end_date)
    )

    filtered = weather.loc[mask].copy()
    if filtered.empty:
        raise ConfigError(
            f"{run['id']} 没有匹配天气记录: ClimateID={run['climate_id']}, "
            f"WeatherID={run['weather_id']}, 日期={start_date}..{end_date}, 来源={source_path}"
        )

    filtered["_parsed_date"] = parsed_dates.loc[mask]
    sort_columns = ["_parsed_date"]
    hour_column = columns.get(normalize_column_name("Hour"))
    if hour_column is not None:
        filtered["_hour_number"] = pd.to_numeric(filtered[hour_column], errors="coerce")
        if filtered["_hour_number"].isna().any():
            raise ConfigError(f"{run['id']} 天气 CSV 的 Hour 字段存在无法解析的值: {source_path}")
        sort_columns.append("_hour_number")

    return {
        "source_path": source_path,
        "columns": columns,
        "data": filtered.sort_values(sort_columns),
    }


def write_hourly_weather(target_path, run, weather_info):
    """写出 hourly 天气文件."""
    columns = weather_info["columns"]
    data = weather_info["data"]
    required_fields = ["jday", "date", "Hour", "Srad", "temperature", "rain"]
    for field_name in required_fields:
        require_column(columns, field_name, weather_info["source_path"])

    include_wind = is_enabled(run["daily_wind"])
    include_rh = is_enabled(run["rel_humid"])
    include_co2 = is_enabled(run["daily_co2"])
    wind_column = require_column(columns, "wind", weather_info["source_path"]) if include_wind else None
    rh_column = require_column(columns, "RH", weather_info["source_path"]) if include_rh else None
    co2_column = require_column(columns, "CO2", weather_info["source_path"]) if include_co2 else None

    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        with temp_path.open("w", encoding="ascii", newline="\n") as file_handle:
            file_handle.write(f"*** {run['id']},  hourly weather data\n")
            file_handle.write(" JDay   Date  Hour     Rad      Temper    rain     Wind   RH   CO2\n")
            for _, row in data.iterrows():
                fields = [
                    row[columns[normalize_column_name("jday")]],
                    f"'{format_date(row['_parsed_date'])}'",
                    row[columns[normalize_column_name("Hour")]],
                    row[columns[normalize_column_name("Srad")]],
                    row[columns[normalize_column_name("temperature")]],
                    row[columns[normalize_column_name("rain")]],
                ]
                if include_wind:
                    fields.append(row[wind_column])
                if include_rh:
                    fields.append(clamp_relative_humidity(row[rh_column], weather_info["source_path"]))
                if include_co2:
                    fields.append(row[co2_column])
                write_fields(file_handle, fields)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_daily_weather(target_path, run, weather_info):
    """写出 daily 天气文件."""
    columns = weather_info["columns"]
    data = weather_info["data"]
    required_fields = ["jday", "date", "Srad", "tmax", "tmin", "rain"]
    for field_name in required_fields:
        require_column(columns, field_name, weather_info["source_path"])

    include_wind = is_enabled(run["daily_wind"])
    include_rh = is_enabled(run["rel_humid"])
    include_co2 = is_enabled(run["daily_co2"])
    wind_column = require_column(columns, "wind", weather_info["source_path"]) if include_wind else None
    rh_column = require_column(columns, "RH", weather_info["source_path"]) if include_rh else None
    co2_column = require_column(columns, "CO2", weather_info["source_path"]) if include_co2 else None

    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        with temp_path.open("w", encoding="ascii", newline="\n") as file_handle:
            file_handle.write(f"*** {run['id']},  daily weather data\n")
            file_handle.write(" JDay   Date       Rad      Temper    rain \n")
            for _, row in data.iterrows():
                fields = [
                    row[columns[normalize_column_name("jday")]],
                    f"'{format_date(row['_parsed_date'])}'",
                    row[columns[normalize_column_name("Srad")]],
                    row[columns[normalize_column_name("tmax")]],
                    row[columns[normalize_column_name("tmin")]],
                    row[columns[normalize_column_name("rain")]],
                ]
                if include_wind:
                    fields.append(row[wind_column])
                if include_rh:
                    fields.append(clamp_relative_humidity(row[rh_column], weather_info["source_path"]))
                if include_co2:
                    fields.append(row[co2_column])
                write_fields(file_handle, fields)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def rewrite_weather_files(paths, runs):
    """按显式日期格式重写每个 selected run 的 .wea 文件."""
    results = []
    for run in runs:
        run_dir = resolve_run_dir(paths["root_path"], run["path"])
        if not run_dir.is_dir():
            raise ConfigError(f"{run['id']} 的 run 目录不存在, 无法重写天气文件: {run_dir}")

        target_path = run_dir / run["weather_file_name"]
        weather_info = read_filtered_weather(paths, run)
        weather_time = run["weather_time"].strip().lower()
        if weather_time == "hourly":
            write_hourly_weather(target_path, run, weather_info)
        elif weather_time == "daily":
            write_daily_weather(target_path, run, weather_info)
        else:
            raise ConfigError(f"{run['id']} 的 Weather.Time 不支持: {run['weather_time']}")

        if not target_path.is_file() or target_path.stat().st_size <= 0:
            raise ConfigError(f"{run['id']} 的天气文件重写失败或为空: {target_path}")
        results.append(
            {
                "id": run["id"],
                "source": weather_info["source_path"],
                "target": target_path,
                "rows": len(weather_info["data"]),
            }
        )
    return results
