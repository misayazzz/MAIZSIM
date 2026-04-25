# Example input 算例运行情况详细说明

本文档根据 `Example input` 目录下各算例的 Excel 参数表和天气 CSV 文件整理。整理时只读取输入文件, 没有运行模型, 也没有生成或修改任何模型输入目录。

数据来源主要包括:

- `Description` 表: 每个 run 的主索引, 包括 `ID`, `weatherID`, `hybrid`, `SoilFile`, `path`, `Gas_CO2`, `Gas_O2`, `I_type`, `year` 等字段。
- `Weather` 表: 每个天气 ID 对应的 CSV 来源和天气尺度, 即 `daily` 或 `hourly`。
- `Time` 表: 每个 run 的起止日期, 以及 `Daily`, `Hourly`, `WeatherDaily`, `WeatherHourly` 设置。
- `Fertilization` 表: 按 run 汇总施肥事件数量, `amount` 字段合计, 日期范围。
- `Irrig`, `Irrig_data`, `Irrig (2)` 表: 按 run 或处理汇总灌溉记录。
- `Climate`, `Variety`, `Soil`, `Gas` 表: 地点, 品种, 土壤文件和气体扩散参数。

注意事项:

- 文中的日期已经从 Excel serial date 转换为 `yyyy-mm-dd`。
- 文中的施肥总量是 `Fertilization.amount` 字段的直接合计, 未额外推断单位。
- 文中的灌溉合计是对应灌溉表中 `amount (mm/day)` 或同名数值字段的直接合计, 未额外换算。
- `Daily/Hourly` 和 `WeatherDaily/WeatherHourly` 均直接来自 `Time` 表。本文仅说明这些字段的配置状态, 不额外解释模型内部数值积分含义。
- `Weather` 表中的天气 ID 有时多于 `Description` 实际使用的天气 ID。本文会分别说明“文件中可用”和“当前运行实际接入”的内容。

## 数据同化研究选型建议

如果研究目标是“基于数据同化分析二维作物模型”, 需要先区分两个问题:

- 本目录里的文件主要是模型输入算例, 不是完整的数据同化观测数据集。整理时没有发现独立的 LAI, 生物量, 产量, 土壤水分, 冠层高度, 物候期或遥感观测表。
- 因此, 这些算例更适合作为“搭建同化框架, 设计合成观测实验, 或接入外部观测数据”的模型底座, 不能直接等同于现成的真实观测同化数据集。
- 如果没有外部实测数据, 最稳妥的第一步是做合成观测或孪生试验。即先用一个基准运行生成“真值”, 再向关键状态变量加入观测误差, 用集合卡尔曼滤波, 粒子滤波, 变分同化或参数反演方法检验同化流程。
- 对 Maizsim/2DSOIL 这类作物-土壤二维模型, 最适合作为同化变量的通常是土壤含水量剖面, LAI 或冠层状态, 地上部生物量, 产量, 物候日期, 蒸散或冠层温度。当前示例输入本身只提供模型驱动和参数, 不提供这些观测序列。

### 总体推荐排序

| 排名 | 算例目录 | 推荐程度 | 最适合的同化研究方向 | 不建议作为主算例的原因或风险 |
|---:|---|---|---|---|
| 1 | `MDEasternShore (maize)` | 最推荐 | 无灌溉条件下的土壤水分, 作物生长状态, 土壤参数和天气驱动响应同化 | 需要外部观测或合成观测。`DEL08` 和 `DEL09` 没有施肥记录, 若研究生长或产量需要谨慎处理。 |
| 2 | `Kansas` | 推荐作为第二阶段 | 旱作/灌溉对比, 水分管理, 灌溉处理下的土壤水分或作物状态同化 | 地点多, 天气尺度混合, 管理差异更复杂, 不如 `MDEasternShore (maize)` 适合作为第一套框架。 |
| 3 | `AgmipET2` | 推荐作为扩展验证 | 多年份, 多水分处理, AgMIP 背景下的模型泛化和水分管理同化 | 年份, 品种, 土壤, 施肥和灌溉系统同时变化, 初期解释成本高。 |
| 4 | `CO2_Respiration_CaseStudy1` | 条件推荐 | 土壤 CO2, 土壤呼吸, 气体扩散或土壤参数反演 | 主题偏土壤气体和呼吸参数敏感性, 不适合作为一般玉米生长同化主算例。 |
| 5 | `Tropical_Temperate_Study` | 适合作为泛化检验 | 热带/温带地点差异, 年际气候差异, 跨气候带参数可迁移性 | 日天气, 无明显水分处理梯度, 更适合在同化方法稳定后做跨气候验证。 |
| 6 | `CO2_Respiration_CaseStudy2` | 只建议用于调试 | 单运行 CO2/土壤呼吸模块检查 | 只有 1 个运行, 可比性和研究设计空间太小。 |

### 各算例的推荐用法和后续建议

| 算例目录 | 推荐结论 | 最推荐的切入方式 | 后续建议 |
|---|---|---|---|
| `MDEasternShore (maize)` | 作为数据同化研究的首选主算例。它运行数量少, 全部是小时天气, 没有显式灌溉, 管理扰动相对少, 而且 `DEL07`, `DEL08`, `DEL09` 构成清晰的土壤替换对照。 | 第一阶段选 `WYE07` 或 `DEL07` 做单运行同化流程验证。第二阶段使用 `DEL07`, `DEL08`, `DEL09` 做土壤差异和土壤水分状态同化。第三阶段再加入 `WYE06`, `WYE08`, `DEL06` 检查跨年和跨地点稳定性。 | 优先同化土壤水分剖面, LAI, 生物量或产量。若没有实测数据, 先做合成观测。若研究生长和产量, 必须先处理 `DEL08` 和 `DEL09` 没有施肥记录的问题, 否则土壤差异会和施肥差异混杂。Del 组降雨很高, 适合研究湿润条件下土壤水分和排水过程, 不适合作为干旱胁迫主案例。 |
| `Kansas` | 适合作为第二推荐算例, 尤其适合把同化研究从无灌溉场景扩展到旱作/灌溉和多地点场景。 | 先选一个地点和一个处理对照, 例如 Ashland 的旱作/灌溉小时天气组, 或显式灌溉运行 `ASHD06IR`, `CULI05IR`, `MOSI06IR`。不要一开始同时使用所有 13 个运行。 | 适合研究土壤水分同化对灌溉处理识别, 水分胁迫估计和产量预测的改进。后续可以比较“只同化作物状态”, “只同化土壤水分”, “联合同化作物状态和土壤水分”的效果。需要注意 Kansas 同时包含日天气和小时天气, 同化时间步和观测时间尺度要单独统一。 |
| `AgmipET2` | 适合作为方法成熟后的扩展算例, 不建议作为第一套同化主算例。它的优势是 AgMIP 背景, 多年份, 多水分处理和灌溉系统丰富。 | 先用 Mead 成对组比较 `MeadNE2` 灌溉和 `MeadNE3` 雨养, 因为它们年份成对且结构清楚。待流程稳定后再分析 Bush 的 `NW-MESA-75%`, `SW-MESA-100%`, `NE-SDI-100%`, `SE-SDI-100%` 灌溉系统差异。 | 适合研究同化方法在多年份和多水分管理下的泛化能力。后续可以把 `MDEasternShore (maize)` 得到的同化框架迁移到 `AgmipET2`, 检查不同年份和不同灌溉制度下参数是否需要重新校准。需要谨慎区分年份, 品种, 土壤文件, 施肥和灌溉制度的共同变化。 |
| `CO2_Respiration_CaseStudy1` | 只在研究重点明确指向土壤 CO2, 土壤呼吸, 气体扩散或土壤参数反演时推荐。它不适合作为一般作物生长同化主算例。 | 以 `OCA2003_Run1` 或中心参数运行为基准, 再利用 `bTort`, `fe`, `kh`, `kL`, `fh`, `rL`, `r0` 的单参数和双参数组合做参数可辨识性分析。 | 后续应把研究问题写成“利用 CO2/呼吸或土壤气体观测反演气体扩散和土壤呼吸参数”, 而不是泛泛的玉米产量同化。若没有 CO2 或土壤呼吸观测, 可先做合成观测实验, 检查哪些参数能被观测约束, 哪些参数存在等效性或不可辨识问题。 |
| `CO2_Respiration_CaseStudy2` | 不建议作为正式主算例, 但适合做最小化调试。 | 用 `SCA2004_Run1` 检查 Excel 接口, 天气读取, 单运行生成输入, CO2/气体模块是否能执行。 | 后续只把它作为调试用例或补充说明。由于只有 1 个运行, 无法支撑跨年份, 跨地点, 多处理或参数组合的同化结论。 |
| `Tropical_Temperate_Study` | 适合作为同化方法稳定后的跨气候带泛化测试, 不建议作为第一主算例。 | 先在 Rahuri 或 Marshall 内部做单地点多年同化验证, 再比较 Rahuri 热带组和 Marshall 温带组的参数迁移性。 | 后续适合研究“同一同化策略能否跨热带和温带气候保持有效”。建议把它放在 `MDEasternShore (maize)` 或 `Kansas` 之后使用。由于是日天气且无明确灌溉处理, 更适合同化 LAI, 生物量, 产量和物候, 而不是高频土壤水分或灌溉决策。 |

### 首选研究路线

建议采用由简单到复杂的路线:

1. 用 `MDEasternShore (maize)` 的 `WYE07` 或 `DEL07` 做单运行合成观测同化, 先验证同化程序, 观测算子, 误差设定和模型重启流程。
2. 用 `MDEasternShore (maize)` 的 `DEL07`, `DEL08`, `DEL09` 做土壤差异实验, 分析同化能否修正土壤水分状态或约束土壤参数。
3. 用 `MDEasternShore (maize)` 的 Wye 和 Del 多年份运行做跨年, 跨地点检验。
4. 如果研究问题扩展到灌溉和水分管理, 再转向 `Kansas` 或 `AgmipET2`。
5. 如果研究问题扩展到 CO2 或土壤呼吸, 再转向 `CO2_Respiration_CaseStudy1`。
6. 如果研究问题扩展到气候带泛化, 再转向 `Tropical_Temperate_Study`。

## 算例目的摘要

| 算例目录 | 目的总结 | 适合重点查看的差异 |
|---|---|---|
| `AgmipET2` | 该算例用于复现或测试 AgMIP ET2 相关玉米模拟输入, 重点覆盖两个地点和多种水分管理条件。它把 Mead 的灌溉/雨养对照与 Bush 的不同灌溉系统处理放在同一套参数表中, 适合检查 Excel 接口能否批量生成多年份, 多品种, 多水分处理的 Maizsim 输入。 | 地点 `Mead` 与 `Bush`, `MeadNE2` 与 `MeadNE3`, `M_75`, `M_100`, `S_100`, 年份, 品种, 施肥和灌溉记录。 |
| `CO2_Respiration_CaseStudy1` | 该算例用于 CO2/土壤呼吸相关参数敏感性测试。虽然 `Weather` 表中列出了 CO2, 温度和降雨扰动天气 ID, 但当前 87 个运行实际都接入 OCA 日天气, 主要目的是在同一地点和基本相同作物管理下系统改变气体扩散参数和土壤参数, 观察土壤 CO2 或呼吸过程对参数变化的响应。 | `Gas_CO2/Gas_O2` 的 `bTort`, 土壤参数 `fe`, `kh`, `kL`, `fh`, `rL`, `r0`, 以及 `kL x fe` 双参数组合。 |
| `CO2_Respiration_CaseStudy2` | 该算例是 CO2/土壤呼吸案例的最小单运行版本。它使用 Sacramento California 的 `SCA` 日天气和一个 SCA 土壤文件, 适合作为 CaseStudy1 之前的快速检查案例, 或用于确认 CO2/气体模块在单一运行下能否正常生成输入和执行。 | 单一运行 `SCA2004_Run1`, `SCA_Wea`, `SCA_Soil_SCA2004_Run1.soi`, 默认气体参数。 |
| `Kansas` | 该算例用于测试 Kansas 多站点玉米模拟, 同时覆盖日天气和小时天气, 以及旱作/灌溉处理。它适合检查接口对多地点, 多天气尺度, 多土壤和补充灌溉记录的处理能力。 | `AshDry` 与 `AshIrr`, Ashland 小时天气, 其他站点日天气, `ASHD06IR`, `CULI05IR`, `MOSI06IR` 的显式灌溉设置。 |
| `MDEasternShore (maize)` | 该算例用于 Maryland Eastern Shore 玉米案例模拟, 重点是 Wye 和 Del 两个地点的小时天气运行。它没有显式灌溉, 依赖天气文件中的降雨输入, 适合做无灌溉条件下的地点, 年份, 品种和土壤对照。Del 组降雨很高, `DEL07`, `DEL08`, `DEL09` 还构成清晰的土壤替换对照。 | Wye 逐年运行, Del 逐年运行, `WyeSoil.soi`, `Caswell.soi`, `Piedmont.soi`, 高降雨天气, 无显式灌溉。 |
| `Tropical_Temperate_Study` | 该算例用于热带地点 Rahuri 与温带地点 Marshall 的多年对比。它把两个地点各 13 年的日天气, 独立土壤文件和固定管理方案整理在同一参数表中, 适合比较气候带差异, 年际天气差异和地点差异对模型结果的影响。 | `Rahuri` 与 `Marshall`, 2009 到 2021 年逐年天气 ID, 两个品种, 两套土壤和施肥总量差异。 |

## 总览

| 算例目录 | Excel 参数表 | 天气 CSV | Description 运行数 | 主要地点 | 天气尺度 | 主要用途或差异主题 |
|---|---|---|---:|---|---|---|
| `AgmipET2` | `AGMIPET2Sim.xlsx` | `AgMipET2weather.csv` | 20 | `Mead`, `Bush` | 小时天气源, `Time` 表为 `WeatherHourly=1` | AgMIP ET2, 包括 Mead 灌溉/雨养和 Bush 不同灌溉系统处理 |
| `CO2_Respiration_CaseStudy1` | `CaseStudy1.xlsx` | `CaseStudy1_2_Weather.csv` | 87 | `OCA` / `OntCA` | 当前运行接入日天气, `WeatherDaily=1` | CO2/土壤呼吸案例 1, 以 OCA 为主, 包含气体扩散和土壤参数敏感性 |
| `CO2_Respiration_CaseStudy2` | `CaseStudy2.xlsx` | `CaseStudy1_2_Weather.csv` | 1 | `SCA` / `SacCA` | 日天气, `WeatherDaily=1` | CO2/土壤呼吸案例 2, Sacramento 单运行 |
| `Kansas` | `kansas inputs.xlsx` | `KansasWea.csv` | 13 | `Ashland`, `Cullison`, `Hutchingson`, `Manhattan`, `Moscow` | 混合, Ashland 为小时天气, 其他站点为日天气 | Kansas 多站点, 包含旱作/灌溉处理和若干补充灌溉运行 |
| `MDEasternShore (maize)` | `MD-DE inputs.xlsx` | `MD_Del_weather.csv` | 7 | `Wye`, `Del` | 小时天气 | Maryland Eastern Shore 玉米案例, 两个地点, 三个品种/土壤组合 |
| `Tropical_Temperate_Study` | `Temperate_Tropical_Sites.xlsx` | `Temperate_Tropical_Weather.csv` | 26 | `Rahuri`, `Marshall` | 日天气 | 热带地点 Rahuri 与温带地点 Marshall 对比, 2009-2021 年逐年运行 |

## 共同文件差异

- `Water.DAT`: 根目录, `AgmipET2`, `Kansas`, `MDEasternShore (maize)` 中内容一致。两个 CO2 案例的 `Water.DAT` 参数数值一致, 主要差别是换行格式。
- `WaterBound.DAT`: 根目录, `AgmipET2`, `MDEasternShore (maize)` 中存在且内容一致。`Kansas`, 两个 CO2 案例和 `Tropical_Temperate_Study` 目录下没有本地 `WaterBound.DAT`。
- `Tropical_Temperate_Study` 目录没有本地 `Water.DAT`, 但 `Example input` 根目录有通用 `Water.DAT` 和 `WaterBound.DAT`。
- `Kansas` 目录存在 `~$kansas inputs.xlsx`, 这是 Excel 临时锁文件, 不应作为正式参数表。

## 天气 CSV 数据概况

| 天气 CSV | 数据行数 | Climate 数 | WeatherID 数 | 日期范围 | 小时字段情况 | 说明 |
|---|---:|---:|---:|---|---|---|
| `AgmipET2/AgMipET2weather.csv` | 307896 | 2 | 6 | 2001-06-07 到 2016-12-31 | 24 个非空小时值, 无空小时行 | 纯小时天气文件, 覆盖 `Mead` 和 `Bush` |
| `CO2_Respiration_CaseStudy1/CaseStudy1_2_Weather.csv` | 319264 | 4 | 33 | 2001-06-07 到 2016-12-31 | 同时含小时和日尺度行, 空小时行 11368 | 包含 `Mead`, `Bush`, `OCA`, `SCA`, 以及 CO2/温度/降雨扰动天气 ID |
| `CO2_Respiration_CaseStudy2/CaseStudy1_2_Weather.csv` | 319264 | 4 | 33 | 2001-06-07 到 2016-12-31 | 同上 | 与 CaseStudy1 文件相同 |
| `Kansas/KansasWea.csv` | 37161 | 5 | 6 | 2005-01-01 到 2006-12-31 | 混合, 有小时行也有空小时行 | `AshDry`, `AshIrr` 为小时天气, 其他站点在 `Weather` 表中标为日天气 |
| `MDEasternShore (maize)/MD_Del_weather.csv` | 41571 | 2 | 2 | 2006-01-01 到 2008-12-31 | 非空小时值含 0 到 24 | 小时天气文件, 覆盖 `Del`, `Wye` |
| `Tropical_Temperate_Study/Temperate_Tropical_Weather.csv` | 12236 | 2 | 34 | 2002-01-01 到 2022-06-30 | 小时字段全部为空 | 纯日天气文件, 当前参数表使用其中 2009-2021 年的 `rhr*` 和 `mrs*` |

## 算例总体描述

本节只保留每个算例的总体目的, 文件组成, 运行数量, 天气尺度, 主要差异和使用建议。`Kansas` 与 `MDEasternShore (maize)` 的极详细设置已经拆分到独立文档。

### 1. AgmipET2

- 参数表: `AgmipET2/AGMIPET2Sim.xlsx`
- 天气文件: `AgmipET2/AgMipET2weather.csv`
- 运行数: 20
- 主要地点: `Mead`, `Bush`
- 天气尺度: 天气源为小时数据, `Time` 表中 `WeatherHourly=1`
- 总体目的: 复现或测试 AgMIP ET2 相关玉米模拟输入, 覆盖多年份, 多地点和多水分管理条件。
- 主要差异: Mead 组包含 `MeadNE2` 灌溉和 `MeadNE3` 雨养对照; Bush 组包含 `NW-MESA-75%`, `SW-MESA-100%`, `NE-SDI-100%`, `SE-SDI-100%` 等灌溉系统处理。
- 适合用途: 适合做多地点, 多年份, 灌溉/雨养和灌溉系统差异测试。若用于数据同化研究, 更适合作为方法成熟后的扩展验证算例。
- 注意事项: 年份, 品种, 土壤文件, 施肥和灌溉制度会共同变化, 不宜作为最简单的首个同化实验。

### 2. CO2_Respiration_CaseStudy1

- 参数表: `CO2_Respiration_CaseStudy1/CaseStudy1.xlsx`
- 天气文件: `CO2_Respiration_CaseStudy1/CaseStudy1_2_Weather.csv`
- 运行数: 87
- 主要地点: `OCA` / `OntCA`
- 天气尺度: 当前运行实际接入日天气, `WeatherDaily=1`
- 总体目的: 用于 CO2/土壤呼吸相关参数敏感性测试, 重点不是一般作物管理对照, 而是气体扩散和土壤过程参数变化。
- 主要差异: 包含 `bTort`, `fe`, `kh`, `kL`, `fh`, `rL`, `r0` 的单参数敏感性, 以及 `kL x fe` 双参数组合。
- 适合用途: 适合研究土壤 CO2, 土壤呼吸, 气体扩散或土壤参数反演。
- 注意事项: `Weather` 表中虽然列出 CO2, 温度和降雨扰动天气 ID, 但当前 87 个运行实际都使用 `OCAWea2003_2005`。若研究问题不是 CO2/土壤呼吸, 不建议把它作为主算例。

### 3. CO2_Respiration_CaseStudy2

- 参数表: `CO2_Respiration_CaseStudy2/CaseStudy2.xlsx`
- 天气文件: `CO2_Respiration_CaseStudy2/CaseStudy1_2_Weather.csv`
- 运行数: 1
- 主要地点: `SCA` / `SacCA`
- 天气尺度: 日天气, `WeatherDaily=1`
- 总体目的: CO2/土壤呼吸案例的最小单运行版本, 用于快速检查 Sacramento 单运行输入。
- 主要差异: 无多运行差异, 只有 `SCA2004_Run1` 一个 run。
- 适合用途: 适合作为 CO2/气体模块或 Excel 接口生成流程的最小调试用例。
- 注意事项: 因为只有 1 个运行, 不适合支撑跨年份, 跨地点, 多处理或参数组合的研究结论。

### 4. Kansas

- 参数表: `Kansas/kansas inputs.xlsx`
- 天气文件: `Kansas/KansasWea.csv`
- 运行数: 13
- 主要地点: `Ashland`, `Cullison`, `Hutchingson`, `Manhattan`, `Moscow`
- 天气尺度: 混合天气尺度。`AshDry` 和 `AshIrr` 为小时天气; `Cullison`, `Moscow`, `Manhattan`, `Hutchingson` 为日天气。
- 总体目的: Kansas 多站点玉米模拟, 覆盖日/小时天气, 多地点, 多土壤, 品种差异和旱作/灌溉处理。
- 主要差异: Ashland 有 `AshDry`/`AshIrr` 旱作和灌溉天气对照; `ASHD06IR`, `CULI05IR`, `MOSI06IR` 是额外显式灌溉运行。
- 适合用途: 适合作为数据同化研究的第二阶段算例, 尤其适合研究灌溉处理, 水分管理和多地点泛化。
- 注意事项: `MOSI06IR` 的 `Irrig` 表有一条日期范围反向或跨年异常记录, 正式运行前需要核查。
- 详细设置: [查看 Kansas 极详细设置](Kansas_settings_zh.md)

### 5. MDEasternShore (maize)

- 参数表: `MDEasternShore (maize)/MD-DE inputs.xlsx`
- 天气文件: `MDEasternShore (maize)/MD_Del_weather.csv`
- 运行数: 7
- 主要地点: `Wye`, `Del`
- 天气尺度: 全部小时天气, `WeatherHourly=1`
- 总体目的: Maryland Eastern Shore 玉米案例模拟, 用于无显式灌溉条件下的地点, 年份, 品种和土壤对照。
- 主要差异: Wye 组覆盖 2006 到 2008 年逐年运行; Del 组包含 2006/2007 年运行, 其中 `DEL07`, `DEL08`, `DEL09` 是同天气, 同模拟期, 同品种下的土壤替换对照。
- 适合用途: 最适合作为数据同化研究的首选主算例, 尤其适合土壤水分, 作物状态和土壤参数同化框架搭建。
- 注意事项: `DEL08` 和 `DEL09` 没有施肥行; Del 组模拟期降雨非常高, 更适合湿润条件下水分过程分析。
- 详细设置: [查看 MDEasternShore (maize) 极详细设置](MDEasternShore_maize_settings_zh.md)

### 6. Tropical_Temperate_Study

- 参数表: `Tropical_Temperate_Study/Temperate_Tropical_Sites.xlsx`
- 天气文件: `Tropical_Temperate_Study/Temperate_Tropical_Weather.csv`
- 运行数: 26
- 主要地点: `Rahuri`, `Marshall`
- 天气尺度: 全部日天气
- 总体目的: 热带地点 Rahuri 与温带地点 Marshall 的多年对比, 每个地点覆盖 2009 到 2021 年逐年运行。
- 主要差异: 两个地点使用不同气候, 土壤文件, 品种和施肥方案; 每个年份对应独立天气 ID 和独立土壤文件。
- 适合用途: 适合同化方法稳定后的跨气候带泛化测试, 或比较热带/温带气候差异对模型输出的影响。
- 注意事项: 该算例是地点和气候带对比, 不是同一地点下的单因素控制试验。它更适合做泛化验证, 不适合作为首个最小同化案例。

## 快速结论

- 如果想测试“多地点多年份和灌溉处理”, `AgmipET2` 和 `Kansas` 最合适。
- 如果想测试“CO2/土壤呼吸参数敏感性”, `CO2_Respiration_CaseStudy1` 最完整, 尤其是 `bTort`, `fe`, `kh`, `kL`, `fh`, `rL`, `r0`, 以及 `kL x fe` 组合。
- 如果想测试一个最小 CO2 案例, `CO2_Respiration_CaseStudy2` 最简单, 只有一个 run。
- 如果想复现实验性玉米案例, `MDEasternShore (maize)` 的运行数少, 结构简单, 但 `DEL08` 和 `DEL09` 需要注意没有施肥记录。
- 如果想做热带/温带气候对比, `Tropical_Temperate_Study` 结构最清楚, 两地点各 13 年, 全部日天气。
