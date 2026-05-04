# SingleLayerLoam2D 算例说明

## 目的

本算例用于参数敏感性分析的最小二维基线。它保留 MAIZSIM/2DSOIL 的二维土壤网格, 但土壤剖面只设置一个 0-200 cm 均质壤土层。

## 文件

- `SingleLayerLoam2D.xlsx`: ExcelInterface 输入工作簿。
- `MD_Del_weather.csv`: 复用 Maryland Eastern Shore 示例中的 Wye 小时天气。
- `Water.DAT`, `WaterBound.DAT`: 复用 Maryland Eastern Shore 示例中的水分参数和边界文件。
- `../../maizsim_input_loam2d.toml`: Python/TOML 自动生成配置。
- `sensitivity_parameter_bounds.toml`: 第一轮 Morris 参数边界配置。

## 基线运行

`Description.ID` 为 `LOAM2D`。

该 run 复用 `WYE07` 的天气, 作物品种和施肥管理, 只替换土壤为单层壤土, 以减少敏感性分析的混杂因素。

当前修订后的关键输入修复:

- `Init.Long=-76.55`, 与 `Climate.Longitude=-76.55` 保持一致。源码中作物端太阳几何实际使用 `LOAM2D.ini` 里的经度, 因此不能保留正值 `76.55`。
- `Init.end=2007-09-30`, 与 `Time.EndDate=2007-09-30` 对齐。源码中 `Init.end` 控制作物端 `g01` 输出窗口, 原 `2007-09-18` 会让作物输出停在 `grainFill`。
- `Init.seedDepth=10 cm`, 与 `GridRatio.PlantingDepth=10 cm` 对齐。
- `Time` 表中 `LOAM2D` 设为 `Daily=1`, `Hourly=0`, `WeatherDaily=0`, `WeatherHourly=1`。敏感性批量运行使用日输出, 但仍用小时天气驱动。
- 天气文件生成脚本会把源 CSV 中超过 100 的 `RH` 限制到 100 后写入 `.wea`。源码读入时还会把 RH 换算值限制到约 98%, 因此源 CSV 的 `RH>100` 不应原样进入生成文件。

## 单层壤土设置

`Soil` 表中仅新增一行 `Loam_200cm.soi`:

| 参数 | 数值 |
|---|---:|
| Bottom depth | 200 cm |
| Sand | 40 |
| Silt | 40 |
| Clay | 20 |
| BD | 1.4 g/cm3 |
| HNew | -100 cm |
| thr | 0.078 |
| ths | 0.43 |
| Alfa | 0.036 |
| n | 1.56 |
| Ks | 24.96 cm/day |
| Kk | 24.96 cm/day |
| thk | 0.43 |

注意: `SingleLayerLoam2D.xlsx` 的 `Soil` 表中 Sand, Silt, Clay 按百分数填写。宏生成 `.lyr` 和 `.soi` 时会转换为 0.40, 0.40, 0.20 这类 fraction。

## 参数来源

本仓库原始文件中没有 Carsel and Parrish (1988) 的完整壤土参数表。当前 `thr`, `ths`, `Alfa`, `n`, `Ks` 取自文献中常用的 USDA loam van Genuchten-Mualem 典型参数:

- `thr=0.078`
- `ths=0.430`
- `Alfa=0.036 1/cm`
- `n=1.56`
- `Ks=24.96 cm/day`

参考文献:

Carsel, R. F., and Parrish, R. S. 1988. Developing joint probability distributions of soil water retention characteristics. Water Resources Research, 24(5), 755-769.

`Kk` 和 `thk` 是 MAIZSIM/2DSOIL 的近饱和导水率连接参数。由于当前没有独立近饱和实测点, 本算例先设为 `Kk=Ks`, `thk=ths`。

## 敏感性分析推荐参数集

严格按当前 Excel 参数说明筛选, 并纳入说明中标注为 `can be experimented with` 的根系空间扩散参数后, 本算例第一轮 Morris 敏感性分析建议使用 13 个参数。源码审查后需要把它们分成 1 个整数/离散参数和 12 个连续实数参数。

| 类别 | 参数 | 当前值 | 源码/回写类型 | Morris 处理 | 约束/联动 |
|---|---|---:|---|---|---|
| 作物物候和叶片 | `JuvenileLeaves` | 18 | C++ `int` | 整数/离散, 不能当连续实数直接写入 | 若按 +/-10% 采样, 需四舍五入为整数, 并记录实际扰动值 |
| 作物物候和叶片 | `Rmax_LTAR` | 0.53 | C++ `double` | 连续 | 保持正值 |
| 作物物候和叶片 | `Rmax_LTIR` | 0.978 | C++ `double`, 源码名为 `Rmax_LIR` | 连续 | 保持正值 |
| 作物物候和叶片 | `PhyllFrmTassel` | 3 | C++ `double`, 源码名为 `PhyllochronsToSilk` | 连续 | 这是物候事件阈值, 响应可能不平滑 |
| 作物物候和叶片 | `StayGreen` | 4.5 | C++ `double` | 连续 | 保持正值 |
| 作物物候和叶片 | `LM_min` | 125 | C++ `double` | 连续 | 保持正值 |
| 根系空间分布 | `Diffx` | 20 | Fortran `REAL`, 源码名为 `DMolx` | 连续 | 保持非负 |
| 根系空间分布 | `Diffz` | 1 | Fortran `REAL`, 源码名为 `DMolz` | 连续 | 保持非负 |
| 土壤水力参数 | `thr` / `thetaR` | 0.078 | Fortran `REAL` | 连续 | 若作为残余含水量扰动, 同步写 `thr` 和 `tha`, 并保持 `0 <= thetaR < thetaS` |
| 土壤水力参数 | `ths` / `thetaS` | 0.430 | Fortran `REAL` | 连续 | 同步写 `ths`, `th`/`thm` 和 `thk`, 并保持 `thetaR < thetaS < 1` |
| 土壤水力参数 | `Alfa` | 0.036 | Fortran `REAL` | 连续 | 必须 `Alfa > 0` |
| 土壤水力参数 | `n` / `npar` | 1.56 | Fortran `REAL` | 连续 | 必须 `n > 1`, 且不要贴近 1 |
| 土壤水力参数 | `Ks` / `Ksat` | 24.96 | Fortran `REAL` | 连续 | 必须 `Ks > 0`; 当前基线应同步 `Kk=Ks` |

按源码分类后的第一轮参数清单:

- 整数/离散参数: `JuvenileLeaves`。
- 连续作物参数: `Rmax_LTAR`, `Rmax_LTIR`, `PhyllFrmTassel`, `StayGreen`, `LM_min`, `Diffx`, `Diffz`。
- 连续土壤参数: `thr`/`thetaR`, `ths`/`thetaS`, `Alfa`, `n`/`npar`, `Ks`/`Ksat`。

参数边界已固化到 `sensitivity_parameter_bounds.toml`。该配置记录每个参数的当前值, 上下限, 参数类型, Excel 来源字段, 目标生成文件字段和联动写回字段。当前 `lower`/`upper` 已从早期宽边界收窄为围绕 `LOAM2D` 基线的局部 Morris 边界, 作为第一轮 smoke 和 formal 的默认稳定边界。若后续需要重新扩大边界, 必须每次只扩大一组参数并重新通过 smoke 验证, 不应直接恢复早期宽边界。

### 失败样本诊断和边界收窄依据

本节记录 `codex_smoke_workers20_timeout300` 宽边界 smoke 的失败样本诊断, 用于防止后续误把失败归因到单个 changed parameter, 或在 formal 前重新引入已知高风险组合。

数据来源:

- 宽边界运行: `sensitivity_runs/codex_smoke_workers20_timeout300`。
- 局部收窄边界运行: `sensitivity_runs/codex_smoke_localbounds_workers20_timeout300`。

宽边界运行使用 `--max-workers 20 --timeout-seconds 300`, 共 28 个 smoke 样本, 22 个成功, 6 个失败。局部收窄边界运行使用同样并行和超时设置, 28 个样本全部成功, `failures.csv` 为空, `morris_indices.csv` 正常生成。

失败不是路径、并发目录或输出解析问题。证据包括:

- 失败样本均已启动 `2dMAIZSIM.exe`, `stdout.txt` 中出现模型读入和作物初始化信息。
- 失败样本 `stderr.txt` 为空, 未见 Python traceback、路径错误或文件访问错误。
- 失败样本均生成了 `LOAM2D.g01`, `LOAM2D.G03`, `LOAM2D.G05` 等输出文件, 说明模型已进入计算阶段。
- 运行结束后无残留 `2dMAIZSIM`, `pixi` 或 `python` 进程。
- `sample_000024` 到 `sample_000028` 的输出停在出苗后早期阶段, 长时间无进度推进后触发 300 秒超时, 更符合数值求解极慢或卡住。

失败样本清单如下:

| sample_id | trajectory_id | step_id | changed_parameter | elapsed_seconds | 失败类型 |
|---:|---:|---:|---|---:|---|
| 4 | 1 | 3 | `thetaS` | 38.348 | `ORTHOMIN TERMINATES -- TOO MANY ITERATIONS` |
| 24 | 2 | 9 | `Alfa` | 300.027 | 模型运行超时 |
| 25 | 2 | 10 | `PhyllFrmTassel` | 300.026 | 模型运行超时 |
| 26 | 2 | 11 | `LM_min` | 300.019 | 模型运行超时 |
| 27 | 2 | 12 | `JuvenileLeaves` | 300.029 | 模型运行超时 |
| 28 | 2 | 13 | `thetaS` | 300.025 | 模型运行超时 |

失败样本的实际写入参数值如下:

| sample_id | `JuvenileLeaves` | `Rmax_LTAR` | `Rmax_LTIR` | `PhyllFrmTassel` | `StayGreen` | `LM_min` | `Diffx` | `Diffz` | `thetaR` | `thetaS` | `Alfa` | `n` | `Ks` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 21 | 0.526667 | 0.800000 | 5.000000 | 2.0 | 130.000000 | 17.466667 | 0.500000 | 0.066667 | 0.45 | 0.055 | 1.866667 | 5.000000 |
| 24 | 16 | 0.526667 | 0.933333 | 5.000000 | 8.0 | 130.000000 | 2.400000 | 1.333333 | 0.066667 | 0.40 | 0.055 | 1.200000 | 23.333333 |
| 25 | 16 | 0.526667 | 0.933333 | 2.666667 | 8.0 | 130.000000 | 2.400000 | 1.333333 | 0.066667 | 0.40 | 0.055 | 1.200000 | 23.333333 |
| 26 | 16 | 0.526667 | 0.933333 | 2.666667 | 8.0 | 103.333333 | 2.400000 | 1.333333 | 0.066667 | 0.40 | 0.055 | 1.200000 | 23.333333 |
| 27 | 19 | 0.526667 | 0.933333 | 2.666667 | 8.0 | 103.333333 | 2.400000 | 1.333333 | 0.066667 | 0.40 | 0.055 | 1.200000 | 23.333333 |
| 28 | 19 | 0.526667 | 0.933333 | 2.666667 | 8.0 | 103.333333 | 2.400000 | 1.333333 | 0.066667 | 0.50 | 0.055 | 1.200000 | 23.333333 |

关键相邻样本对比:

- `sample_000004` 是显式 ORTHOMIN 数值失败。它与上一个成功样本 `sample_000003` 的主要差异是 `thetaS` 从 `0.35` 增加到 `0.45`; 其它关键水力参数保持 `Diffx=17.466667`, `Diffz=0.5`, `thetaR=0.066667`, `Alfa=0.055`, `n=1.866667`, `Ks=5.0`。下一个成功样本 `sample_000005` 又把 `Diffx` 从 `17.466667` 降到 `2.4`, 并在 `thetaS=0.45` 下成功。因此不能说 `thetaS=0.45` 单独失败, 更合理的结论是 `thetaS=0.45 + Diffx=17.466667 + Diffz=0.5 + Alfa=0.055 + n=1.866667 + Ks=5.0` 这个背景组合触发了数值不稳定。
- `sample_000024` 是连续超时链条的起点。它与上一个成功样本 `sample_000023` 的主要差异是 `Alfa` 从 `0.015` 增加到 `0.055`; 其它关键参数保持 `Diffx=2.4`, `Diffz=1.333333`, `thetaR=0.066667`, `thetaS=0.40`, `n=1.2`, `Ks=23.333333`。因此在该背景下, `Alfa=0.055 + n=1.2` 是最清晰的超时触发组合。
- `sample_000025` 到 `sample_000028` 不能解释为作物参数单独导致失败。它们继承了 `sample_000024` 已经失败的土壤水力背景, 后续改变的 `PhyllFrmTassel`, `LM_min`, `JuvenileLeaves`, `thetaS` 只是 Morris 轨迹后续步。尤其 `sample_000028` 的 `thetaS=0.50` 不能单独归因为失败原因, 因为在 `thetaS=0.40` 时 `sample_000024` 到 `sample_000027` 已经连续超时。

从现有 smoke 结果可执行的防错结论如下:

- 不要把 `Alfa=0.055`, `n=1.2`, `Diffx=2.4`, `Ks=5.0`, `thetaS=0.45` 等单个值直接标记为必然失败值; 失败来自 Morris 背景参数组合。
- 第一轮 formal 不应恢复早期宽边界, 尤其应避免 `Alfa` 接近 `0.055` 且 `n` 接近 `1.2` 的组合。
- 第一轮 formal 不应使用 `Ks=5.0 cm/day` 作为下界; 在低 `Ks` 背景下再叠加较高 `thetaS`, 较高 `Alfa`, 低 `Diffz` 和较高 `Diffx` 已触发 ORTHOMIN 失败。
- `Diffx=2.4` 和 `Diffz=0.5` 这类远离基线的根系扩散端点不宜与宽土壤水力边界同时放开。现有证据显示它们出现在慢运行或失败背景中, 但不能单独定性为失败原因。
- `thetaS=0.50` 和 `thetaR=0.12` 这类宽含水量端点尚未证明会单独失败, 但与 `Alfa`, `n`, `Ks` 的极端组合会扩大数值求解风险。
- 作物参数宽边界如 `StayGreen=8`, `PhyllFrmTassel=5`, `LM_min=103.333333` 不应被直接归因为数值失败; 样本 25-27 的 changed_parameter 是作物参数, 但它们继承了高风险土壤水力背景。

当前局部边界更稳的依据:

- 当前单层壤土基线来自一组内部一致的 USDA loam van Genuchten-Mualem 典型参数: `thetaR=0.078`, `thetaS=0.430`, `Alfa=0.036`, `n=1.56`, `Ks=24.96`。
- 当前边界围绕这组基线做局部扰动: `thetaR=0.070-0.086`, `thetaS=0.387-0.473`, `Alfa=0.032-0.040`, `n=1.40-1.72`, `Ks=22.5-27.5`, `Diffx=18.0-22.0`, `Diffz=0.9-1.1`。
- 当前边界保留联动关系: `thetaR` 同步写 `thr/tha`, `thetaS` 同步写 `ths/th/thm/thk`, `Ks` 同步写 `Ks/Kk`。
- 实测 smoke 对比显示, 宽边界 28 个样本中 22 个成功、6 个失败; 当前局部边界 28 个样本全部成功, 并生成完整 `outputs.csv` 和 `morris_indices.csv`。

后续扩大边界时必须遵守以下规则:

- 每次只扩大一组参数, 例如先土壤水力, 再根系扩散, 再作物物候; 每次扩大后都重新运行 smoke。
- formal 前检查采样矩阵实际值, 确认没有再次出现 `n≈1.2` 且 `Alfa≈0.055`, 或 `Ks≈5`, `Diffx≈2.4`, `Diffz≈0.5` 这类高风险组合。
- 每个样本回写后继续校验 `0 <= thetaR < thetaS < 1`, `Alfa > 0`, `n >= 1.4`, `Ks > 0`, `Diffx >= 0`, `Diffz >= 0`, 并校验 `thr=tha`, `ths=th/thm/thk`, `Ks=Kk`。
- `failures.csv` 非空时不要计算正式 Morris 指标, 也不要把后续继承失败背景的样本误判为 changed_parameter 本身失败。
- formal 必须检查 `failures.csv`, `outputs.csv` 缺失值, 运行耗时分布和 `matured` 标记。当前局部 smoke 虽然无失败且指标无缺失, 但有部分样本 `matured=false`; 解释 `final_shoot_dm` 和 `final_ear_dm` 时应将这些样本视为末日 `shootDM` 和 `earDM`, 不能直接等同成熟地上生物量或成熟产量。

### 靶向失败边界探针结果

为进一步探索“什么参数设置会报错或长时间模拟”, 已新增独立诊断脚本 `sensitivity_analysis/maizsim_probe_failures.py`。该脚本不计算 Morris 指标, 只用于构造靶向参数组合, 复制独立运行目录, 回写参数, 并记录失败、超时、慢成功和输出指标。

探针脚本后续默认把结果写入 `failure_probes/<analysis_id>/`, 避免和正式 Morris 的 `sensitivity_runs/<analysis_id>/` 混淆。本次探索开始较早, 以下两轮历史结果仍保留在 `sensitivity_runs` 下用于溯源:

- `sensitivity_runs/codex_failure_probe_targeted_138_timeout240`: 138 个靶向组合, `--max-workers 20`, `--timeout-seconds 240`, `--slow-seconds 120`。
- `sensitivity_runs/codex_failure_probe_p0p1_cropbaseline_timeout240`: 24 个 P0/P1 组合, 作物参数固定为基线, 只改变土壤水力和根系扩散参数。

两轮结果汇总:

| 运行 | 总数 | 快成功 | 慢成功 | 超时 | ORTHOMIN |
|---|---:|---:|---:|---:|---:|
| `codex_failure_probe_targeted_138_timeout240` | 138 | 87 | 31 | 19 | 1 |
| `codex_failure_probe_p0p1_cropbaseline_timeout240` | 24 | 11 | 1 | 4 | 8 |

其中“慢成功”定义为模型成功结束, 但耗时大于等于 120 秒。慢成功不代表模型错误, 但不适合直接进入大规模 formal, 否则总运行时间会失控。

#### `Alfa` 与 `n` 的组合风险

在低 `Diffx=2.4`, `Diffz=1.333333`, `thetaR=0.066667`, `thetaS=0.40`, `Ks=23.333333` 背景下, `Alfa` 与 `n` 是最清楚的长时/超时风险面。

靶向 138 组合探针显示:

- `n=1.2` 时, `Alfa=0.015` 可成功但很慢, 耗时约 174 秒。
- `n=1.2` 且 `Alfa>=0.032` 时均超时。
- `n=1.3` 在部分 `Alfa` 值下超时或慢成功, 不够稳定。
- `n>=1.4` 时, 该组 `Alfa` 范围内基本恢复为快成功。

固定作物基线的 P0/P1 探针进一步确认:

| case | `Alfa` | `n` | 状态 | 耗时 |
|---|---:|---:|---|---:|
| `T01_low_n_low_alfa` | 0.015 | 1.20 | 慢成功 | 140.588 s |
| `T02_known_timeout_anchor` | 0.055 | 1.20 | 超时 | 240.027 s |
| `T03_local_alfa_high_low_n` | 0.040 | 1.20 | 超时 | 240.027 s |
| `T04_alfa_045_low_n` | 0.045 | 1.20 | 超时 | 240.026 s |
| `T05_alfa_050_low_n` | 0.050 | 1.20 | 超时 | 240.026 s |
| `T06_high_alfa_n_140` | 0.055 | 1.40 | 快成功 | 62.699 s |
| `T07_high_alfa_base_n` | 0.055 | 1.56 | 快成功 | 53.610 s |
| `T08_high_alfa_n_130` | 0.055 | 1.30 | 快成功 | 78.640 s |
| `T09_alfa_050_n_130` | 0.050 | 1.30 | 快成功 | 77.887 s |

结论:

- `n=1.2` 是明确的高风险下界, 即使 `Alfa=0.015` 也会显著变慢, `Alfa>=0.040` 时在 P0/P1 中超时。
- `n=1.3` 不是绝对失败, 但在 138 组合探针中仍出现不稳定, 因此不建议作为第一轮 formal 下界。
- 当前局部边界 `n>=1.40` 是合理的稳定下界。
- 当前局部边界 `Alfa<=0.040` 只有在 `n>=1.40` 时才应视为稳定; 不应将 `Alfa=0.040` 与 `n=1.2` 同时放入正式采样。

#### 低 `Ks` 与高 `Alfa`, 高 `n` 的 ORTHOMIN 风险

固定作物基线的 P0/P1 探针显示, 下列背景极易触发 ORTHOMIN:

- `thetaR=0.0667`
- `Alfa=0.055`
- `n=1.8667`
- `Ks=5.0`

在这个背景下, 单独改变 `thetaS`, `Diffx`, `Diffz` 并不能可靠解除失败:

| case | `thetaS` | `Diffx` | `Diffz` | `Ks` | 状态 | 耗时 |
|---|---:|---:|---:|---:|---|---:|
| `O01_low_ks_safe_anchor` | 0.35 | 17.4667 | 0.5 | 5.0 | ORTHOMIN | 65.611 s |
| `O02_known_orthomin_anchor` | 0.45 | 17.4667 | 0.5 | 5.0 | ORTHOMIN | 53.966 s |
| `O03_thetaS_040` | 0.40 | 17.4667 | 0.5 | 5.0 | ORTHOMIN | 59.334 s |
| `O04_thetaS_043` | 0.43 | 17.4667 | 0.5 | 5.0 | ORTHOMIN | 57.712 s |
| `O05_low_diffx` | 0.45 | 2.4 | 0.5 | 5.0 | ORTHOMIN | 56.066 s |
| `O06_mid_diffx` | 0.45 | 10.0 | 0.5 | 5.0 | ORTHOMIN | 55.478 s |
| `O07_raise_diffz` | 0.45 | 17.4667 | 1.0 | 5.0 | ORTHOMIN | 56.387 s |
| `O08_raise_ks` | 0.45 | 17.4667 | 0.5 | 10.0 | ORTHOMIN | 54.603 s |
| `O09_local_alfa_high` | 0.45 | 17.4667 | 0.5 | 5.0 | 快成功 | 84.770 s |
| `O10_local_n_high` | 0.45 | 17.4667 | 0.5 | 5.0 | 快成功 | 69.755 s |

其中 `O09_local_alfa_high` 的差异是把 `Alfa` 降到 `0.040`; `O10_local_n_high` 的差异是把 `n` 降到 `1.72`。这说明在低 `Ks` 背景下, `Alfa=0.055 + n=1.8667` 的组合比单独的 `thetaS`, `Diffx`, `Diffz` 更关键。

结论:

- `Ks=5.0` 不应作为第一轮 formal 下界。
- `Alfa=0.055` 与 `n=1.8667` 同时出现时, 低 `Ks` 背景高度危险。
- 降低 `Alfa` 到当前局部上界 `0.040`, 或把 `n` 降到当前局部上界附近 `1.72`, 在 P0/P1 探针中可以解除 ORTHOMIN。
- 因此当前边界 `Alfa<=0.040`, `n<=1.72`, `Ks>=22.5` 是组合层面的稳定选择, 不是任意收窄。

#### 根系扩散和含水量端点的单独风险

在当前局部土壤水力背景下, 根系扩散极端没有单独触发失败:

- `Diffx=2.4-25.0`
- `Diffz=0.5-3.0`
- 30 个 `root_extreme` 组合全部快成功。

在当前局部 `Alfa/n/Ks` 背景下, 含水量端点也没有单独触发失败:

- `thetaR=0.04-0.12`
- `thetaS=0.35-0.50`, 且 `thetaR < thetaS`
- 25 个 `water_content` 组合全部快成功。

固定作物基线 P0/P1 中, 当前局部边界最坏角点也成功:

- `thetaR=0.086`
- `thetaS=0.473`
- `Alfa=0.040`
- `n=1.40`
- `Ks=22.5`
- `Diffx=18.0`
- `Diffz=0.9`
- 状态为快成功, 耗时约 24.628 秒。

结论:

- `Diffx` 和 `Diffz` 不应作为单参数失败原因处理; 它们主要在低 `Ks`, 高 `Alfa`, 极端 `n` 背景下放大风险。
- `thetaR` 和 `thetaS` 端点不应作为单参数失败原因处理; 但它们会和 `Alfa/n/Ks` 极端组合共同影响数值稳定性。
- 当前局部边界的最坏角点已经通过 P0/P1 探针, 可作为第一轮 formal 的默认边界。

#### 作物参数独立和配对探针结果

为补齐作物参数组合风险判断, 新增并运行 `maizsim_probe_failures.py --case-set crop`。该矩阵分两层:

- 固定当前土壤水力和根系扩散基线, 只改变作物物候和叶片参数, 用于判断作物参数是否有独立数值风险。
- 将作物低/高角点与已知风险土壤背景配对, 用于区分作物独立风险, 土壤背景继承风险和作物-土壤交互风险。

运行记录:

- 结果目录: `failure_probes/codex_crop_probe_full_125_timeout240`。
- 命令参数: `--case-set crop --max-workers 20 --timeout-seconds 240 --slow-seconds 120`。
- 总组合数: 125。
- 总体结果: 118 个快成功, 2 个慢成功, 5 个超时, 0 个 ORTHOMIN。

固定土壤和根系基线的作物探针结果:

| 组合组 | 数量 | 结果 |
|---|---:|---|
| `crop_control` | 1 | 全部快成功 |
| `crop_local_single` | 12 | 全部快成功 |
| `crop_wide_single` | 12 | 全部快成功 |
| `crop_local_corner` | 8 | 全部快成功 |
| `crop_wide_corner` | 8 | 全部快成功 |
| `crop_rate_grid` | 27 | 全部快成功 |
| `crop_canopy_grid` | 27 | 全部快成功 |
| `crop_inherited_failure_replay` | 4 | 全部快成功 |

这 99 个固定土壤/根系样本全部快成功, 耗时范围约 34.366-58.366 秒。覆盖的作物宽范围为:

- `JuvenileLeaves=16-21`
- `Rmax_LTAR=0.42-0.58`
- `Rmax_LTIR=0.80-1.00`
- `PhyllFrmTassel=2.666667-5.0`
- `StayGreen=2.0-8.0`
- `LM_min=103.333333-130.0`

其中 `crop_inherited_failure_replay` 专门重放了宽边界 smoke 中样本 24-27 附近的作物组合, 但把土壤水力参数固定回当前基线后全部快成功。因此, 宽边界 smoke 中 changed_parameter 为 `PhyllFrmTassel`, `LM_min`, `JuvenileLeaves` 的超时样本, 不能解释为作物参数独立失败。

作物-土壤配对探针中, 非快成功样本如下:

| case | 作物背景 | 根系背景 | 土壤背景 | 状态 | 耗时 |
|---|---|---|---|---|---:|
| `crop_pair_C0_R0_SAN` | 当前作物基线 | 当前根系基线 | `thetaR=0.066667`, `thetaS=0.40`, `Alfa=0.040`, `n=1.20`, `Ks=23.333333` | 超时 | 240.027 s |
| `crop_pair_C0_RM_SAN` | 当前作物基线 | `Diffx=2.4`, `Diffz=1.333333` | 同上 | 超时 | 240.023 s |
| `crop_pair_CL_RL_SAN` | 当前局部作物低角点 | `Diffx=2.4`, `Diffz=0.5` | 同上 | 超时 | 240.023 s |
| `crop_pair_CH_RH_SAN` | 当前局部作物高角点 | `Diffx=25.0`, `Diffz=3.0` | 同上 | 超时 | 240.021 s |
| `crop_pair_EWL_RM_SAN` | 早期宽作物低角点 | `Diffx=2.4`, `Diffz=1.333333` | 同上 | 慢成功 | 201.003 s |
| `crop_pair_EWH_RM_SAN` | 早期宽作物高角点 | `Diffx=2.4`, `Diffz=1.333333` | 同上 | 超时 | 240.019 s |
| `crop_pair_CL_RL_SLK` | 当前局部作物低角点 | `Diffx=2.4`, `Diffz=0.5` | `thetaR=0.066667`, `thetaS=0.45`, `Alfa=0.055`, `n=1.866667`, `Ks=5.0` | 慢成功 | 167.743 s |

结论:

- 当前局部边界内, 作物物候和叶片参数没有发现独立数值失败风险。
- 即使恢复到早期宽作物范围, 只要土壤水力和根系扩散保持当前基线, 作物组合仍全部快成功。
- `Alfa=0.040 + n=1.20` 背景在多个作物组合下都超时, 包括当前作物基线, 当前局部低/高作物角点和早期宽作物高角点。因此该风险应归因于土壤水力背景, 不是作物参数。
- 作物组合会调节风险背景下的耗时。例如早期宽作物低角点在 `Alfa=0.040 + n=1.20` 背景下从超时变为慢成功, 但耗时仍超过 120 秒, 不能视为稳定组合。
- 低 `Ks=5.0`, 高 `Alfa=0.055`, 高 `n=1.866667` 背景在作物配对探针中至少出现慢成功; 结合前述 P0/P1 的 ORTHOMIN 结果, 仍应作为土壤水力高风险组合处理, 不应通过改变作物参数来规避。

#### 后续采样过滤规则

第一轮正式 Morris 不只依赖单参数上下限。当前主流程已在采样后执行高危组合拒绝采样: 若任一样本命中下列规则, 则丢弃整套 Morris 设计并用递增 seed 重新生成, 避免单点替换破坏 Morris 轨迹结构。包含型阈值比较使用 `morris_defaults.rejection_tolerance`, 避免浮点舍入让接近阈值的高危样本漏过; `n < 1.40` 保持严格小于, 因为 `n=1.40` 是当前局部稳定边界。

- 拦截: `n < 1.40`。
- 拦截: `Ks <= 10`。
- 拦截: `Alfa >= 0.032` 且 `n <= 1.20`。
- 拦截: `Alfa >= 0.040` 且 `n <= 1.20`。
- 拦截: `Alfa >= 0.050` 且 `n <= 1.30`。
- 拦截: `Ks <= 10` 且 `Alfa >= 0.050` 且 `n >= 1.72`。
- 拦截: `Ks <= 10` 且 `Alfa >= 0.050` 且 `Diffz <= 1.0`。
- 拦截: `Ks <= 10` 且 `thetaS >= 0.40` 且 `Diffx >= 10` 且 `Diffz <= 0.5`。
- 数值稳定性层面, 当前作物局部边界可直接进入第一轮 formal; 作物参数扩大到上述早期宽范围时, 也应先保证土壤水力组合未命中前述过滤规则。
- 不要把 `PhyllFrmTassel`, `LM_min`, `JuvenileLeaves`, `StayGreen` 等作物参数的 changed_parameter 单独解释为数值失败根因; 需要先检查该样本继承的土壤水力背景。
- 若后续必须探索宽边界, 应先用 `maizsim_probe_failures.py --case-set p0p1` 和 `maizsim_probe_failures.py --case-set crop` 或定制探针通过后, 再进入 Morris formal。
- `morris_defaults.rejection_max_attempts` 控制最多重采样次数。若超过该次数仍无法生成不含高危组合的 Morris 设计, 主流程会报错停止, 不进入模型运行。
- `parallel_execution.slow_seconds` 控制慢运行阈值。模型成功但耗时大于等于该阈值时写入 `slow_samples.csv`, 并默认跳过 Morris 指标计算, 防止慢成功样本掩盖数值不稳定。

这些规则只适用于当前 `LOAM2D` 单层壤土基线和当前 MAIZSIM/2DSOIL 输入结构。若更换土壤剖面、网格、天气、时间步设置或边界条件, 应重新运行 failure probe。

### 输出指标和聚合规则

第一轮敏感性分析只使用能够从当前输出文件稳定抽取的标量指标。所有指标默认使用作物生长期窗口, 即从 `LOAM2D.g01` 第一条日期到 `Note` 首次为 `Matured` 的日期; 如果样本没有成熟, 窗口使用 `LOAM2D.g01` 的完整日期范围, 并在结果表中标记 `matured=false`。

| 指标名 | 对应参考输出 | 文件和字段 | 聚合规则 | 备注 |
|---|---|---|---|---|
| `max_lai` | `LAI` | `LOAM2D.g01` 的 `LAI` | 生长期最大值 | 主指标 |
| `final_shoot_dm` | 地上部生物量 | `LOAM2D.g01` 的 `shootDM` | 首条 `Matured` 记录; 无成熟则取最后一条并标记 | 地上部干物质量, 不包含根 |
| `final_ear_dm` | `grain yield` | `LOAM2D.g01` 的 `earDM` | 首条 `Matured` 记录; 无成熟则取最后一条并标记 | 作为籽粒产量代理指标 |
| `mean_top20_theta` | `SSM` | `LOAM2D.G03` 的 `thNew`, `Area`, `Y` | `Y <= 20 cm` 节点按 `Area` 加权为每日均值, 再取时间均值 | 表层土壤水分主指标 |
| `seasonal_transpiration_deficit` | `WS` | `LOAM2D.G05` 的 `SeasPTran`, `SeasATran` | 最后一日计算 `1 - SeasATran / SeasPTran` | 当 `SeasPTran <= 0` 时记为缺失 |
| `seasonal_potential_transpiration` | 作物潜在蒸腾 | `LOAM2D.G05` 的 `SeasPTran` | 取生长期最后一日累计值 | 用于刻画作物潜在蒸腾需求 |
| `seasonal_actual_transpiration` | 作物实际蒸腾 | `LOAM2D.G05` 的 `SeasATran` | 取生长期最后一日累计值 | 用于刻画作物实际蒸腾实现量 |

当前输出文件没有直接 `DVS` 字段, 第一轮不设置 `DVS` 或物候事件替代指标。

不使用以下列作为第一轮主指标: `MxRtDep`, `LOAM2D.G06` 的 `Shadow`, 以及饱和或近饱和节点的气体 ppm 浓度。

### Morris 实现思路和参数特殊性

后续敏感性分析应按 Hu 的 Morris 全局筛选思路实现, 不应只做固定基线下的单参数高低扰动。具体实现时, 每条 Morris 轨迹的相邻样本只改变一个参数, 但不同 elementary effects 应来自不同背景参数组合。最终用各参数 elementary effects 的 `mu*` 进行排序, 并可同时输出标准差用于判断非线性或交互影响。

批量运行实现必须采用并行结构, 一次调度多个样本同时运行。Morris 采样会生成大量独立模型运行, 如果按样本完全串行执行, 总耗时会过长, 不适合作为正式敏感性分析流程。

### Morris 默认采样设置

第一轮实现使用 `SALib` 提供的 Morris 接口, 不手写核心采样和 `mu*` 计算:

- 采样接口: `SALib.sample.morris.sample`.
- 分析接口: `SALib.analyze.morris.analyze`.
- 默认水平数: `num_levels = 4`.
- 默认随机种子: `seed = 20260429`.
- 默认不启用 `optimal_trajectories`, 避免正式运行前额外增加轨迹筛选成本。
- 默认 `analysis_scaled = true`。原因是 `JuvenileLeaves` 是整数参数, 采样后会转换为实际写入整数值; Morris 分析必须使用实际写入值矩阵, 不能用未整数化的原始采样矩阵。
- smoke 规模: `r = 2`, 13 个参数时共 `2 * (13 + 1) = 28` 个模型运行, 用于检查采样, 回写, 并行调度和输出解析。
- formal 规模: `r = 150`, 13 个参数时共 `2100` 个模型运行, 作为正式敏感性分析规模。
- Hu 文献中的 `r = 500` 仅作为文献参考和未来可选扩展, 当前不作为运行目标。
- 分析默认输出 `mu`, `mu_star`, `sigma`, `mu_star_conf`; 主要排序使用 `mu_star`, `sigma` 用于判断非线性和交互影响。

### 并行执行边界和产物结构

并行运行必须满足以下执行边界:

- 使用 `concurrent.futures` 调度多个样本运行, 每个样本在独立运行目录中调用 `2dMAIZSIM.exe`.
- 代码默认 `max_workers = min(8, os.cpu_count() or 1)`, 可通过命令行覆盖; 本算例 smoke 和 formal 推荐显式设置 `--max-workers 16`, 机器资源不足时再下调.
- 每个样本目录必须从 `Loam2D` 基线目录复制生成, 并在启动前清理旧输出文件, 避免读取基线残留结果。
- 每个样本目录中的 `run.dat` 必须改写为指向该样本目录内的输入和输出文件; 不允许多个样本共享同一个基线 `run.dat` 或输出路径。
- 每个样本运行必须记录 `sample_id`, `trajectory_id`, `step_id`, `changed_parameter`, 实际写入参数值, 运行状态, 退出码, 耗时, 标准输出路径和标准错误路径。
- 模型退出码非 0, 关键输出文件缺失, 或指标解析失败时, 样本状态记为 `failed`, 错误写入 `failures.csv`; 默认不把失败样本静默用于 Morris 指标计算。

推荐输出目录结构:

```text
sensitivity_runs/<analysis_id>/
  samples.csv
  sampling_summary.csv
  rejected_designs.csv
  manifest.csv
  outputs.csv
  failures.csv
  slow_samples.csv
  morris_indices.csv
  samples/
    sample_000001/
    sample_000002/
```

### 下一步实现计划

新对话开始实现敏感性分析时, 应按以下顺序推进, 先完成 smoke 闭环, 再扩大到 formal。

1. 读取配置和依赖环境.

   - 先执行 `pixi info`, 确认使用仓库根目录的 `pixi.toml` 和 `default` 环境.
   - 确认 `SALib` 可导入: `from SALib.sample import morris` 和 `from SALib.analyze import morris`.
   - 读取 `sensitivity_parameter_bounds.toml`, 校验 13 个参数, 5 个输出指标, `morris_defaults`, `parallel_execution`.

2. 新增敏感性分析脚本.

   - 建议新增独立脚本: `示例输入/ExcelInterface-master/maizsim_run_sensitivity.py`.
   - 如果实现拆分较多, 可新增包目录: `示例输入/ExcelInterface-master/tools/maizsim_sensitivity/`.
   - 脚本入口应支持命令行参数: `--bounds`, `--mode smoke|formal`, `--analysis-id`, `--max-workers`, `--dry-run`.
   - 所有 Python 运行命令必须使用 `pixi run python ...`.

3. 生成 Morris 样本.

   - 使用 `SALib.sample.morris.sample`.
   - `problem.names` 来自 TOML 的参数名.
   - `problem.bounds` 来自 TOML 的 `lower` 和 `upper`.
   - 默认使用 `num_levels=4`, `seed=20260429`.
   - `smoke` 使用 `r=2`, 生成 28 个模型运行.
   - `formal` 使用 `r=150`, 生成 2100 个模型运行.
   - `JuvenileLeaves` 采样后必须转换为整数, 并在 `samples.csv` 中同时记录原始采样值和实际写入值.
   - 采样后必须校验实际写入值仍保持 Morris 单参数步进结构; 若整数化导致某一步没有实际参数变化, 应将整套设计作为 rejected design 并用递增 seed 重采样。超过 `rejection_max_attempts` 后再停止。

4. 为每个样本准备独立运行目录.

   - 每个样本目录从 `Loam2D` 基线目录复制.
   - 样本目录命名遵循 `samples/sample_000001` 这类稳定格式.
   - 启动模型前清理该样本目录内旧输出文件和旧日志.
   - 必须改写样本目录中的 `run.dat`, 确保所有输入和输出路径都指向样本目录自身.
   - 不允许多个样本共享同一个 `Loam2D` 基线目录运行.

5. 回写参数.

   - 作物参数写入 `PI34M91.var`.
   - 土壤参数写入 `Loam_200cm.soi`.
   - `thetaR` 同步写 `thr` 和 `tha`.
   - `thetaS` 同步写 `ths`, `th`, `thm`, `thk`.
   - `Ks` 同步写 `Ks` 和 `Kk`.
   - 回写后立即校验约束: `0 <= thetaR < thetaS < 1`, `Alfa > 0`, `n > 1`, `Ks > 0`, `Diffx >= 0`, `Diffz >= 0`.

6. 并行运行模型.

   - 使用 `concurrent.futures` 实现并行调度.
   - 代码默认 `max_workers = min(8, os.cpu_count() or 1)`, 命令行可覆盖; 本算例推荐显式使用 `--max-workers 16`.
   - `smoke` 和 `formal` 都必须走并行调度, 不能写成串行特例.
   - 每个样本独立调用该目录内的 `2dMAIZSIM.exe run.dat`.
   - 每个样本记录 `stdout.txt`, `stderr.txt`, 退出码, 耗时, 开始时间和结束时间.
   - 超时按 TOML 的 `timeout_seconds` 处理, 失败写入 `failures.csv`.
   - 成功但耗时大于等于 `slow_seconds` 的样本写入 `slow_samples.csv`, 默认不继续计算 Morris 指标.

7. 解析 7 个输出指标.

   - `max_lai`: 从 `LOAM2D.g01` 的 `LAI` 取生长期最大值.
   - `final_shoot_dm`: 从 `LOAM2D.g01` 的 `shootDM` 取首次 `Matured` 记录; 若没有成熟, 取最后一条并标记 `matured=false`.
   - `final_ear_dm`: 从 `LOAM2D.g01` 的 `earDM` 取首次 `Matured` 记录; 若没有成熟, 取最后一条并标记 `matured=false`.
   - `mean_top20_theta`: 从 `LOAM2D.G03` 中筛选 `Y <= 20 cm` 节点, 按 `Area` 加权得到每日 `thNew`, 再取时间均值.
   - `seasonal_transpiration_deficit`: 从 `LOAM2D.G05` 最后一日计算 `1 - SeasATran / SeasPTran`, 当 `SeasPTran <= 0` 时记为缺失.
   - `seasonal_potential_transpiration`: 从 `LOAM2D.G05` 的 `SeasPTran` 取生长期最后一日累计值.
   - `seasonal_actual_transpiration`: 从 `LOAM2D.G05` 的 `SeasATran` 取生长期最后一日累计值.

8. 输出结果文件.

   - `samples.csv`: 每个样本的 Morris 参数值和实际写入值.
   - `sampling_summary.csv`: 接受的采样 seed, 尝试次数和拒绝的 Morris 设计数量.
   - `rejected_designs.csv`: 若发生拒绝采样, 记录每次被拒绝设计的第一个高危样本和原因.
   - `manifest.csv`: 每个样本的目录, 轨迹编号, 步编号, 改变参数, 运行状态和耗时.
   - `outputs.csv`: 每个成功样本的 7 个指标.
   - `failures.csv`: 每个失败样本的失败阶段和错误原因.
   - `slow_samples.csv`: 每个成功但明显变慢样本的运行记录.
   - `morris_indices.csv`: 每个指标对应的 `mu`, `mu_star`, `sigma`, `mu_star_conf`.

9. 计算 Morris 指标.

   - 使用 `SALib.analyze.morris.analyze`.
   - 传入分析接口的 `X` 必须是实际写入值矩阵, 即 `samples.csv` 中的 `actual_*` 列, 并设置 `scaled=true`.
   - 每个输出指标单独计算一张敏感性结果表.
   - 排序主依据为 `mu_star`.
   - `sigma` 用于判断非线性或参数交互影响.
   - 若任一 required 指标存在失败或缺失样本, 默认不计算该指标的正式 Morris 结果, 先修复失败原因.

10. 最小验证流程.

   - 先运行 `--mode smoke --max-workers 16`.
   - 验证 28 个样本目录全部独立, 不覆盖基线目录.
   - 验证 `samples.csv`, `manifest.csv`, `outputs.csv`, `morris_indices.csv` 均生成.
   - 验证 `failures.csv` 为空或失败原因清晰可复现.
   - smoke 通过后再运行 formal。

本算例的 13 个参数不是完全同质的连续变量, 实现采样和回写时必须保留以下特殊处理:

- `JuvenileLeaves` 是整数/离散参数, 采样后必须四舍五入或映射到允许整数值, 并记录实际写入值。
- `thetaR` 代表残余含水量时需要同步写 `thr` 和 `tha`, 且必须满足 `0 <= thetaR < thetaS`。
- `thetaS` 需要同步写 `ths`, `th`/`thm` 和 `thk`, 且必须满足 `thetaR < thetaS < 1`。
- `Ks` 需要同步写 `Ks` 和 `Kk`, 保持当前近饱和导水率连接关系。
- `Alfa` 和 `Ks` 必须为正值, `n` 必须大于 1, `Diffx` 和 `Diffz` 必须非负。
- `PhyllFrmTassel` 是物候事件阈值参数, 响应可能出现阶跃或不平滑, 解释 `mu*` 时需要结合物候日期变化。
- `DaylengthSensitive` 是 0/1 布尔开关, 不纳入连续 Morris 参数; 如需分析, 应单独做情景对比。
- 敏感性批量运行默认使用日输出, 但天气仍为小时驱动, 所有样本必须保持相同输出和天气设置。

不建议在第一轮中把 `Kk` 和 `thk` 作为独立 Morris 参数。`Kk` 和 `thk` 在源码中也是连续实数, 但它们是近饱和导水率连接参数。当前单层壤土基线没有独立近饱和实测点, 因此建议在扰动 `Ks` 时令 `Kk` 同步变化, 在扰动 `ths` 时令 `thk` 同步变化, 以保持导水率曲线连接关系稳定。

`DaylengthSensitive` 是 C++ `bool` 类型的 0/1 开关, 不适合按 +/-10% 连续扰动。若需要分析日长敏感性, 应单独设置情景对比。

`RRRM`, `RRRY`, `RVRL`, `VelZ`, `ConstI_M` 等参数在 `cultivar_corn.xlsx` 的说明中标注为通常不修改或通常不用, 因此不纳入第一轮推荐参数集。

源码依据:

- 作物 `.var` 文件读入: `Crop source/controller.cpp` 中读取 `genericLeafNo`, `DayLengthSensitive`, `stayGreen`, `LM_min`, `Rmax_LTAR`, `Rmax_LIR`, `PhyllochronsToSilk`。
- 作物参数类型: `Crop source/initinfo.h` 中 `genericLeafNo` 为 `int`, `DayLengthSensitive` 为 `bool`, `Rmax_LIR`, `Rmax_LTAR`, `LM_min`, `PhyllochronsToSilk` 为 `double`。
- 根系扩散参数读入: `Soil Source/root_diff_new.for` 中读取 `DMolx`, `DMolz`, `Vel`; Fortran 默认实数类型为 `REAL`。
- 土壤水力参数读入: `Soil Source/SETMAT01.FOR` 中 `Par(1..9)` 对应 `thr`, `ths`, `tha`, `thm`, `Alfa`, `n`, `Ks`, `Kk`, `thk`; `Par` 为 Fortran 默认 `REAL`。

## 二维设置

`GridRatio` 表中 `Loam_200cm.soi` 继承 WYE07 的二维网格比例:

- `SR1=1.6`
- `IR1=0.05`
- `SR2=2.1`
- `IR2=2`
- `PlantingDepth=10`
- `XLimitRoot=23`
- `BottomBC=-7`, 即 free drainage。
- `GasBCTop=-4`
- `GasBCBottom=1`

因此该算例不是一维桶模型, 而是单层均质土壤的二维剖面网格。

## 生成命令

在仓库根目录运行:

```powershell
pixi run python "示例输入/ExcelInterface-master/maizsim_generate_inputs.py" --config "示例输入/ExcelInterface-master/maizsim_input_loam2d.toml"
```

生成后进入:

```powershell
示例输入/ExcelInterface-master/Example input/SingleLayerLoam2D/Loam2D
```

运行模型:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

## 结果核查

修订后模型可以完整运行, 并在作物端达到生理成熟。最近一次核查结果(日输出):

- 模型退出码为 `0`, 控制台输出 `Physiological maturity` 和 `Completing crop simulation...`。
- 生理成熟出现在 `2007-09-28 20:00`。
- `LOAM2D.g01` 共有 3213 条作物小时记录, 最后一条为 `Matured`。
- LAI 峰值为 `4.56`, 成熟时约 `0.04`。
- 成熟时 `totalDM=500.238`, `shootDM=402.114`, `earDM=279.42`, `rootDM=98.124`。
- 日输出后 `LOAM2D.G03` 约 `6.10 MB`, `LOAM2D.G07` 约 `4.62 MB`, `LOAM2D.G05` 约 `65.9 KB`, `LOAM2D.G06` 约 `47.7 KB`。
- `2DSOIL03.LOG` 和 `createError.log` 均为空。
- `LOAM2D.wea` 中 `RH` 范围为 `23.75-100`, 没有 `RH>100`。

仍需注意的输出列:

- `MxRtDep` 全程为 `0`, 不是根系没有生长, 而是源码中 `SHOOTR->MaxRootDepth` 没有被根系模块维护。根系判断应优先使用 `LOAM2D.G04` 的二维根量/根密度, 或用后处理从 `RMassM+RMassY` 计算根深。
- `LOAM2D.G06` 的 `Shadow` 是未限幅的原始几何影长, 在低太阳高度附近可能出现极大正负值。敏感性分析不应使用该列作为结果指标。
- `LOAM2D.G03` 中饱和或近饱和节点的 `CO2Conc/O2Conc` 可能出现极端 ppm 值, 因为气相体积趋近于零时浓度换算会失真。通用敏感性分析不应直接使用饱和节点气体 ppm。
- 极干节点的 `hNew` 可低于 `hCritA=-1E5`, 因为源码中 `hCritA` 不是全域硬下限。水分响应建议优先使用 `ThetaAvail`, `waterstress`, 蒸腾和产量/生物量指标。
