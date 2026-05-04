"""MAIZSIM 输出指标解析."""

import math

import pandas as pd


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


def weighted_daily_top20_theta(g03):
    """计算每日 0-20 cm 面积加权平均含水量."""
    top = g03.loc[g03["Y"] <= 20].copy()
    if top.empty:
        return math.nan
    grouped_values = []
    for date, group in top.groupby("Date", sort=False):
        area_sum = group["Area"].sum()
        if area_sum > 0:
            grouped_values.append((group["thNew"] * group["Area"]).sum() / area_sum)
    if not grouped_values:
        return math.nan
    return float(pd.Series(grouped_values).mean())


def parse_metrics(sample_dir):
    """解析一个样本目录中的 7 个敏感性输出指标."""
    g01_path = sample_dir / "LOAM2D.g01"
    g03_path = sample_dir / "LOAM2D.G03"
    g05_path = sample_dir / "LOAM2D.G05"

    for path in [g01_path, g03_path, g05_path]:
        if not path.is_file():
            raise FileNotFoundError(f"关键输出文件缺失: {path}")

    g01 = read_csv_output(g01_path)
    start_date, end_date, matured, maturity_date = crop_window(g01)
    g01_window = filter_window(g01, start_date, end_date)

    max_lai = float(g01_window["LAI"].max())
    final_row = g01.loc[clean_note(g01["Note"]).eq("Matured")].head(1)
    if final_row.empty:
        final_row = g01.tail(1)
    final_shoot_dm = float(final_row["shootDM"].iloc[0])
    final_ear_dm = float(final_row["earDM"].iloc[0])

    g03 = filter_window(read_csv_output(g03_path), start_date, end_date)
    mean_top20_theta = weighted_daily_top20_theta(g03)

    g05 = filter_window(read_csv_output(g05_path), start_date, end_date)
    if g05.empty:
        seasonal_transpiration_deficit = math.nan
        seasonal_potential_transpiration = math.nan
        seasonal_actual_transpiration = math.nan
    else:
        final_g05 = g05.tail(1).iloc[0]
        seas_p_tran = float(final_g05["SeasPTran"])
        seas_a_tran = float(final_g05["SeasATran"])
        if seas_p_tran > 0:
            seasonal_transpiration_deficit = float(1 - seas_a_tran / seas_p_tran)
        else:
            seasonal_transpiration_deficit = math.nan
        seasonal_potential_transpiration = seas_p_tran
        seasonal_actual_transpiration = seas_a_tran

    return {
        "max_lai": max_lai,
        "final_shoot_dm": final_shoot_dm,
        "final_ear_dm": final_ear_dm,
        "mean_top20_theta": mean_top20_theta,
        "seasonal_transpiration_deficit": seasonal_transpiration_deficit,
        "seasonal_potential_transpiration": seasonal_potential_transpiration,
        "seasonal_actual_transpiration": seasonal_actual_transpiration,
        "matured": bool(matured),
        "maturity_date": "" if pd.isna(maturity_date) else maturity_date.strftime("%Y-%m-%d"),
    }
