"""扩展敏感性指标目录."""


DEPTH_RANGES = [
    ("0_10", 0, 10),
    ("0_20", 0, 20),
    ("10_20", 10, 20),
    ("20_40", 20, 40),
    ("40_80", 40, 80),
    ("80_120", 80, 120),
    ("120_200", 120, 200),
    ("0_200", 0, 200),
]

LEGACY_METRICS = [
    {
        "name": "max_lai",
        "group": "legacy_crop",
        "label": "Maximum LAI",
        "morris": True,
    },
    {
        "name": "final_shoot_dm",
        "group": "legacy_crop",
        "label": "Final shoot dry matter",
        "morris": True,
    },
    {
        "name": "final_ear_dm",
        "group": "legacy_crop",
        "label": "Final ear dry matter",
        "morris": True,
    },
    {
        "name": "mean_top20_theta",
        "group": "legacy_soil_water",
        "label": "Mean 0-20 cm water content",
        "morris": True,
    },
    {
        "name": "seasonal_transpiration_deficit",
        "group": "legacy_water_balance",
        "label": "Seasonal transpiration deficit",
        "morris": True,
    },
    {
        "name": "seasonal_potential_transpiration",
        "group": "legacy_water_balance",
        "label": "Seasonal potential transpiration",
        "morris": True,
    },
    {
        "name": "seasonal_actual_transpiration",
        "group": "legacy_water_balance",
        "label": "Seasonal actual transpiration",
        "morris": True,
    },
]


def metric(name, group, label=None, morris=True):
    """创建指标目录记录."""
    return {
        "name": name,
        "group": group,
        "label": label or name,
        "morris": morris,
    }


def g01_metrics():
    """返回 G01 作物输出扩展指标."""
    rows = []
    event_labels = {
        "germinated": "Germination",
        "emerged": "Emergence",
        "tasselinit": "Tassel initiation",
        "tasseled": "Tasseling",
        "silked": "Silking",
        "grainfill": "Grain filling start",
        "matured": "Maturity",
    }
    for name, label in event_labels.items():
        rows.append(metric(f"{name}_flag", "g01_phenology", f"{label} flag"))
    for name, label in event_labels.items():
        rows.append(metric(f"{name}_date", "g01_phenology", f"{label} date", morris=False))

    rows.extend(
        [
            metric("germination_doy_censored", "g01_phenology", "Germination DOY censored"),
            metric("emergence_doy_censored", "g01_phenology", "Emergence DOY censored"),
            metric("tasselinit_doy_censored", "g01_phenology", "Tassel initiation DOY censored"),
            metric("tasseled_doy_censored", "g01_phenology", "Tasseling DOY censored"),
            metric("silking_doy_censored", "g01_phenology", "Silking DOY censored"),
            metric("grainfill_start_doy_censored", "g01_phenology", "Grain filling start DOY censored"),
            metric("maturity_doy_censored", "g01_phenology", "Maturity DOY censored"),
            metric("emergence_to_tasselinit_days", "g01_phenology", "Emergence to tassel initiation days"),
            metric("emergence_to_silking_days", "g01_phenology", "Emergence to silking days"),
            metric("silking_to_grainfill_days", "g01_phenology", "Silking to grain filling days"),
            metric("grainfill_to_maturity_days_censored", "g01_phenology", "Grain filling to maturity days censored"),
            metric("season_length_days_censored", "g01_phenology", "Season length days censored"),
            metric("mean_lai", "g01_lai_leaf", "Mean LAI"),
            metric("final_lai", "g01_lai_leaf", "Final LAI"),
            metric("lai_integral", "g01_lai_leaf", "LAI integral"),
            metric("date_max_lai_doy", "g01_lai_leaf", "Date of maximum LAI DOY"),
            metric("max_la_pl", "g01_lai_leaf", "Maximum plant leaf area"),
            metric("max_la_dead", "g01_lai_leaf", "Maximum dead leaf area"),
            metric("final_la_dead", "g01_lai_leaf", "Final dead leaf area"),
            metric("max_leaves", "g01_lai_leaf", "Maximum leaves"),
            metric("final_leaves", "g01_lai_leaf", "Final leaves"),
            metric("final_mature_leaves", "g01_lai_leaf", "Final mature leaves"),
            metric("final_dropped_leaves", "g01_lai_leaf", "Final dropped leaves"),
            metric("final_total_dm", "g01_biomass", "Final total dry matter"),
            metric("final_leaf_dm", "g01_biomass", "Final total leaf dry matter"),
            metric("final_dropped_leaf_dm", "g01_biomass", "Final dropped leaf dry matter"),
            metric("final_stem_dm", "g01_biomass", "Final stem dry matter"),
            metric("final_root_dm", "g01_biomass", "Final root dry matter"),
            metric("final_soil_root_dm", "g01_biomass", "Final soil root dry matter"),
            metric("final_soluble_c", "g01_biomass", "Final soluble carbon"),
            metric("non_ear_shoot_dm", "g01_biomass", "Final non-ear shoot dry matter"),
            metric("ear_shoot_ratio", "g01_biomass", "Ear to shoot dry matter ratio"),
            metric("root_shoot_ratio", "g01_biomass", "Root to shoot dry matter ratio"),
            metric("leaf_shoot_ratio", "g01_biomass", "Leaf to shoot dry matter ratio"),
            metric("stem_shoot_ratio", "g01_biomass", "Stem to shoot dry matter ratio"),
            metric("mean_leaf_wp", "g01_stress_gas", "Mean leaf water potential"),
            metric("min_leaf_wp", "g01_stress_gas", "Minimum leaf water potential"),
            metric("mean_av_gs", "g01_stress_gas", "Mean stomatal conductance"),
            metric("min_av_gs", "g01_stress_gas", "Minimum stomatal conductance"),
            metric("mean_vpd", "g01_stress_gas", "Mean VPD"),
            metric("max_vpd", "g01_stress_gas", "Maximum VPD"),
            metric("mean_tcan", "g01_stress_gas", "Mean canopy temperature"),
            metric("max_tcan", "g01_stress_gas", "Maximum canopy temperature"),
            metric("seasonal_pn_sum", "g01_stress_gas", "Seasonal net photosynthesis sum"),
            metric("seasonal_pg_sum", "g01_stress_gas", "Seasonal gross photosynthesis sum"),
            metric("seasonal_respiration_sum", "g01_stress_gas", "Seasonal respiration sum"),
            metric("seasonal_et_demand_sum", "g01_stress_gas", "Seasonal ET demand sum"),
            metric("seasonal_et_supply_sum", "g01_stress_gas", "Seasonal ET supply sum"),
            metric("et_supply_demand_ratio", "g01_stress_gas", "ET supply to demand ratio"),
            metric("final_n_demand", "g01_nitrogen", "Final nitrogen demand"),
            metric("final_n_uptake", "g01_nitrogen", "Final nitrogen uptake"),
            metric("final_leaf_n", "g01_nitrogen", "Final leaf nitrogen"),
            metric("mean_leaf_n", "g01_nitrogen", "Mean leaf nitrogen"),
            metric("seasonal_n_uptake_sum", "g01_nitrogen", "Seasonal nitrogen uptake sum"),
            metric("seasonal_nitr_sum", "g01_nitrogen", "Seasonal nitrification sum"),
        ]
    )
    return rows


def g03_metrics():
    """返回 G03 土壤剖面扩展指标."""
    rows = []
    for column, stats in {
        "thNew": ["mean", "final", "min", "max"],
        "hNew": ["mean", "final", "min"],
        "Temp": ["mean", "final"],
        "NO3N": ["mean", "final"],
        "NH4N": ["mean", "final"],
        "CO2Conc": ["mean", "final"],
        "O2Conc": ["mean", "final"],
        "N2OConc": ["mean", "final"],
    }.items():
        for stat in stats:
            for depth_label, _, _ in DEPTH_RANGES:
                rows.append(metric(f"{stat}_{column}_{depth_label}", "g03_soil_profile"))
    return rows


def g04_metrics():
    """返回 G04 根系和吸收扩展指标."""
    rows = []
    for column in ["RMassM", "RMassY", "RDenM", "RDenY", "WaterSink", "NitSink", "GasSink"]:
        for stat in ["seasonal_sum", "seasonal_mean", "final_sum"]:
            for depth_label, _, _ in DEPTH_RANGES:
                rows.append(metric(f"{stat}_{column}_{depth_label}", "g04_root_uptake"))
    rows.extend(
        [
            metric("final_root_depth_max", "g04_root_uptake", "Final maximum root depth"),
            metric("final_root_depth_d95", "g04_root_uptake", "Final 95 percent root depth"),
            metric("root_density_0_20_share", "g04_root_uptake", "Final root density 0-20 cm share"),
            metric("water_sink_0_20_share", "g04_root_uptake", "Seasonal water sink 0-20 cm share"),
            metric("nit_sink_0_20_share", "g04_root_uptake", "Seasonal nitrogen sink 0-20 cm share"),
        ]
    )
    return rows


def g05_metrics():
    """返回 G05 水量平衡扩展指标."""
    names = [
        "seasonal_potential_soil_evap",
        "seasonal_actual_soil_evap",
        "soil_evap_deficit",
        "seasonal_rain",
        "seasonal_infiltration",
        "final_drainage",
        "final_runoff",
        "final_n_leach",
        "final_theta_avail",
        "actual_et",
        "potential_et",
        "et_deficit",
        "transpiration_fraction",
        "soil_evap_fraction",
        "infiltration_rain_ratio",
        "runoff_rain_ratio",
        "drainage_rain_ratio",
    ]
    return [metric(name, "g05_water_balance") for name in names]


def g06_metrics():
    """返回 G06 能量和辐射扩展指标."""
    rows = []
    for column in ["PARInt", "RADInt", "WATPOT", "WATACT", "WATRAT", "SoilEA", "WATTSM", "RNS", "RNC", "Flux"]:
        for stat in ["seasonal_sum", "seasonal_mean", "final"]:
            rows.append(metric(f"{stat}_{column}", "g06_energy_radiation"))
    return rows


def g07_metrics():
    """返回 G07 氮碳库扩展指标."""
    rows = []
    for column in ["Humus_N", "Humus_C", "Litter_N", "Litter_C", "Manure_N", "Manure_C", "Root_N", "Root_C"]:
        for stat in ["seasonal_mean", "final"]:
            rows.append(metric(f"{stat}_{column}", "g07_cn_pools"))
    return rows


def mass_balance_metrics():
    """返回水量和质量平衡文件扩展指标."""
    rows = []
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
        rows.append(metric(f"final_massbl_{column}", "mass_balance"))
    for column in ["Rainfall", "Inifiltration", "Runoff@end", "WaterStorage", "LeftDischarge", "RightDischarge"]:
        safe_name = column.replace("@", "_")
        rows.append(metric(f"final_runoff_balance_{safe_name}", "mass_balance"))
    return rows


EXTENDED_METRICS = (
    g01_metrics()
    + g03_metrics()
    + g04_metrics()
    + g05_metrics()
    + g06_metrics()
    + g07_metrics()
    + mass_balance_metrics()
)
ALL_METRICS = LEGACY_METRICS + [item for item in EXTENDED_METRICS if item["name"] not in {m["name"] for m in LEGACY_METRICS}]
METRIC_BY_NAME = {item["name"]: item for item in ALL_METRICS}


def legacy_metric_names():
    """返回旧版论文图指标名."""
    return [item["name"] for item in LEGACY_METRICS]


def morris_metric_names(include_legacy=True):
    """返回可用于 Morris 分析的数值指标名."""
    metrics = ALL_METRICS if include_legacy else EXTENDED_METRICS
    return [item["name"] for item in metrics if item.get("morris", True)]


def metric_group(metric_name):
    """返回指标分组."""
    return METRIC_BY_NAME.get(metric_name, {}).get("group", "other")


def metric_label(metric_name):
    """返回指标显示标签."""
    return METRIC_BY_NAME.get(metric_name, {}).get("label", metric_name)


def metric_metadata_rows():
    """返回指标元数据表记录."""
    return [
        {
            "metric": item["name"],
            "label": item.get("label", item["name"]),
            "group": item.get("group", "other"),
            "morris": bool(item.get("morris", True)),
        }
        for item in ALL_METRICS
    ]
