"""MAIZSIM 输出指标解析."""

import math

import pandas as pd

from .metric_catalog import DEPTH_RANGES


EVENT_NOTES = {
    "germinated": "Germinated",
    "emerged": "Emerged",
    "tasselinit": "Tasselinit",
    "tasseled": "Tasseled",
    "silked": "Silked",
    "grainfill": "grainFill",
    "matured": "Matured",
}


def read_csv_output(path):
    """读取模型 CSV 风格输出并清理列名."""
    frame = pd.read_csv(path, skipinitialspace=True)
    frame.columns = [column.strip() for column in frame.columns]
    return frame


def parse_dates(frame):
    """解析输出表中的 Date 列."""
    column_name = "Date" if "Date" in frame.columns else "date"
    return pd.to_datetime(frame[column_name].astype(str).str.strip(), format="%m/%d/%Y", errors="coerce")


def clean_note(series):
    """清理 Note 字段中的引号和空白."""
    return series.astype(str).str.strip().str.strip('"')


def crop_window(g01):
    """根据 g01 输出确定作物生长期窗口."""
    dates = parse_dates(g01)
    notes = clean_note(g01["Note"])
    matured_mask = notes.eq("Matured")
    if matured_mask.any():
        matured_index = matured_mask.idxmax()
        return dates.iloc[0], dates.loc[matured_index], True, dates.loc[matured_index]
    return dates.iloc[0], dates.iloc[-1], False, pd.NaT


def filter_window(frame, start_date, end_date):
    """按日期窗口筛选输出表."""
    dates = parse_dates(frame)
    return frame.loc[(dates >= start_date) & (dates <= end_date)].copy()


def numeric_series(frame, column_name):
    """读取数值列, 不存在时返回空序列."""
    if column_name not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column_name], errors="coerce")


def safe_float(value):
    """将标量转换为 float, 失败时返回 NaN."""
    try:
        if pd.isna(value):
            return math.nan
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def safe_divide(numerator, denominator):
    """安全除法."""
    numerator = safe_float(numerator)
    denominator = safe_float(denominator)
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return math.nan
    return float(numerator / denominator)


def row_value(row, column_name):
    """从输出行读取数值字段."""
    if column_name not in row.index:
        return math.nan
    return safe_float(row[column_name])


def first_event_dates(g01):
    """提取 G01 Note 中每个生育事件的首次日期."""
    dates = parse_dates(g01)
    notes = clean_note(g01["Note"])
    result = {}
    for event_name, note_name in EVENT_NOTES.items():
        mask = notes.eq(note_name)
        if mask.any():
            result[event_name] = dates.loc[mask].iloc[0]
        else:
            result[event_name] = pd.NaT
    return result


def date_text(value):
    """输出 ISO 日期文本."""
    if pd.isna(value):
        return ""
    return value.strftime("%Y-%m-%d")


def day_of_year(value):
    """返回日期的年内日."""
    if pd.isna(value):
        return math.nan
    return int(value.dayofyear)


def censored_doy(value, end_date):
    """返回事件 DOY; 事件缺失时用模拟结束 DOY + 1."""
    if pd.isna(value):
        return int(end_date.dayofyear) + 1
    return int(value.dayofyear)


def days_between(start_date, end_date):
    """计算两个日期之间的天数."""
    if pd.isna(start_date) or pd.isna(end_date):
        return math.nan
    return float((end_date - start_date).days)


def date_of_series_max(frame, column_name):
    """返回数值列首次最大值所在日期 DOY."""
    values = numeric_series(frame, column_name)
    if values.dropna().empty:
        return math.nan
    index = values.idxmax()
    dates = parse_dates(frame)
    return day_of_year(dates.loc[index])


def daily_mean_integral(frame, column_name):
    """按日均值累加形成季节积分."""
    values = numeric_series(frame, column_name)
    if values.dropna().empty:
        return math.nan
    work = pd.DataFrame({"Date": parse_dates(frame), "value": values})
    daily = work.dropna().groupby("Date", sort=False)["value"].mean()
    if daily.empty:
        return math.nan
    return float(daily.sum())


def final_time_mask(frame):
    """定位空间输出中的最后一个时间步."""
    if "Date_time" in frame.columns:
        date_time = pd.to_numeric(frame["Date_time"], errors="coerce")
        if not date_time.dropna().empty:
            return date_time.eq(date_time.max())
    dates = parse_dates(frame)
    if dates.dropna().empty:
        return pd.Series(False, index=frame.index)
    return dates.eq(dates.max())


def depth_mask(frame, lower, upper):
    """按 Y 坐标构建深度层筛选."""
    y_values = numeric_series(frame, "Y")
    mask = y_values.le(upper)
    if lower > 0:
        mask &= y_values.gt(lower)
    else:
        mask &= y_values.ge(lower)
    return mask


def weighted_values_by_date(frame, value_column, mask):
    """计算每个日期的面积加权值."""
    subset = frame.loc[mask].copy()
    if subset.empty or value_column not in subset.columns or "Area" not in subset.columns:
        return pd.Series(dtype=float)
    subset["_value"] = pd.to_numeric(subset[value_column], errors="coerce")
    subset["_area"] = pd.to_numeric(subset["Area"], errors="coerce")
    subset["_date"] = parse_dates(subset)
    subset = subset.loc[subset["_value"].notna() & subset["_area"].gt(0) & subset["_date"].notna()]
    if subset.empty:
        return pd.Series(dtype=float)

    def weighted_average(group):
        area_sum = group["_area"].sum()
        if area_sum <= 0:
            return math.nan
        return float((group["_value"] * group["_area"]).sum() / area_sum)

    return subset.groupby("_date", sort=False).apply(weighted_average, include_groups=False).dropna()


def weighted_value_at_final_time(frame, value_column, mask):
    """计算最后时间步的面积加权值."""
    final_mask = final_time_mask(frame)
    subset = frame.loc[mask & final_mask].copy()
    if subset.empty or value_column not in subset.columns or "Area" not in subset.columns:
        return math.nan
    values = pd.to_numeric(subset[value_column], errors="coerce")
    weights = pd.to_numeric(subset["Area"], errors="coerce")
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return math.nan
    return float((values.loc[valid] * weights.loc[valid]).sum() / weights.loc[valid].sum())


def weighted_daily_frame(frame, value_columns, mask):
    """一次性计算多个列的每日面积加权值."""
    existing_columns = [column for column in value_columns if column in frame.columns]
    if not existing_columns or "Area" not in frame.columns:
        return pd.DataFrame()
    subset = frame.loc[mask, ["Area", *existing_columns]].copy()
    if subset.empty:
        return pd.DataFrame(columns=existing_columns)
    subset["_date"] = parse_dates(frame.loc[mask])
    subset["_area"] = pd.to_numeric(subset["Area"], errors="coerce")
    values = subset[existing_columns].apply(pd.to_numeric, errors="coerce")
    valid = subset["_date"].notna() & subset["_area"].gt(0)
    if not valid.any():
        return pd.DataFrame(columns=existing_columns)
    dates = subset.loc[valid, "_date"]
    weights = subset.loc[valid, "_area"]
    values = values.loc[valid]
    weighted_sum = values.multiply(weights, axis=0).groupby(dates, sort=False).sum()
    area_sum = values.notna().multiply(weights, axis=0).groupby(dates, sort=False).sum()
    return weighted_sum.divide(area_sum.where(area_sum.gt(0)))


def weighted_final_values(frame, value_columns, mask):
    """一次性计算多个列最后时间步的面积加权值."""
    existing_columns = [column for column in value_columns if column in frame.columns]
    result = {column: math.nan for column in value_columns}
    if not existing_columns or "Area" not in frame.columns:
        return result
    subset = frame.loc[mask & final_time_mask(frame), ["Area", *existing_columns]].copy()
    if subset.empty:
        return result
    weights = pd.to_numeric(subset["Area"], errors="coerce")
    values = subset[existing_columns].apply(pd.to_numeric, errors="coerce")
    for column in existing_columns:
        valid = values[column].notna() & weights.gt(0)
        if valid.any():
            result[column] = float((values.loc[valid, column] * weights.loc[valid]).sum() / weights.loc[valid].sum())
    return result


def weighted_daily_top20_theta(g03):
    """计算每日 0-20 cm 面积加权平均含水量."""
    values = weighted_values_by_date(g03, "thNew", depth_mask(g03, 0, 20))
    if values.empty:
        return math.nan
    return float(values.mean())


def add_g01_metrics(metrics, g01, start_date, end_date, matured, maturity_date):
    """添加 G01 作物生长、物候和生理指标."""
    g01_window = filter_window(g01, start_date, end_date)
    final_row = g01.loc[clean_note(g01["Note"]).eq("Matured")].head(1)
    if final_row.empty:
        final_row = g01.tail(1)
    final_row = final_row.iloc[0]
    event_dates = first_event_dates(g01)

    metrics["max_lai"] = float(numeric_series(g01_window, "LAI").max())
    metrics["final_shoot_dm"] = row_value(final_row, "shootDM")
    metrics["final_ear_dm"] = row_value(final_row, "earDM")
    metrics["matured"] = bool(matured)
    metrics["maturity_date"] = date_text(maturity_date)

    for event_name, event_date in event_dates.items():
        metrics[f"{event_name}_flag"] = int(not pd.isna(event_date))
        metrics[f"{event_name}_date"] = date_text(event_date)
    metrics["germination_doy_censored"] = censored_doy(event_dates["germinated"], end_date)
    metrics["emergence_doy_censored"] = censored_doy(event_dates["emerged"], end_date)
    metrics["tasselinit_doy_censored"] = censored_doy(event_dates["tasselinit"], end_date)
    metrics["tasseled_doy_censored"] = censored_doy(event_dates["tasseled"], end_date)
    metrics["silking_doy_censored"] = censored_doy(event_dates["silked"], end_date)
    metrics["grainfill_start_doy_censored"] = censored_doy(event_dates["grainfill"], end_date)
    metrics["maturity_doy_censored"] = censored_doy(maturity_date, end_date)

    metrics["emergence_to_tasselinit_days"] = days_between(event_dates["emerged"], event_dates["tasselinit"])
    metrics["emergence_to_silking_days"] = days_between(event_dates["emerged"], event_dates["silked"])
    metrics["silking_to_grainfill_days"] = days_between(event_dates["silked"], event_dates["grainfill"])
    metrics["grainfill_to_maturity_days_censored"] = (
        metrics["maturity_doy_censored"] - metrics["grainfill_start_doy_censored"]
    )
    metrics["season_length_days_censored"] = metrics["maturity_doy_censored"] - int(start_date.dayofyear) + 1

    metrics["mean_lai"] = float(numeric_series(g01_window, "LAI").mean())
    metrics["final_lai"] = row_value(final_row, "LAI")
    metrics["lai_integral"] = daily_mean_integral(g01_window, "LAI")
    metrics["date_max_lai_doy"] = date_of_series_max(g01_window, "LAI")
    metrics["max_la_pl"] = float(numeric_series(g01_window, "LA_pl").max())
    metrics["max_la_dead"] = float(numeric_series(g01_window, "LA_dead").max())
    metrics["final_la_dead"] = row_value(final_row, "LA_dead")
    metrics["max_leaves"] = float(numeric_series(g01_window, "Leaves").max())
    metrics["final_leaves"] = row_value(final_row, "Leaves")
    metrics["final_mature_leaves"] = row_value(final_row, "MaturLvs")
    metrics["final_dropped_leaves"] = row_value(final_row, "Dropped")

    metrics["final_total_dm"] = row_value(final_row, "totalDM")
    metrics["final_leaf_dm"] = row_value(final_row, "TotLeafDM")
    metrics["final_dropped_leaf_dm"] = row_value(final_row, "DrpLfDM")
    metrics["final_stem_dm"] = row_value(final_row, "stemDM")
    metrics["final_root_dm"] = row_value(final_row, "rootDM")
    metrics["final_soil_root_dm"] = row_value(final_row, "SoilRt")
    metrics["final_soluble_c"] = row_value(final_row, "solubleC")
    metrics["non_ear_shoot_dm"] = metrics["final_shoot_dm"] - metrics["final_ear_dm"]
    metrics["ear_shoot_ratio"] = safe_divide(metrics["final_ear_dm"], metrics["final_shoot_dm"])
    metrics["root_shoot_ratio"] = safe_divide(metrics["final_root_dm"], metrics["final_shoot_dm"])
    metrics["leaf_shoot_ratio"] = safe_divide(metrics["final_leaf_dm"], metrics["final_shoot_dm"])
    metrics["stem_shoot_ratio"] = safe_divide(metrics["final_stem_dm"], metrics["final_shoot_dm"])

    metrics["mean_leaf_wp"] = float(numeric_series(g01_window, "LeafWP").mean())
    metrics["min_leaf_wp"] = float(numeric_series(g01_window, "LeafWP").min())
    metrics["mean_av_gs"] = float(numeric_series(g01_window, "av_gs").mean())
    metrics["min_av_gs"] = float(numeric_series(g01_window, "av_gs").min())
    metrics["mean_vpd"] = float(numeric_series(g01_window, "VPD").mean())
    metrics["max_vpd"] = float(numeric_series(g01_window, "VPD").max())
    metrics["mean_tcan"] = float(numeric_series(g01_window, "Tcan").mean())
    metrics["max_tcan"] = float(numeric_series(g01_window, "Tcan").max())
    metrics["seasonal_pn_sum"] = float(numeric_series(g01_window, "Pn").sum())
    metrics["seasonal_pg_sum"] = float(numeric_series(g01_window, "Pg").sum())
    metrics["seasonal_respiration_sum"] = float(numeric_series(g01_window, "Respir").sum())
    metrics["seasonal_et_demand_sum"] = float(numeric_series(g01_window, "ETdmd").sum())
    metrics["seasonal_et_supply_sum"] = float(numeric_series(g01_window, "ETsply").sum())
    metrics["et_supply_demand_ratio"] = safe_divide(
        metrics["seasonal_et_supply_sum"],
        metrics["seasonal_et_demand_sum"],
    )

    metrics["final_n_demand"] = row_value(final_row, "N_Dem")
    metrics["final_n_uptake"] = row_value(final_row, "NUpt")
    metrics["final_leaf_n"] = row_value(final_row, "LeafN")
    metrics["mean_leaf_n"] = float(numeric_series(g01_window, "LeafN").mean())
    metrics["seasonal_n_uptake_sum"] = float(numeric_series(g01_window, "NUpt").sum())
    metrics["seasonal_nitr_sum"] = float(numeric_series(g01_window, "Nitr").sum())


def add_g03_metrics(metrics, g03):
    """添加 G03 土壤剖面指标."""
    metrics["mean_top20_theta"] = weighted_daily_top20_theta(g03)
    column_stats = {
        "thNew": ["mean", "final", "min", "max"],
        "hNew": ["mean", "final", "min"],
        "Temp": ["mean", "final"],
        "NO3N": ["mean", "final"],
        "NH4N": ["mean", "final"],
        "CO2Conc": ["mean", "final"],
        "O2Conc": ["mean", "final"],
        "N2OConc": ["mean", "final"],
    }
    value_columns = list(column_stats)
    for depth_label, lower, upper in DEPTH_RANGES:
        mask = depth_mask(g03, lower, upper)
        daily_frame = weighted_daily_frame(g03, value_columns, mask)
        final_values = weighted_final_values(g03, value_columns, mask)
        for column, stats in column_stats.items():
            daily_values = daily_frame[column].dropna() if column in daily_frame.columns else pd.Series(dtype=float)
            if "mean" in stats:
                metrics[f"mean_{column}_{depth_label}"] = float(daily_values.mean()) if not daily_values.empty else math.nan
            if "min" in stats:
                metrics[f"min_{column}_{depth_label}"] = float(daily_values.min()) if not daily_values.empty else math.nan
            if "max" in stats:
                metrics[f"max_{column}_{depth_label}"] = float(daily_values.max()) if not daily_values.empty else math.nan
            if "final" in stats:
                metrics[f"final_{column}_{depth_label}"] = final_values.get(column, math.nan)


def sum_for_mask(frame, column_name, mask):
    """对筛选后的列求和."""
    values = numeric_series(frame.loc[mask], column_name)
    if values.dropna().empty:
        return math.nan
    return float(values.sum())


def mean_for_mask(frame, column_name, mask):
    """对筛选后的列求均值."""
    values = numeric_series(frame.loc[mask], column_name)
    if values.dropna().empty:
        return math.nan
    return float(values.mean())


def add_g04_metrics(metrics, g04):
    """添加 G04 根系与吸收指标."""
    final_mask = final_time_mask(g04)
    for depth_label, lower, upper in DEPTH_RANGES:
        mask = depth_mask(g04, lower, upper)
        for column in ["RMassM", "RMassY", "RDenM", "RDenY", "WaterSink", "NitSink", "GasSink"]:
            metrics[f"seasonal_sum_{column}_{depth_label}"] = sum_for_mask(g04, column, mask)
            metrics[f"seasonal_mean_{column}_{depth_label}"] = mean_for_mask(g04, column, mask)
            metrics[f"final_sum_{column}_{depth_label}"] = sum_for_mask(g04, column, mask & final_mask)

    final_rows = g04.loc[final_mask].copy()
    if final_rows.empty:
        metrics["final_root_depth_max"] = math.nan
        metrics["final_root_depth_d95"] = math.nan
        metrics["root_density_0_20_share"] = math.nan
    else:
        root_density = numeric_series(final_rows, "RDenM").fillna(0) + numeric_series(final_rows, "RDenY").fillna(0)
        y_values = numeric_series(final_rows, "Y")
        active = root_density.gt(0) & y_values.notna()
        metrics["final_root_depth_max"] = float(y_values.loc[active].max()) if active.any() else math.nan
        total_density = float(root_density.sum())
        if total_density > 0:
            ordered = pd.DataFrame({"Y": y_values, "density": root_density}).dropna().sort_values("Y")
            ordered["cumulative"] = ordered["density"].cumsum() / total_density
            d95_rows = ordered.loc[ordered["cumulative"].ge(0.95)]
            metrics["final_root_depth_d95"] = float(d95_rows["Y"].iloc[0]) if not d95_rows.empty else math.nan
            metrics["root_density_0_20_share"] = safe_divide(root_density.loc[y_values.le(20)].sum(), total_density)
        else:
            metrics["final_root_depth_d95"] = math.nan
            metrics["root_density_0_20_share"] = math.nan

    water_sink = numeric_series(g04, "WaterSink")
    nit_sink = numeric_series(g04, "NitSink")
    y_values = numeric_series(g04, "Y")
    metrics["water_sink_0_20_share"] = safe_divide(water_sink.loc[y_values.le(20)].sum(), water_sink.sum())
    metrics["nit_sink_0_20_share"] = safe_divide(nit_sink.loc[y_values.le(20)].sum(), nit_sink.sum())


def add_g05_metrics(metrics, g05):
    """添加 G05 水分平衡指标."""
    if g05.empty:
        g05_final = pd.Series(dtype=float)
    else:
        g05_final = g05.tail(1).iloc[0]
    seas_p_tran = row_value(g05_final, "SeasPTran")
    seas_a_tran = row_value(g05_final, "SeasATran")
    seas_p_so_ev = row_value(g05_final, "SeasPSoEv")
    seas_a_so_ev = row_value(g05_final, "SeasASoEv")
    seas_rain = row_value(g05_final, "SeasRain")

    metrics["seasonal_potential_transpiration"] = seas_p_tran
    metrics["seasonal_actual_transpiration"] = seas_a_tran
    metrics["seasonal_transpiration_deficit"] = 1 - seas_a_tran / seas_p_tran if seas_p_tran > 0 else math.nan
    metrics["seasonal_potential_soil_evap"] = seas_p_so_ev
    metrics["seasonal_actual_soil_evap"] = seas_a_so_ev
    metrics["soil_evap_deficit"] = 1 - seas_a_so_ev / seas_p_so_ev if seas_p_so_ev > 0 else math.nan
    metrics["seasonal_rain"] = seas_rain
    metrics["seasonal_infiltration"] = row_value(g05_final, "SeasInfil")
    metrics["final_drainage"] = row_value(g05_final, "Drainage")
    metrics["final_runoff"] = row_value(g05_final, "Runoff")
    metrics["final_n_leach"] = row_value(g05_final, "N_Leach")
    metrics["final_theta_avail"] = row_value(g05_final, "ThetaAvail")
    metrics["actual_et"] = seas_a_tran + seas_a_so_ev
    metrics["potential_et"] = seas_p_tran + seas_p_so_ev
    metrics["et_deficit"] = 1 - metrics["actual_et"] / metrics["potential_et"] if metrics["potential_et"] > 0 else math.nan
    metrics["transpiration_fraction"] = safe_divide(seas_a_tran, metrics["actual_et"])
    metrics["soil_evap_fraction"] = safe_divide(seas_a_so_ev, metrics["actual_et"])
    metrics["infiltration_rain_ratio"] = safe_divide(metrics["seasonal_infiltration"], seas_rain)
    metrics["runoff_rain_ratio"] = safe_divide(metrics["final_runoff"], seas_rain)
    metrics["drainage_rain_ratio"] = safe_divide(metrics["final_drainage"], seas_rain)


def add_simple_time_metrics(metrics, frame, columns, group_prefix):
    """对时序输出添加 sum/mean/final 指标."""
    final_row = frame.tail(1).iloc[0] if not frame.empty else pd.Series(dtype=float)
    for column in columns:
        values = numeric_series(frame, column)
        metrics[f"seasonal_sum_{column}"] = float(values.sum()) if not values.dropna().empty else math.nan
        metrics[f"seasonal_mean_{column}"] = float(values.mean()) if not values.dropna().empty else math.nan
        metrics[f"final_{column}"] = row_value(final_row, column)


def add_g07_metrics(metrics, g07):
    """添加 G07 氮碳库指标."""
    final_rows = g07.loc[final_time_mask(g07)].copy()
    columns = ["Humus_N", "Humus_C", "Litter_N", "Litter_C", "Manure_N", "Manure_C", "Root_N", "Root_C"]
    for column in columns:
        values = numeric_series(g07, column)
        final_values = numeric_series(final_rows, column)
        metrics[f"seasonal_mean_{column}"] = float(values.mean()) if not values.dropna().empty else math.nan
        metrics[f"final_{column}"] = float(final_values.mean()) if not final_values.dropna().empty else math.nan


def add_mass_balance_metrics(metrics, massbl, runoff_balance):
    """添加质量平衡与径流平衡指标."""
    massbl_final = massbl.tail(1).iloc[0] if not massbl.empty else pd.Series(dtype=float)
    for column in [
        "Min_N",
        "Humus_N",
        "Humus_C",
        "Litter_N",
        "Litter_C",
        "All_N",
        "All_C",
        "water",
        "Denitr",
        "CFlux",
        "OM_CO2_C",
        "Root_CO2_C",
    ]:
        metrics[f"final_massbl_{column}"] = row_value(massbl_final, column)

    runoff_final = runoff_balance.tail(1).iloc[0] if not runoff_balance.empty else pd.Series(dtype=float)
    for column in ["Rainfall", "Inifiltration", "Runoff@end", "WaterStorage", "LeftDischarge", "RightDischarge"]:
        safe_name = column.replace("@", "_")
        metrics[f"final_runoff_balance_{safe_name}"] = row_value(runoff_final, column)


def parse_metrics(sample_dir):
    """解析一个样本目录中的旧版和扩展敏感性输出指标."""
    required_paths = {
        "g01": sample_dir / "LOAM2D.g01",
        "g03": sample_dir / "LOAM2D.G03",
        "g05": sample_dir / "LOAM2D.G05",
    }
    for path in required_paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"关键输出文件缺失: {path}")

    g01 = read_csv_output(required_paths["g01"])
    start_date, end_date, matured, maturity_date = crop_window(g01)
    metrics = {}
    add_g01_metrics(metrics, g01, start_date, end_date, matured, maturity_date)
    add_g03_metrics(metrics, filter_window(read_csv_output(required_paths["g03"]), start_date, end_date))
    add_g05_metrics(metrics, filter_window(read_csv_output(required_paths["g05"]), start_date, end_date))

    optional_readers = [
        ("g04", sample_dir / "LOAM2D.G04", add_g04_metrics),
        (
            "g06",
            sample_dir / "LOAM2D.G06",
            lambda result, frame: add_simple_time_metrics(
                result,
                frame,
                ["PARInt", "RADInt", "WATPOT", "WATACT", "WATRAT", "SoilEA", "WATTSM", "RNS", "RNC", "Flux"],
                "g06",
            ),
        ),
        ("g07", sample_dir / "LOAM2D.G07", add_g07_metrics),
    ]
    for _, path, callback in optional_readers:
        if path.is_file():
            callback(metrics, filter_window(read_csv_output(path), start_date, end_date))

    massbl_path = sample_dir / "MassBl.out"
    runoff_path = sample_dir / "MassBlRunOff.out"
    massbl = filter_window(read_csv_output(massbl_path), start_date, end_date) if massbl_path.is_file() else pd.DataFrame()
    runoff_balance = (
        filter_window(read_csv_output(runoff_path), start_date, end_date) if runoff_path.is_file() else pd.DataFrame()
    )
    add_mass_balance_metrics(metrics, massbl, runoff_balance)
    return metrics
