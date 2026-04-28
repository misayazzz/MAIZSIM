# MDEasternShore 玉米算例详细运行设置

## 算例来源与适用边界

本算例来源于仓库 README 中标注的 Maryland Eastern Shore 示例, 对应 Kim et al., 2012 的 MAIZSIM 论文: "Modeling temperature responses of leaf growth, development, and biomass in maize with MAIZSIM", Agronomy Journal 104:1523-1537, DOI: `10.2134/agronj2011.0321`.

论文中 MAIZSIM 与 2DSOIL 耦合, 用于模拟 Maryland Wye 和 Delaware Georgetown 的玉米田间数据. 其中 Delaware 包括 2006 和 2007 两个年份, Maryland Wye 包括 2006, 2007 和 2008 三个年份. 因此, 论文直接对应的是 5 个站点年份案例.

本地 `MD-DE inputs.xlsx` 将该案例整理为 ExcelInterface 输入格式, 并包含 7 个 run: `WYE06`, `WYE07`, `WYE08`, `DEL06`, `DEL07`, `DEL08`, `DEL09`. 其中 `WYE06`, `WYE07`, `WYE08`, `DEL06`, `DEL07` 与论文中的站点年份设置高度对应. `DEL08` 和 `DEL09` 不是论文中独立的 Delaware 2008 或 2009 田间年份, 而是在 `DEL07` 的同一地点, 同一天气, 同一模拟期和同一品种条件下替换土壤文件形成的派生土壤对照.

需要特别区分本地 Excel 输入和论文田间管理描述. 本地 `Irrig`, `Drip` 和 `DripNodes` 表没有实际灌溉事件, 因而本文后续按无显式灌溉输入解释这 7 个 run. 但 Kim et al., 2012 的论文材料方法中描述 Delaware 2006 和 2007 的氮肥随灌溉水施入. 因此, "本地算例无显式灌溉记录" 只适用于当前 ExcelInterface 输入文件, 不能外推为原论文 Delaware 田间试验没有灌溉.

综上, 本文后续分析的是仓库中 `MDEasternShore (maize)` 目录下的模型输入算例, 不是对 Kim et al., 2012 原始试验所有管理细节的完整复刻. 若用于论文复现或严谨对比, 应同时核对原论文的田间管理描述和本地 Excel 表中的运行设置.

本文档专门记录 `MDEasternShore (maize)` 算例的完整运行设置。

返回主文档: [Example input 算例总览与选型建议](Example输入算例总览与选型建议.md)

## 文件与总体设计

- 参数表: `MDEasternShore (maize)/MD-DE inputs.xlsx`
- 天气文件: `MDEasternShore (maize)/MD_Del_weather.csv`
- 水分参数文件: `MDEasternShore (maize)/Water.DAT`
- 水分时变边界文件: `MDEasternShore (maize)/WaterBound.DAT`
- 运行数: 7
- 地点: `Wye`, `Del`
- 天气尺度: 全部 `hourly`
- `Time` 表: 全部 `Daily=0`, `Hourly=1`, `WeatherDaily=0`, `WeatherHourly=1`
- 气体参数: 全部使用 `GasCO2Default`, `GasO2Default`, `GasN2ODefault`
- `Irrig` 和 `Drip` 表没有任何 `WYE06`, `WYE07`, `WYE08`, `DEL06`, `DEL07`, `DEL08`, `DEL09` 的专属灌溉记录, 因此这 7 个 run 可以按无显式灌溉的雨养运行理解。
- `DripNodes` 表的使用范围为 `A1:B2`, 但第 2 行是空共享字符串, 没有有效的 `ID` 或 `nodes`; 同时 `Drip` 表只有表头, 没有日期, 速率, 起止时间或 run ID, 因此不能视为启用了滴灌。

### Description 表完整设置

`Description` 表是 7 个 run 的主索引。它决定每个 run 使用哪个土壤文件, 天气文件名, 品种文件, 气候 ID, 氮文件和公共参数块。

| Run | Path | SoilFile | SoilName | WeatherFilename | Hybrid | VarietyFile | ClimateID | WeatherID | ClimateFile | Location | NitrogenFile |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `WYE06` | Wye06 | WyeSoil.soi | Wyesoil | WYE06.wea | PI34M91 | PI34M91.var | Wye | Wye | WyeClimate.dat | Wye | Wye.nit |
| `WYE07` | Wye07 | WyeSoil.soi | Wyesoil | WYE07.wea | PI34M91 | PI34M91.var | Wye | Wye | WyeClimate.dat | Wye | Wye.nit |
| `WYE08` | Wye08 | WyeSoil.soi | Wyesoil | WYE08.wea | P37y14 | P37y14.var | Wye | Wye | WyeClimate.dat | Wye | Wye.nit |
| `DEL06` | Del06 | WyeSoil.soi | Wyesoil | DEL06.wea | PI33B53 | PI33B53.var | Del | Del | WyeClimate.dat | Del | Del.nit |
| `DEL07` | Del07 | WyeSoil.soi | Wyesoil | DEL07.wea | PI33B53 | PI33B53.var | Del | Del | WyeClimate.dat | Del | Del.nit |
| `DEL08` | Del08 | Caswell.soi | Caswell | DEL07.wea | PI33B53 | PI33B53.var | Del | Del | WyeClimate.dat | Del | Del.nit |
| `DEL09` | Del09 | Piedmont.soi | Piedmont | DEL07.wea | PI33B53 | PI33B53.var | Del | Del | WyeClimate.dat | Del | Del.nit |

公共模块引用如下。7 个 run 在这些模块上完全一致, 差异不来自气体, 溶质, 生物学默认参数或水分运动默认参数。

| 适用 run | Solute | Biology | MulchGeo | MulchDecomp | Gas_File | Gas_CO2 | Gas_O2 | Gas_N2O | Tillage | WaterMovParam |
|---|---|---|---|---|---|---|---|---|---|---|
| 全部 7 个 run | NitrogenDefault | BiologyDefault | MulchGeo1 | MulchDecomp1 | GasID.gas | GasCO2Default | GasO2Default | GasN2ODefault | Default | WaterMovDefault |

### Init 表完整设置

`Init` 表给出每个 run 的种植密度, 坐标, 海拔, 作物开始日期, 播种日期, 作物结束日期, 自动灌溉开关, 种子位置和行距等设置。日期已经从 Excel serial date 转换为 `yyyy-mm-dd`。

| Run | Population(p/ha) | Lat | Long | altitude(m) | begin date | sowing | end | autoirrigated | autoIrrigAmt | RowAngle | Xseed | seedDepth | CEC | EOMult | NoSoilFile | OutputSoilFile | RowSpacing(cm) |
|---|---:|---:|---:|---:|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `WYE06` | 69000 | 39.02 | 76.55 | 50 | 2006-05-01 | 2006-05-08 | 2006-09-25 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `WYE07` | 69000 | 39.02 | 76.55 | 50 | 2007-05-05 | 2007-05-18 | 2007-09-18 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `WYE08` | 69000 | 39.02 | 76.55 | 50 | 2008-06-05 | 2008-06-09 | 2008-10-12 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `DEL06` | 73000 | 39.02 | 76.55 | 50 | 2006-04-08 | 2006-04-10 | 2006-10-11 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `DEL07` | 73000 | 39.02 | 76.55 | 50 | 2007-04-23 | 2007-04-30 | 2007-09-28 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `DEL08` | 73000 | 39.02 | 76.55 | 50 | 2007-04-23 | 2007-04-30 | 2007-09-28 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |
| `DEL09` | 73000 | 39.02 | 76.55 | 50 | 2007-04-23 | 2007-04-30 | 2007-09-28 | 0 | 空 | 0 | 0 | 8 | 0.65 | 0.5 | 0 | 1 | 76.2 |

注意:

- `autoirrigated=0`, 且 `autoIrrigAmt` 为空, 说明没有启用自动灌溉。
- Wye 组种植密度为 69000 p/ha, Del 组为 73000 p/ha。
- 7 个 run 的 `RowAngle=0`, `Xseed=0`, `seedDepth=8`, `CEC=0.65`, `EOMult=0.5`, `NoSoilFile=0`, `OutputSoilFile=1`, `RowSpacing=76.2` 完全一致。
- `Init` 表中 `Long=76.55`, 而 `Climate` 表中 `Longitude=-76.55`。本文保留表内原值, 不额外推断二者符号差异的原因。

### Time 表完整设置

`Time` 表给出模型运行时间窗, 时间步控制和天气读取尺度。7 个 run 的时间步参数完全一致, 差异主要是运行起止日期。

| Run | startDate | EndDate | dt | dtMin | DMul1 | DMul2 | Daily | Hourly | WeatherDaily | WeatherHourly | RunToEnd |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `WYE06` | 2006-04-28 | 2006-09-10 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `WYE07` | 2007-04-28 | 2007-09-30 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `WYE08` | 2008-05-28 | 2008-10-15 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `DEL06` | 2006-04-07 | 2006-10-18 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `DEL07` | 2007-04-15 | 2007-10-10 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `DEL08` | 2007-04-15 | 2007-10-10 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |
| `DEL09` | 2007-04-15 | 2007-10-10 | 0.0001 | 0.0000001 | 1.3 | 0.3 | 0 | 1 | 0 | 1 | 0 |

注意:

- `Daily=0`, `Hourly=1`, `WeatherDaily=0`, `WeatherHourly=1`, 说明所有运行都按小时天气读取和小时运行配置处理。
- `RunToEnd=0`, 说明参数表没有要求忽略给定结束日期一直运行到内部默认终点。
- `Time.startDate/EndDate` 与 `Init.begin date/sowing/end` 不是同一组日期字段。例如 `WYE06` 的 Time 窗口是 2006-04-28 到 2006-09-10, 但 Init 的 begin/sowing/end 是 2006-05-01, 2006-05-08, 2006-09-25。本文分别保留两套表内设置。

### 施肥, 残茬和耕作事件完整设置

`Fertilization` 表中 `amount` 为直接读取值, 未额外换算单位。WYE06 和 DEL06 各有一条 `amount=0` 的 residue/tillage 记录, 用 `date_residue`, `type`, `rate`, `Vertical Layers` 描述。

| Run | date | amount | depth | Litter_C | Litter_N | Manure_C | Manure_N | date_residue | type | rate | Vertical Layers | 说明 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| `WYE06` | 2006-05-01 | 0 | 5 | 0 | 0 | 0 | 0 | 2006-05-01 | t | 5 | 3 | residue/tillage 记录 |
| `WYE06` | 2006-05-10 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `WYE06` | 2006-06-14 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `WYE07` | 2007-05-10 | 65 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `WYE07` | 2007-06-14 | 65 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `WYE08` | 2008-06-06 | 65 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `WYE08` | 2008-07-06 | 65 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-04-09 | 0 | 0 | 0 | 0 | 0 | 0 | 2006-04-09 | t | 5 | 3 | residue/tillage 记录 |
| `DEL06` | 2006-04-20 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-05-24 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-06-10 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-06-24 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-07-15 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL06` | 2006-08-15 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-05-10 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-05-24 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-06-10 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-06-24 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-07-15 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |
| `DEL07` | 2007-08-15 | 60 | 5 | 0 | 0 | 0 | 0 | 空 | 空 | 空 | 空 | 施肥 |

按 run 汇总:

| Run | Fertilization 表记录数 | 施肥 amount 合计 | residue/tillage 记录 | 说明 |
|---|---:|---:|---|---|
| `WYE06` | 3 | 120 | 1 条, 2006-05-01 | 两次实际施肥, 各 60 |
| `WYE07` | 2 | 130 | 无 | 两次施肥, 各 65 |
| `WYE08` | 2 | 130 | 无 | 两次施肥, 各 65 |
| `DEL06` | 7 | 360 | 1 条, 2006-04-09 | 六次实际施肥, 各 60 |
| `DEL07` | 6 | 360 | 无 | 六次施肥, 各 60 |
| `DEL08` | 0 | 0 | 无 | 当前表中没有对应施肥行 |
| `DEL09` | 0 | 0 | 无 | 当前表中没有对应施肥行 |

### Tillage, GridRatio 和边界设置

`Description` 表中 7 个 run 都引用 `Tillage=Default`。`Tillage` 表只有一行:

| ID | Till(1/0) | DaysBeforePlanting | Depth |
|---|---:|---:|---:|
| Default | 0 | 4 | 15 |

因此从 `Tillage` 表看, 默认耕作开关为 0。需要注意, `Fertilization` 表仍有 `WYE06` 和 `DEL06` 的 residue/tillage 事件记录; 这两类字段来自不同表, 本文分别保留原始设置。

`GridRatio` 表按土壤文件设置网格比例, 种植深度, 根系横向限制和上下边界。三个土壤文件的 GridRatio 设置完全相同。

| soilfile | SR1 | IR1 | SR2 | IR2 | PlantingDepth | XLimitRoot | BottomBC | GasBCTop | GasBCBottom | InitRtMass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WyeSoil.soi | 1.6 | 0.05 | 2.1 | 2 | 10 | 23 | -2 | -4 | 1 | 0 |
| Caswell.soi | 1.6 | 0.05 | 2.1 | 2 | 10 | 23 | -2 | -4 | 1 | 0 |
| Piedmont.soi | 1.6 | 0.05 | 2.1 | 2 | 10 | 23 | -2 | -4 | 1 | 0 |

### 共同模块默认参数

这些设置由 7 个 run 共同引用, 因此不构成运行间差异。

`Biology` 表:

| ID | dThH | dThL | es | Th_m | tb | QT | dThD | Th_d |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BiologyDefault | 0.1 | 0.08 | 0.6 | 1 | 25 | 3 | 0.1 | 2 |

`Gas` 表:

| ID | EPSI | bTort | Diffusion_Coeff(cm2/day) |
|---|---:|---:|---:|
| GasCO2Default | 1 | 0.65 | 11920 |
| GasO2Default | 1 | 0.65 | 15400 |
| GasN2ODefault | 1 | 0.65 | 12355.2 |

`Solute` 表:

| ID | EPSI | lUPW | CourMax | Diffusion_Coeff |
|---|---:|---:|---:|---:|
| NitrogenDefault | 0.8 | 0 | 0.5 | 1.2 |

`WaterMovParam` 表:

| ID | MaxIt | TolTh | TolH | hCritA | hCritS | DtMx | htab1 | htabN | EPSI.Heat | EPSI.Solute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WaterMovDefault | 20 | 0.01 | 0.05 | -100000 | 0.001 | 0.02 | 0.001 | 1000 | 0.5 | 0.5 |

目录内 `Water.DAT` 中的水分运动参数与 Excel `WaterMovParam` 表大部分一致, 但 `hCritS` 不一致:

| 来源 | MaxIt | TolTh | TolH | hCritA | hCritS | DtMx | htab1 | htabN | EPSI.Heat | EPSI.Solute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Excel `WaterMovParam` | 20 | 0.01 | 0.05 | -100000 | 0.001 | 0.02 | 0.001 | 1000 | 0.5 | 0.5 |
| `MDEasternShore (maize)/Water.DAT` | 20 | 0.01 | 0.05 | -100000 | 1.0E+010 | 0.02 | 0.001 | 1000 | 0.5 | 0.5 |

目录内还包含 `WaterBound.DAT`, 其内容是水分运动的时变边界示例或已生成文件:

| Time | Node | VarB |
|---:|---:|---:|
| 252.542 | 6 | 0 |
| 252.542 | 7 | 0 |
| 252.542 | 12 | 0 |
| 252.542 | 13 | 0 |

如果以 Excel 重新生成模型输入, 应以工作簿中引用的表为准; 如果直接复用目录内 `.DAT` 文件, 则需要注意 `Water.DAT` 的 `hCritS` 和 Excel 表不同, 且 `WaterBound.DAT` 中存在节点 6, 7, 12, 13 的边界记录。本文不在未运行模型的情况下判断 `.DAT` 是否就是最终运行文件。

`MulchGeo` 表:

| ID | Min_Hori_Size | Diffusion_Restriction | LongWaveRadiationCtrl | Decomposition_ctrl | DeltaRshort | DeltaRlong | Omega | epsilon_mulch | alpha_mulch | MaxStep in Picard Iteration | Tolerance_head | rho_mulch | pore_space | MaxPondingDepth |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MulchGeo1 | 2 | 0 | 0 | 1 | 0.3 | 0.3 | 0.6 | 1 | 0.3 | 10 | 0.01 | 600000 | 0.95 | 5 |

`MulchDecomp` 表:

| ID | ContactFraction | alpha_feeding | CARB MASS | CELL MASS | LIGN MASS | CARB N MASS | CELL N MASS | LIGN N MASS | CARB Decomp | CELL Decomp | LIGN Decomp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MulchDecomp1 | 0.6 | 0.1 | 0.2 | 0.7 | 0.1 | 0.08 | 0.01 | 0.01 | 0.425 | 0.24 | 0.0228 |

### 灌溉和滴灌表原始状态

- `Irrig` 表没有任何 run ID, 日期, 灌溉量, 深度, 起止小时等有效运行记录。该表右侧只保留灌溉类型说明, 包括 `flood_H`, `flood_R`, `Sprinkler`。
- `Drip` 表只有表头 `ID`, `Date`, `rate(cm/hr)`, `StartTime`, `StopTime`, `Distance`, 没有任何数据行。
- `DripNodes` 表只有表头 `ID`, `nodes`, 没有任何有效数据行。
- 因此这 7 个 run 既没有普通灌溉记录, 也没有滴灌记录, 也没有自动灌溉。

### 气候与天气设置

`Climate` 表中有两个气候 ID, 但两个地点的经纬度和大气参数在表内写成一致:

| ClimateID | Location | Latitude | Longitude | DailyBulb | DailyWind | RelHumid | DailyCO2 | AvgWind | AvgRainRate | AvgCO2 | Altitude |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Wye` | Wye | 39.02 | -76.55 | 0 | 0 | 1 | 0 | 8 | 3 | 380 | 50 |
| `Del` | Del | 39.02 | -76.55 | 0 | 0 | 1 | 0 | 8 | 3 | 380 | 50 |

`Climate` 表还包含以下公共列, 两个 `ClimateID` 的数值完全一致:

| 适用 ClimateID | RainIntensity | DailyConc | Furrow | Bsolar | Btemp | Atemp | Erain | BWInd | BIR | ChemCOnc | RH |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Wye`, `Del` | 0 | 0 | 0 | 1000000 | 1 | 0 | 0.1 | 1 | 1 | 0 | 0 |

`Weather` 表中有 5 行天气映射, 都来自同一个 CSV:

| ClimateID | WeatherID | Source_name | Source | Time |
|---|---|---|---|---|
| `Wye` | `Wye` | `MD_Del_Weather.csv` | file | hourly |
| `Wye` | `Wye` | `MD_Del_Weather.csv` | file | hourly |
| `Wye` | `Wye` | `MD_Del_Weather.csv` | file | hourly |
| `Del` | `Del` | `MD_Del_Weather.csv` | file | hourly |
| `Del` | `Del` | `MD_Del_Weather.csv` | file | hourly |

这说明参数表把 Wye 和 Del 都作为小时天气运行处理。`Description` 表中每个 run 会生成自己的 `WeatherFilename`, 例如 `WYE06.wea`, `DEL06.wea`, `DEL07.wea`; 但这些 `.wea` 文件的来源均是 `MD_Del_Weather.csv` 中对应的 `WeatherID`。

需要注意文件名大小写: 目录中文件名是 `MD_Del_weather.csv`, 而 `Weather` 表的 `Source_name` 写作 `MD_Del_Weather.csv`。在 Windows 下通常不影响读取, 但在大小写敏感文件系统上复现时需要统一。

天气 CSV 的小时行完整性如下:

| WeatherID | 日期范围 | 行数 | 覆盖天数 | 行数完整性 | 累计 rain |
|---|---|---:|---:|---|---:|
| `Wye` | 2006-01-01 到 2008-12-31 | 26304 | 1096 | 每天 24 行, 覆盖完整 | 3264.7 |
| `Del` | 2006-04-04 到 2007-12-31 | 15267 | 637 | `2006-04-05` 和 `2006-04-06` 各 13 行, `2007-01-01` 有 25 行 | 3796.0 |

上述 Del 的小时行异常不落在 7 个 run 的核心模拟窗口开始之后的有效天气缺口内, 但它说明原始 CSV 不是严格每天 24 行的完全规整小时序列。

### 降雨情况

`MD_Del_weather.csv` 的 `rain` 列显示, 该案例不需要额外灌溉的一个重要原因是天气文件本身降雨较多, 尤其是 Del 地点。以下统计直接对 `rain` 列按数值求和, 若按模型常规将 `rain` 理解为 mm, 则数值单位为 mm。

| 站点 | 年份 | CSV 行数 | 年内或文件内累计降雨 | 有雨小时数 | 最大小时雨量 |
|---|---:|---:|---:|---:|---:|
| Del | 2006 | 6506 | 1657.3 | 436 | 5.0 |
| Del | 2007 | 8761 | 2138.7 | 921 | 32.5 |
| Wye | 2006 | 8760 | 1245.4 | 555 | 30.2 |
| Wye | 2007 | 8760 | 932.9 | 545 | 16.8 |
| Wye | 2008 | 8784 | 1086.4 | 617 | 29.0 |

需要注意, Del 2006 在 CSV 中不是完整自然年, 文件从 2006-04-04 左右开始, 但 4 月到 12 月已经累计到 1657.3。

按 7 个 run 的模拟期统计:

| Run | 地点 | 模拟期 | 天数 | 期内降雨 | 有雨天数 | 日雨量大于等于 10 的天数 | 日雨量大于等于 25 的天数 | 最大日雨量 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `WYE06` | Wye | 2006-04-28 到 2006-09-10 | 136 | 626.9 | 46 | 16 | 11 | 56.4 |
| `WYE07` | Wye | 2007-04-28 到 2007-09-30 | 156 | 275.3 | 42 | 12 | 3 | 30.0 |
| `WYE08` | Wye | 2008-05-28 到 2008-10-15 | 141 | 411.0 | 50 | 12 | 5 | 70.4 |
| `DEL06` | Del | 2006-04-07 到 2006-10-18 | 195 | 1371.1 | 91 | 29 | 17 | 120.0 |
| `DEL07` | Del | 2007-04-15 到 2007-10-10 | 179 | 1196.6 | 105 | 42 | 25 | 123.7 |
| `DEL08` | Del | 2007-04-15 到 2007-10-10 | 179 | 1196.6 | 105 | 42 | 25 | 123.7 |
| `DEL09` | Del | 2007-04-15 到 2007-10-10 | 179 | 1196.6 | 105 | 42 | 25 | 123.7 |

降雨判断:

- `DEL06`, `DEL07`, `DEL08`, `DEL09` 的模拟期降雨都非常高, 超过 1190。
- `WYE06` 也偏高, 模拟期约 627。
- `WYE07` 相对较少, 模拟期约 276, 是 7 个运行中最干的一组。
- `WYE08` 处于中间水平, 模拟期约 412。
- 最大日雨量很集中, 例如 Del 在 2007-04-15 为 123.7, Del 在 2006-06-25 和 2006-09-01 都为 120.0, Wye 在 2008-06-04 为 70.4。

### 逐运行明细

| Run | Path | 地点 | WeatherID | WeatherFilename | 品种 | 土壤名 | 土壤文件 | NitrogenFile | 起止日期 | 施肥安排 | 灌溉 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `WYE06` | Wye06 | Wye | Wye | WYE06.wea | PI34M91 | Wyesoil | WyeSoil.soi | Wye.nit | 2006-04-28 到 2006-09-10 | 3 行, `amount` 合计 120, 2006-05-01 有一行 `amount=0` 的 residue/tillage 记录, 2006-05-10 和 2006-06-14 各 60 | 无 |
| `WYE07` | Wye07 | Wye | Wye | WYE07.wea | PI34M91 | Wyesoil | WyeSoil.soi | Wye.nit | 2007-04-28 到 2007-09-30 | 2 行, 2007-05-10 和 2007-06-14 各 65, 合计 130 | 无 |
| `WYE08` | Wye08 | Wye | Wye | WYE08.wea | P37y14 | Wyesoil | WyeSoil.soi | Wye.nit | 2008-05-28 到 2008-10-15 | 2 行, 2008-06-06 和 2008-07-06 各 65, 合计 130 | 无 |
| `DEL06` | Del06 | Del | Del | DEL06.wea | PI33B53 | Wyesoil | WyeSoil.soi | Del.nit | 2006-04-07 到 2006-10-18 | 7 行, `amount` 合计 360, 2006-04-09 有一行 `amount=0` 的 residue/tillage 记录, 2006-04-20, 2006-05-24, 2006-06-10, 2006-06-24, 2006-07-15, 2006-08-15 各 60 | 无 |
| `DEL07` | Del07 | Del | Del | DEL07.wea | PI33B53 | Wyesoil | WyeSoil.soi | Del.nit | 2007-04-15 到 2007-10-10 | 6 行, 2007-05-10, 2007-05-24, 2007-06-10, 2007-06-24, 2007-07-15, 2007-08-15 各 60, 合计 360 | 无 |
| `DEL08` | Del08 | Del | Del | DEL07.wea | PI33B53 | Caswell | Caswell.soi | Del.nit | 2007-04-15 到 2007-10-10 | 无施肥行 | 无 |
| `DEL09` | Del09 | Del | Del | DEL07.wea | PI33B53 | Piedmont | Piedmont.soi | Del.nit | 2007-04-15 到 2007-10-10 | 无施肥行 | 无 |

### 品种差异

`Variety` 表有 3 个品种。除 `JuvenileLeaves` 外, 表中这些品种的其余主要生长参数相同。

| Hybrid | 用在哪些 run | JuvenileLeaves | DaylengthSensitive | Rmax_LTAR | Rmax_LTIR | PhyllFrmTassel | StayGreen |
|---|---|---:|---:|---:|---:|---:|---:|
| `PI34M91` | `WYE06`, `WYE07` | 18 | 1 | 0.53 | 0.978 | 3 | 4.5 |
| `P37y14` | `WYE08` | 16 | 1 | 0.53 | 0.978 | 3 | 4.5 |
| `PI33B53` | `DEL06`, `DEL07`, `DEL08`, `DEL09` | 19 | 1 | 0.53 | 0.978 | 3 | 4.5 |

### 土壤设置

本组实际使用 3 个土壤文件, 共 12 个土层记录:

| 土壤文件 | 用在哪些 run | 土层数 | 深度范围 | 质地概括 | 在本组中的作用 |
|---|---|---:|---|---|---|
| `WyeSoil.soi` | `WYE06`, `WYE07`, `WYE08`, `DEL06`, `DEL07` | 4 | 20 到 145 cm | 高砂土, 砂含量 75 到 90, 粘粒 0 到 6 | Wye 和 Del 前 5 个运行的主土壤 |
| `Caswell.soi` | `DEL08` | 4 | 23 到 203 cm | 上层高砂, 深层粘粒升高到 23 | Del 2007 窗口下的土壤替换对照 |
| `Piedmont.soi` | `DEL09` | 4 | 18 到 203 cm | 粘粒明显较高, 第二层粘粒 55 | Del 2007 窗口下的更粘重土壤替换对照 |

土壤剖面关键字段如下:

| SoilFile | Bottom depth | OM | NO3 | NH4 | HNew | Sand | Silt | Clay | BD | TH33 | TH1500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WyeSoil.soi | 20 | 0.0025 | 9.5 | 0 | -100 | 75 | 20 | 5 | 1.26 | -1 | -1 |
| WyeSoil.soi | 35 | 0.0025 | 5.1 | 0 | -100 | 80 | 15 | 5 | 1.33 | -1 | -1 |
| WyeSoil.soi | 75 | 0.0025 | 6.1 | 0 | -100 | 85 | 14 | 6 | 1.36 | -1 | -1 |
| WyeSoil.soi | 145 | 0.00125 | 5.9 | 0 | -100 | 90 | 10 | 0 | 1.36 | -1 | -1 |
| Caswell.soi | 23 | 0.015 | 25 | 4 | -200 | 83 | 11 | 6 | 1.392 | 0.158 | -1 |
| Caswell.soi | 30 | 0.0025 | 25 | 4 | -200 | 85 | 11 | 4 | 1.43 | 0.17 | -1 |
| Caswell.soi | 157 | 0.0025 | 25 | 4 | -200 | 60 | 17 | 23 | 1.41 | 0.24 | -1 |
| Caswell.soi | 203 | 0.0025 | 25 | 4 | -200 | 60 | 17 | 23 | 1.382 | 0.238 | -1 |
| Piedmont.soi | 18 | 0.0125 | 25 | 4 | -200 | 33.5 | 36.5 | 30 | 1.128 | 0.322 | -1 |
| Piedmont.soi | 147 | 0.0025 | 25 | 4 | -200 | 17.1 | 27.9 | 55 | 0.99 | 0.39 | -1 |
| Piedmont.soi | 185 | 0.0025 | 25 | 4 | -200 | 33.3 | 31.7 | 35 | 1.221 | 0.329 | -1 |
| Piedmont.soi | 203 | 0.0025 | 25 | 4 | -200 | 38.5 | 36.5 | 25 | 1.262 | 0.288 | -1 |

土壤表中还包含初始类型, 初始温度和气体浓度。所有土层的 `Humus_C=-1`, `Humus_N=-1`, `Litter_C=0`, `Litter_N=0`, `Manure_C=0`, `Manure_N=0`。

| 土壤文件 | 适用土层 | Init Type | Tmpr | CO2(ppm) | O2(ppm) | N2O(ppm) |
|---|---|---|---:|---:|---:|---:|
| WyeSoil.soi | 20, 35, 75, 145 | m | 23 | 400 | 206000 | 0 |
| Caswell.soi | 23, 30, 157, 203 | m | 25 | 400 | 206000 | 0 |
| Piedmont.soi | 18, 147, 185, 203 | m | 25 | 400 | 206000 | 0 |

`WyeSoil.soi` 的土壤过程参数按层如下。这里直接记录 `Soil` 表中的原值, 不额外解释每个参数在模型内部的具体方程含义。

| Bottom depth | kh | kL | km | kn | kd | fe | fh | r0 | rL | rm | fa | nq | cs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.00007 | 0.035 | 0.07 | 0.2 | 0.0000001 | 0.6 | 0.2 | 10 | 50 | 10 | 0.1 | 8 | 0.00001 |
| 35 | 0.00007 | 0.035 | 0.07 | 0.2 | 0.0000001 | 0.6 | 0.2 | 10 | 50 | 10 | 0.1 | 8 | 0.00001 |
| 75 | 0.00007 | 0.035 | 0.07 | 0.2 | 0.0000001 | 0.6 | 0.2 | 10 | 50 | 10 | 0.1 | 8 | 0.00001 |
| 145 | 0.00007 | 0.035 | 0.07 | 0.2 | 0.0000001 | 0.6 | 0.2 | 10 | 50 | 10 | 0.1 | 8 | 0.00001 |

`WyeSoil.soi` 的水分特征和传导相关字段按层如下:

| Bottom depth | thr | ths | tha | th | alfa | n | ks | kk | thk |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.051 | 0.396 | 0.051 | 0.396 | 0.032 | 1.85 | 120 | 120 | 0.396 |
| 35 | 0.051 | 0.43 | 0.051 | 0.43 | 0.042 | 1.75 | 86 | 86 | 0.43 |
| 75 | 0.01 | 0.39 | 0.01 | 0.39 | 0.019 | 1.6 | 60 | 30 | 0.39 |
| 145 | 0.01 | 0.3 | 0.01 | 0.3 | 0.019 | 1.4 | 25 | 25 | 0.3 |

`Caswell.soi` 和 `Piedmont.soi` 的附加字段在 8 个土层中相同。表内原值如下:

| 适用土壤与土层 | kh | kL | km | kn | kd | fe | fh | r0 | rL | rm | fa | nq | cs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Caswell 23/30/157/203, Piedmont 18/147/185/203 | -1 | -1 | -1 | -1 | -1 | -1 | -1 | -1 | -1 | 0.00007 | 0.035 | 0.07 | 0.2 |

| 适用土壤与土层 | thr | ths | tha | th | alfa | n | ks | kk | thk |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Caswell 23/30/157/203, Piedmont 18/147/185/203 | 0.00001 | 0.6 | 0.2 | 10 | 50 | 10 | 0.1 | 8 | 0.00001 |

注意: `Caswell.soi` 和 `Piedmont.soi` 中 `kh` 到 `rL` 这些字段为 `-1`, 可能代表缺省或特殊输入标记。本文只说明表内原值, 不在未运行模型的情况下推断模型如何解释这些 `-1`。

土壤对比结论:

- `WyeSoil.soi` 极偏砂, 尤其 75 到 145 cm 深度砂含量达到 85 到 90, 粘粒最低到 0。它更容易体现排水快, 保水能力低的土壤背景。
- `Caswell.soi` 上层仍偏砂, 但 30 cm 以下砂含量降为 60, 粘粒升到 23, 比 `WyeSoil.soi` 更细。
- `Piedmont.soi` 是三者中最粘重的土壤, 第二层 18 到 147 cm 的粘粒为 55, 砂含量只有 17.1。`DEL09` 因此是 Del 2007 气象条件下的高粘土对照。
- `DEL07`, `DEL08`, `DEL09` 使用同一地点, 同一天气 ID, 同一模拟期和同一品种, 但换了土壤文件; 因此这三组最适合比较土壤质地差异对模型输出的影响。

### 运行间主要修改点

- `WYE06`, `WYE07`, `WYE08` 是 Wye 地点的逐年运行。三者都使用 `WyeSoil.soi`, 无灌溉, 小时天气。主要变化是年份, 模拟窗口, 天气文件名, 品种和施肥日期。
- `WYE06` 和 `WYE07` 的品种相同, 均为 `PI34M91`; `WYE08` 改为 `P37y14`。因此 Wye 组不是严格的单一年份天气对照, 还包含品种变化。
- `DEL06` 和 `DEL07` 是 Del 地点的两个年份运行, 都用 `WyeSoil.soi`, 品种 `PI33B53`, 无灌溉。它们主要比较 2006 和 2007 天气, 模拟窗口和施肥日期。
- `DEL07`, `DEL08`, `DEL09` 共享同一模拟期 2007-04-15 到 2007-10-10, 共享 `WeatherID=Del`, 共享 `WeatherFilename=DEL07.wea`, 共享品种 `PI33B53`, 但土壤分别为 `WyeSoil.soi`, `Caswell.soi`, `Piedmont.soi`。这三组是最明确的土壤替换对照。
- `DEL08` 和 `DEL09` 在 `Fertilization` 表中没有对应施肥行。运行前如果希望这两组与 `DEL07` 只比较土壤, 需要确认是否应该复用 `DEL07` 的施肥方案; 当前参数表并没有这样写。
- 7 组 run 都没有显式灌溉。水分输入来自小时天气文件中的降雨, 而 Del 组生育期降雨非常高, 这与无灌溉设置是匹配的。

