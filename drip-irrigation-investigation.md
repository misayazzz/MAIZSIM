# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-24

最新更新：2026-05-26

## 当前结论

如果目标只是把滴灌水量接入MAIZSIM，并在季节尺度上检查水量闭合、作物根区水分响应和压力修正，那么上一版“有界地表源项重分配”已经基本够用。

如果目标是精细模拟滴灌湿润体形态，尤其要最终和HYDRUS二维`theta(x,z,t)`图对比，上一版不够，必须改。本轮先补上了“HYDRUS SurfaceDrip地表宽度曲线约束+MAIZSIM内部二维水分/根系响应诊断”的验证基础，并把滴灌扩展为两个模式：

- `DripSpreadMode=0`：保留原来的入渗受限触发扩展模式，用`RO`信号判断是否需要向相邻地表节点扩展。
- `DripSpreadMode=1`：新增HYDRUS SurfaceDrip宽度曲线标定模式，不再等待`RO`触发，而是按累计有效供水时间查HYDRUS SurfaceDrip公开算例的时间-湿润宽度曲线；随后把连续目标湿润区间与MAIZSIM地表边界控制区间求交，允许边缘边界段部分覆盖，并按“覆盖宽度×横向距离权重”分配滴灌通量。

当前最重要的判断是：

- 滴灌对二维土壤水分场有明确作用；二维`Delta theta = drip - baseline`图显示增湿峰值位于滴灌节点正下方。
- 根系二维图已经叠加到水分增量图中，能判断增湿区和根区是否重叠。
- 新精细模式可以让壤土、砂壤土在短时HYDRUS SurfaceDrip宽度对照算例中接近“当前有限地表范围和边界控制段可表达的HYDRUS目标宽度”，并避免粗网格下只能按完整边界段跳变。
- 这仍不是完整HYDRUS有限元模型，也不是地下埋设滴头源项模型；它是MAIZSIM地表边界上的HYDRUS校准近似。
- 已新增官方HYDRUS Drip1/Drip2工程输出解析入口，可以从`.h3d3`中的`MESHTRIA.000`和`th.out`直接导出HYDRUS二维`theta(x,z,t)`、网格CSV、形态指标和PNG图。
- 当前仍不能声称“已完成MAIZSIM二维湿润体形态与HYDRUS二维图的直接对比”。原因已经从“没有HYDRUS二维场”变为“已有官方HYDRUS二维场，但尚未构造同几何、同土壤、同初始条件、同流量、同边界的MAIZSIM专用算例”。官方Drip1/Drip2是`Kat=1`轴对称算例，而当前MAIZSIM回归矩阵主要是`KAT=2`平面剖面作物天气算例，不能直接硬比。

## 为什么必须这样改

HYDRUS的SurfaceDrip思想不是固定给一个地表节点长期灌水，也不是无限制横向铺开。公开资料中，地表滴灌会先施加到滴头附近边界；当给定通量超过土壤接纳能力时，地表湿润区随时间扩展，并最终趋向稳定面积。Lazarovitch等2023年展示了两个土壤的差异：砂壤土较快达到稳定半径，壤土需要更长时间。

因此，若要和HYDRUS二维图对比，代码层面至少要满足三点：

- 有可核对的目标湿润宽度曲线，而不是只靠`RO`被动触发。
- 有网格离散后的目标宽度检查，因为MAIZSIM地表边界是离散节点，不能表达任意连续半径。
- 有MAIZSIM二维土壤水分图用于内部诊断；若要真正对比HYDRUS，还需要HYDRUS同条件二维`theta`场。

本轮实现解决的是这个目标的第一步：把地表源项宽度从经验触发改成可核对的HYDRUS派生曲线，并用MAIZSIM内部二维图检查滴灌效应。若要完成强意义上的HYDRUS二维图对比，还需要HYDRUS同条件二维参考场和形态指标。

## 当前代码实现

### Fortran核心

核心文件：

- `Soil Source/Drip.FOR`

当前`.drp`事件行兼容4种格式：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode
```

字段含义：

- `wAppl`按`cm/hr`输入，Fortran内部换算为`cm/day`。
- `DripWetWidthMax`单位为`cm`，表示单个滴头允许达到的最大地表湿润宽度。
- `DripSpreadMode=0`表示原有入渗受限触发模式。
- `DripSpreadMode=1`表示HYDRUS SurfaceDrip宽度曲线标定模式。

`DripSpreadMode=1`的计算流程：

1. 对每个事件和滴头保存`DripEffHours`、`DripLastTime`和`DripLastPressure`。
2. 每次模型步进时先计算压力修正因子`PressureFactor`；再用上一时间段的`DripLastPressure`乘以真实经过时间，累加为`DripEffHours`。
3. 调用`DripTargetWidth(MaxWetWidth, DripEffHours)`得到连续目标湿润宽度。
4. 以滴头节点横坐标为中心构造连续目标区间`[x - TargetWetWidth / 2, x + TargetWetWidth / 2]`。
5. 按相邻地表节点中点重构每个表面边界控制区间，计算目标区间与控制区间的覆盖宽度`CoverWidth`；边缘边界段可只覆盖一部分。
6. 对覆盖区间内节点按横向距离给权重，中心节点权重最高，边缘节点权重较低。
7. 用`NodeWeight * CoverWidth`归一化，并在写入边界通量密度时除以该边界段完整`Width(k)`，使`sum(DripRate(k) * Width(k)) = SourceFlux`严格守恒。

此外：

- Fortran端现在按字段数严格解析`.drp`事件行，只接受6、11、12或13字段；7到10字段、超过13字段、或13字段中出现非数字`DripSpreadMode`都会停止并报错。
- `DripSpreadMode=1`会把HYDRUS曲线拐点`0.03`、`0.05`、`0.10`、`0.20`、`0.30`、`0.50`、`1.00`、`2.00 h`加入`tNext`同步，减少早期湿润宽度跳变。这个同步仍按事件真实经过时间触发；当`PressureFactor < 1`时，它是数值辅助，不等于按累计有效供水时间精确触发每个HYDRUS曲线拐点。

这样做的含义是：湿润范围由累计有效供水时间查询HYDRUS SurfaceDrip宽度曲线驱动，实际可达到的宽度由有限地表范围和MAIZSIM地表边界控制段决定。它比“完整边界段求和”更接近连续HYDRUS目标，但仍不是把有限元边界真正切成子段；边缘部分覆盖在MAIZSIM中表现为该完整边界段整体通量密度按覆盖比例降低。

2026-05-25补充：上一版使用`EffectiveHours = ElapsedHours * PressureFactor`，在压力因子随时间变化时可能把已经形成的目标宽度向回缩。本版改为累计有效供水时间后，压力不足只会降低后续扩展速率，不会把已累计的有效供水时间清零或缩小。

2026-05-25补充：上一版`DripSpreadMode=1`仍用完整表面边界段表达目标宽度，粗网格下会出现`16.3 cm`目标只能表达为`6.05 cm`或`15.08 cm`的问题。本版改为部分覆盖边界控制段后，砂壤土`16.3 cm`目标在基础网格和宽网格都可表达为`16.3 cm`，窄网格因端点舍入表达为`16.29625 cm`；壤土仍会因为滴头靠近左边界、目标区间超出有限地表范围而被域边界裁剪。

### Python输入与验证链路

核心文件：

- `DA_Framework/da_framework/hydrus_drip_calibration.py`
- `DA_Framework/da_framework/hydrus_official_export.py`
- `DA_Framework/da_framework/drip_validation.py`
- `DA_Framework/da_framework/drip_precision_validation.py`
- `DA_Framework/da_framework/hydrus_2d_comparison.py`
- `DA_Framework/da_framework/drip_regression.py`
- `示例输入/ExcelInterface-master/tools/maizsim_inputs/drip.py`

当前Python链路已经支持：

- 从Excel输入读取`DripSpreadMode`、`SpreadMode`或`WettingMode`。
- 校验`DripSpreadMode`只能为`0`或`1`。
- 写出13字段`.drp`。
- 解析6字段、11字段、12字段和13字段`.drp`。
- 在真实模型回归矩阵中默认写入`DripSpreadMode=1`，用于精细湿润体验证。
- 用`drip_precision_validation.py`复现45算例矩阵、HYDRUS曲线节点宽度表、逐边界段部分覆盖明细、短时模型宽度对照、二维`Delta theta`根系叠加图和二维形态指标图。
- 用`hydrus_official_export.py`从官方HYDRUS OLE工程文件或已解出的HYDRUS流文件导出二维`theta` CSV、网格节点/单元CSV、HYDRUS三联图和形态指标。
- `hydrus_2d_comparison.py`现在支持用`--maizsim-date-time`选择MAIZSIM小时输出帧；如果同一天存在多个`Date_time`而只传`--date`，工具会报错，避免把多个时刻混成一张二维场。

## HYDRUS标定口径

当前只把公开HYDRUS SurfaceDrip示例中可核对的两个土壤固化为目标曲线：

| 土壤 | HYDRUS公开条件 | 2 h饱和半径 | 2 h地表全湿润宽度 |
| --- | --- | --- | --- |
| `sandy_loam` | SurfaceDrip，`2 L/h`，总`4 L` | 约`8.15 cm` | `16.3 cm` |
| `loam` | SurfaceDrip，`2 L/h`，总`4 L` | 约`19.85 cm` | `39.7 cm` |
| `clay_loam` | 公开图无直接目标 | 无 | `20.0 cm` fallback |

解释：

- `sandy_loam`和`loam`是HYDRUS图数字化后的第一版标定。
- `clay_loam`不是HYDRUS标定值，只是为了继续覆盖低导水率入渗受限场景的fallback。
- 若`DripWetWidthMax`接近`16.3 cm`或`39.7 cm`，Fortran使用固化的HYDRUS时间-宽度表插值。
- 其它宽度走保守fallback：`MaxWetWidth * sqrt(累计有效供水小时数 / 2 h)`，再截断到`MaxWetWidth`。
- 数字化曲线已落盘到`DA_Framework/reference/hydrus_surface_drip_digitized_targets.csv`；单元测试会检查该CSV与代码中的`HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM`一致，避免后续硬编码曲线和可复核源表漂移。
- 注意：这份CSV是Figure 8曲线的第一版人工数字化记录，不是HYDRUS原始节点输出；如果要作为论文级标定，应补充原图截图、轴标定方法、取点工具和数字化误差估计。

## 已完成验证

### 构建和单元测试

命令：

```powershell
pixi run --manifest-path pixi.toml python -m unittest discover -s DA_Framework\tests
```

结果：

- 84个测试通过。

命令：

```powershell
pixi run --manifest-path pixi.toml check
```

结果：

- 配置校验通过。
- dry-run完成，未调用Excel，未改写运行文件。

命令：

```powershell
MSBuild.exe .\maizsim07.sln /p:Configuration=Release /p:Platform=x64
```

结果：

- Release构建成功。
- 0个错误。
- 73个既有C++/Fortran警告。

命令：

```powershell
git diff --check
```

结果：

- 未发现空白错误；只出现Git换行符提示。

### 45个真实模型回归算例

命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.drip_regression --workspace tmp\codex_drip_regression_precision --keep-workspace --timeout-seconds 300
```

覆盖范围：

- 3种土壤：`sandy_loam`、`loam`、`clay_loam`。
- 3种网格：`narrow_x075`、`base_x100`、`wide_x125`。
- 5类场景：`baseline`、`long_low_single`、`long_multi_node`、`long_high_single`、`long_pressure_single`。

结果：

| 检查项 | 数值 | 状态 |
| --- | --- | --- |
| 算例数量 | `45` | pass |
| `DripDemand - DripInput - DripPressureLoss`最大绝对残差 | `1.24e-14 mm` | pass |
| 湿润宽度上限越界数 | `0` | pass |
| `DripInput`总量 | `3116.078 mm` | pass |
| `DripDemand`总量 | `3116.232 mm` | pass |
| `DripPressureLoss`总量 | `0.154 mm` | pass |
| `DripHydraulicExcess`总量 | `2.969 mm` | pass |
| 非baseline `Runoff`总量 | `153.798 mm` | diagnostic |

按土壤汇总：

| 土壤 | 最大实际湿润宽度 | 最大湿润节点数 | 配置上限 | 说明 |
| --- | --- | --- | --- | --- |
| `sandy_loam` | `16.300 cm` | `8` | `16.3 cm` | 部分覆盖后不再停在单一中心段；不同网格均可接近或达到HYDRUS砂壤土上限。 |
| `loam` | `39.688 cm` | `10` | `39.7 cm` | 多滴头或宽网格场景可接近壤土上限；单滴头基础网格会因左边界裁剪停在约`32.085 cm`。 |
| `clay_loam` | `20.000 cm` | `9` | `20.0 cm` | fallback上限内扩展，伴随径流和水力超量。 |

关键解释：

- 当前45矩阵证明了新精细模式不会破坏水量闭合，也不会超过配置湿润宽度上限。
- 壤土最大宽度接近`39.7 cm`，这是因为HYDRUS SurfaceDrip公开图中壤土2 h饱和半径约`19.85 cm`，映射到地表全宽就是`39.7 cm`。它看起来横向很宽，但在当前采用的HYDRUS SurfaceDrip地表宽度目标下是预期行为，不等于二维`theta`场已经匹配HYDRUS。
- 砂壤土宽度上限小得多；部分覆盖后，粗网格边缘段可以按覆盖比例施加通量，避免了旧实现中`16.3 cm`目标被完整边界段跳变压缩为`6.05 cm`或`15.08 cm`的问题。

### HYDRUS SurfaceDrip短时宽度对照

验证脚本：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.drip_precision_validation
```

输出：

- `tmp/codex_precision_drip_validation/precision_hydrus_curve_width.csv`
- `tmp/codex_precision_drip_validation/precision_surface_partial_coverage.csv`
- `tmp/codex_precision_drip_validation/precision_hydrus_curve_model_width.csv`
- `tmp/codex_precision_drip_validation/precision_hydrus_curve_width.png`
- `tmp/codex_precision_drip_validation/precision_short_hydrus_width.csv`
- `tmp/codex_precision_drip_validation/precision_short_hydrus_width.png`
- `tmp/codex_precision_drip_validation/precision_pressure_width_diagnostics.csv`

曲线节点覆盖：

- `precision_hydrus_curve_width.csv`记录2种HYDRUS标定土壤、3种网格、8个HYDRUS曲线时间节点，共48条连续HYDRUS宽度、Fortran实际目标宽度、域裁剪宽度、旧完整段宽度和新部分覆盖宽度记录。Fortran实际目标宽度会先钳到中心边界段宽度，再截断到`DripWetWidthMax`。
- `precision_surface_partial_coverage.csv`逐边界段记录`segment_left_cm`、`segment_right_cm`、`covered_width_cm`、`covered_fraction`、`node_weight`和`flux_fraction`，用于核对边缘段覆盖比例和通量比例。这里的“部分覆盖”是有效源区面积权重；MAIZSIM并没有把边界几何真实切成子段，而是在完整边界段上按覆盖比例降低通量密度。
- `precision_hydrus_curve_model_width.csv`对模型稳定可输出的`0.5 h`、`1.0 h`、`2.0 h`做端到端运行，共18个短时模型算例。
- 18个短时模型算例中，MAIZSIM实际最大宽度与部分覆盖目标的最大误差为`0.70325 cm`。这是连续宽度曲线与模型时间步/小时输出采样之间的误差，状态为`pass`，当前容差为`0.8 cm`。
- 2 h短时算例中，MAIZSIM实际最大宽度与部分覆盖目标的最大误差为`0.302 cm`。
- 逐边界段`flux_fraction`求和最大误差为`1.11e-16`，说明部分覆盖通量分配在验证表中严格归一。
- Fortran实际目标与部分覆盖目标的最大差值为`11.12875 cm`，状态记为`review`，主要来自滴头靠近有限地表左边界时，壤土`39.7 cm`目标区间被模型边界裁剪，不是水量闭合错误。

2 h短时对照结果：

| 土壤 | 网格 | HYDRUS目标宽度 | 域裁剪目标 | 部分覆盖目标 | MAIZSIM实际最大宽度 |
| --- | --- | --- | --- | --- | --- |
| `loam` | `narrow_x075` | `39.7 cm` | `28.57875 cm` | `28.57125 cm` | `28.524 cm` |
| `loam` | `base_x100` | `39.7 cm` | `32.09500 cm` | `32.08500 cm` | `31.783 cm` |
| `loam` | `wide_x125` | `39.7 cm` | `35.15625 cm` | `35.15000 cm` | `35.003 cm` |
| `sandy_loam` | `narrow_x075` | `16.3 cm` | `16.30000 cm` | `16.29625 cm` | `16.296 cm` |
| `sandy_loam` | `base_x100` | `16.3 cm` | `16.30000 cm` | `16.30000 cm` | `16.300 cm` |
| `sandy_loam` | `wide_x125` | `16.3 cm` | `16.30000 cm` | `16.30000 cm` | `16.300 cm` |

判断：

- MAIZSIM实际宽度和“部分覆盖目标”在`0.8 cm`容差内一致；偏差来自模型时间步和小时输出对连续宽度曲线的采样。
- 不能要求MAIZSIM在有限地表范围内严格等于连续HYDRUS半径；壤土目标宽度大于滴头左侧可用地表范围时，会被域边界裁剪。
- 部分覆盖后，砂壤土宽网格单滴头不再停在中心节点`6.05 cm`，而是通过边缘段覆盖比例达到`16.3 cm`。

### MAIZSIM内部二维水分和根系响应诊断

输出：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`
- `tmp/codex_precision_drip_validation/precision_spatial_shape_metrics.png`
- `tmp/codex_precision_drip_validation/precision_spatial_delta_root.csv`

图中标识：

- 红色倒三角：滴灌地表位置。
- 红色虚线：滴灌节点横向坐标。
- 红色水平线：本次代表算例实际施加的地表滴灌源区范围。
- `drip node 7`：本次代表算例使用的滴灌节点。
- 填色：`Delta theta = drip - baseline`。
- 青色等值线：作物根系分布。

2007-06-01基础网格高强度单滴头结果：

下表指标均来自MAIZSIM内部`drip - baseline`，不是MAIZSIM-HYDRUS差值。

| 土壤 | 峰值`Delta theta` | 峰值距滴头偏移 | 正增湿面积 | 正增湿最大深度 | 深宽比 | 根区加权`Delta theta` |
| --- | --- | --- | --- | --- | --- | --- |
| `sandy_loam` | `0.1339` | `0.0 cm` | `1492.62 cm2` | `55.0 cm` | `1.44` | `0.0097` |
| `loam` | `0.1428` | `0.0 cm` | `2182.74 cm2` | `55.0 cm` | `1.44` | `0.0186` |
| `clay_loam` | `0.1910` | `0.0 cm` | `935.53 cm2` | `41.2 cm` | `1.60` | `0.0138` |

判断：

- 三种土壤的水分增量峰值都在滴灌节点正下方，说明滴灌位置和二维水分响应一致。
- 壤土和砂壤土的正增湿范围较深，黏壤土更集中在浅层且有更强表层增湿，这与导水率差异和径流诊断一致。
- 根系等值线与正增湿区有重叠，且根区加权`Delta theta`均为正，说明滴灌效应不是只停留在地表诊断列。
- 这里的二维图是MAIZSIM内部`滴灌 - baseline`对照，不是`MAIZSIM - HYDRUS`对照。它能回答“滴灌在MAIZSIM里是否产生局部水分响应”，不能单独证明“湿润体形态已经匹配HYDRUS二维图”。
- `positive_delta_x_span_cm`表示长期模拟后水分影响范围，不等于地表滴灌源项宽度；例如壤土和砂壤土可以出现较宽的正增湿影响范围，但这不代表地表源项宽度超过了HYDRUS上限。

图像质量检查：

- `precision_case_widths.png`、`precision_hydrus_curve_width.png`、`precision_short_hydrus_width.png`、`precision_delta_theta_root_overlay_0601.png`、`precision_spatial_shape_metrics.png`均已生成。
- 五张PNG非空，像素标准差分别约为`0.128`、`0.134`、`0.181`、`0.140`、`0.208`。
- 人工查看确认坐标轴、图例、滴灌节点标识、地表源区水平线和根系等值线可读。
- 图像质量检查只证明当前诊断图可读、非空，不证明HYDRUS二维形态匹配。

关键检查项：

| 检查项 | 数值 | 状态 |
| --- | --- | --- |
| HYDRUS曲线节点模型宽度最大误差 | `0.70325 cm` | pass |
| 2 h短时模型宽度最大误差 | `0.302 cm` | pass |
| 逐边界段通量比例求和最大误差 | `1.11e-16` | pass |
| Fortran实际目标未被部分覆盖表达的最大差值 | `11.12875 cm` | review |
| 压力补偿活动期宽度回缩算例数 | `0` | pass |
| 出现压力损失的压力补偿算例数 | `3` | diagnostic |
| 正增湿二维记录数 | `3` | pass |
| 峰值距滴头最大偏移 | `0.0 cm` | pass |
| 正增湿面积非空记录数 | `3` | pass |
| 根区加权`Delta theta`为正记录数 | `3` | pass |

### 官方HYDRUS二维场导出

2026-05-26补充：已经确认PC-Progress公开HYDRUS示例工程`Drip1.h3d3`和`Drip2.h3d3`内含可解析的二维含水量输出：

- `Drip1`：壤土，`Kat=1`轴对称垂向流，`theta_r=0.078`，`theta_s=0.43`，`alpha=0.036 cm^-1`，`n=1.56`，`Ks=1.04 cm/h`，`t=0..2 h`共21帧。
- `Drip2`：砂壤土，`Kat=1`轴对称垂向流，`theta_r=0.065`，`theta_s=0.41`，`alpha=0.075 cm^-1`，`n=1.89`，`Ks=4.42083 cm/h`，`t=0..2 h`共41帧。
- 两个工程共用`1532`个节点、`2927`个三角单元、`50 cm x 100 cm`剖面网格。
- `th.out`是小端`float32`连续二进制，每帧为`time_h + theta[1..NumNPD]`。
- `MESHTRIA.000`提供节点坐标和三角单元；导出工具把HYDRUS的`z_cm`转换为`depth_cm = surface_z - z_cm`。

导出命令示例：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_official_export `
  --project-file tmp\codex_hydrus_official\drip\Drip1.h3d3 `
  --output-dir tmp\codex_hydrus_official_exports `
  --prefix Drip1 `
  --output-time-h 2 `
  --wet-delta-threshold 0.005
```

输出内容：

- `Drip1_theta_baseline.csv`和`Drip1_theta_output.csv`：HYDRUS节点级`theta`场，包含`node`、`time_h`、`x_cm`、`z_cm`、`depth_cm`、`theta`、`area_cm2`。
- `Drip1_mesh_nodes.csv`和`Drip1_mesh_elements.csv`：HYDRUS网格节点和三角单元。
- `Drip1_summary.csv`：HYDRUS自身湿润体形态指标。
- `Drip1_hydrus_fields.png`：初始`theta`、输出`theta`和`Delta theta`三联图，图中标出滴头位置。
- `Drip1_hydrus_manifest.json`：土壤参数、几何类型、输出时间和形态指标。

2 h官方HYDRUS场的当前导出指标：

| 工程 | 土壤 | 初始`theta` | 输出最大`theta` | `Delta theta`最大值 | 湿润宽度 | 湿润深度 | 峰值位置 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Drip1` | 壤土 | `0.242421` | `0.430000` | `0.187579` | `28.055 cm` | `18.476 cm` | `x=0, depth=0` |
| `Drip2` | 砂壤土 | `0.122075` | `0.410000` | `0.287925` | `21.904 cm` | `23.026 cm` | `x=0, depth=0` |

这些指标使用`Delta theta >= 0.005`作为湿润区阈值，是从官方HYDRUS二维`theta`场计算出来的，不是从手工数字化曲线反推。它们和前文`16.3 cm`、`39.7 cm`曲线口径不完全等价；后者来自公开图中地表湿润半径/宽度的第一版人工数字化，前者来自官方工程节点场和指定阈值。因此后续标定不能再简单把“曲线宽度达标”当作“二维形态匹配”，必须用同一阈值和同一几何口径比较HYDRUS和MAIZSIM的`Delta theta`场。

当前不能直接把这些HYDRUS图与已有MAIZSIM回归图做结论性对比，原因如下：

- 官方HYDRUS Drip1/Drip2是`Kat=1`轴对称算例；当前45回归矩阵主要使用`KAT=2`平面剖面。
- 当前短时MAIZSIM算例仍带WYE天气、蒸发和作物时间设置；HYDRUS Drip1/Drip2是无降雨、无作物、无根系吸水的理想2 h算例。
- 现有MAIZSIM砂壤土参数和HYDRUS Drip2不完全一致，例如`theta_r`当前为`0.045`，官方HYDRUS Drip2为`0.065`。
- 水源单位还需要统一：HYDRUS是`2 L/h`、总`4 L`的SurfaceDrip工程；MAIZSIM`.drp`中的`wAppl`是边界通量深度，需要按几何和边界面积换算。

### HYDRUS二维场直接对比入口

2026-05-26补充：已新增正式模块`DA_Framework/da_framework/hydrus_2d_comparison.py`，用于接入HYDRUS二维含水量场。这个模块不是用MAIZSIM结果伪造HYDRUS参考，而是要求提供HYDRUS导出的二维CSV；该CSV现在可以由`hydrus_official_export.py`从官方Drip1/Drip2工程生成。

HYDRUS参考CSV的最小字段：

| 字段 | 含义 | 可接受列名示例 |
| --- | --- | --- |
| `x_cm` | 横向坐标，单位`cm` | `x_cm`、`x`、`X` |
| `depth_cm` | 距地表深度，单位`cm` | `depth_cm`、`depth`、`z_cm` |
| `theta` | 体积含水量 | `theta`、`theta_hydrus`、`th`、`swc` |
| `area_cm2` | 点或单元面积权重，可选 | `area_cm2`、`area`、`weight` |

如果HYDRUS CSV不含`area_cm2`，工具会用`1.0`作为点权重；此时`wet_area`和`wet_iou`只能解释为采样点权重近似，不应写成真实面积。

同条件manifest：

- 可选但强烈建议提供`--comparison-manifest`。
- 示例文件：`DA_Framework/examples/hydrus_2d_comparison_manifest.example.json`。
- manifest用于记录HYDRUS工程、MAIZSIM run、土壤水力参数、初始条件、滴头流量、总水量、事件时长、输出时刻、域尺寸、滴头坐标、边界条件和baseline定义。工具会检查这些关键字段是否存在，但不会自动证明它们与两个模型文件完全一致。

直接对比命令示例：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_2d_comparison `
  --maizsim-g03 path\to\MAIZSIM\LOAM2D.G03 `
  --hydrus-csv path\to\hydrus_theta.csv `
  --maizsim-date-time 39203.083333 `
  --maizsim-baseline-g03 path\to\baseline\LOAM2D.G03 `
  --hydrus-baseline-csv path\to\hydrus_baseline_theta.csv `
  --comparison-manifest path\to\same_condition_manifest.json `
  --drip-x-cm 12.1 `
  --drip-source-left-cm 4.1 `
  --drip-source-right-cm 20.4 `
  --output-dir tmp\codex_hydrus_2d_field_comparison
```

其中`--maizsim-date-time`用于选择MAIZSIM小时输出中的具体`Date_time`帧；如果只用`--date`而同一天有多个小时帧，工具会报错。`--drip-x-cm`标出滴头中心，`--drip-source-left-cm`和`--drip-source-right-cm`标出地表滴灌源区；三者是绘图标注参数，不参与误差计算。

输出内容：

- `hydrus_2d_comparison_summary.csv`：`theta_mae`、`theta_rmse`、`theta_bias`、`theta_corr`、`delta_theta_rmse`、湿润区面积、湿润区交并比、湿润宽度、湿润深度和峰值距离。
- `hydrus_2d_comparison_points.csv`：HYDRUS点位、插值后的MAIZSIM值、残差和可选的`Delta theta`残差。
- `hydrus_2d_comparison_fields.png`：HYDRUS、MAIZSIM和差值三联图；如果提供滴灌标注参数，图中会用红色虚线和地表线段标出滴头中心和滴灌源区。
- `hydrus_2d_comparison_manifest.json`：如果提供`--comparison-manifest`，输出目录会复制一份同条件元数据，便于审计。

当前状态：

- 工具链已经具备HYDRUS二维数值场接入口和形态指标计算。
- 单元测试使用合成场验证了CSV解析、同条件manifest字段检查、MAIZSIM `G03`深度转换、插值、`theta`误差、湿润区交并比和带滴灌标注的图像输出。
- 已具备官方HYDRUS二维`theta(x,z,t)`导出能力，但仍缺同条件MAIZSIM专用算例，因此本项目当前还不能声称“HYDRUS二维形态对比通过”。下一步应先构造Drip1-like/Drip2-like零天气、无作物、同土壤、同初始压力头、同施水量的MAIZSIM算例，再使用上述模块生成正式对比表和三联图。

### 负向解析验证

为检查Fortran端不会再静默吞掉畸形可选字段，临时把13字段`.drp`事件行最后的`DripSpreadMode`改成非数字值。模型启动后明确输出：

```text
Invalid drip event fields
```

这说明畸形13字段不会再降级为12字段并默认`DripSpreadMode=0`。

## 对“横向铺开过大”的最新解释

这个问题要分两种情况：

1. 在旧`DripSpreadMode=0`里，如果`RO`触发后没有物理上限，确实容易铺满整个地表。这个问题已经通过`DripWetWidthMax`和`RO`收紧处理过。
2. 在新`DripSpreadMode=1`里，横向铺开不是由`RO`失控造成，而是由HYDRUS目标曲线决定。壤土2 h目标全宽约`39.7 cm`，因此基础网格出现接近全地表宽度是HYDRUS对照目标本身导致的，不是代码无约束扩散。

所以，如果研究目标是“不要让横向湿润体超过现实滴灌观测”，下一步不能再靠经验缩小代码宽度，而应补充对应土壤、滴头流量、初始水分和施水量下的HYDRUS工程或实测湿润体数据，再重新标定`DripTargetWidth`曲线。

## 文献合理性审查

本次代码改动的合理性主要来自三类证据：

- HYDRUS技术说明中的SurfaceDrip边界条件不是固定单节点通量，而是在单个滴头节点不能接纳指定通量时，将超额通量逐步分配到相邻边界节点，直到整个通量被接纳；其结果是瞬态湿润面积随灌水过程逐步扩大。
- Lazarovitch等2023年的HYDRUS综述使用SurfaceDrip算例展示了`2 L/h`、总`4 L`条件下壤土和砂壤土的动态湿润半径差异：砂壤土较快达到稳定半径，壤土扩展时间更长。这支持按土壤水力性质区分湿润宽度曲线，而不是用一个固定经验宽度。
- Kandelous和Simunek关于滴灌湿润体的比较研究显示，常用经验模型把湿润体水平宽度、垂向深度表示为累计施水量`Vw`、滴头流量`Q`和饱和导水率`Ks`等变量的函数；HYDRUS-2D验证研究也强调需要用含水量场和湿润体尺寸的RMSE来评价二维形态。

由此看，本次把`ElapsedHours * 当前PressureFactor`改为累计有效供水时间是合理的：湿润体扩展应更接近累计进入土壤的水量过程，而不是由某一时刻的压力因子重新缩放整个历史灌水时间。不过，这仍只是MAIZSIM地表边界上的工程近似；要证明二维湿润体形态与HYDRUS一致，仍需同条件HYDRUS二维`theta(x,z,t)`场。

## 仍然不能声称的内容

当前实现不能声称：

- 已完整复现HYDRUS有限元二维流场。
- 已完成MAIZSIM二维湿润体形态与HYDRUS二维图的直接对比。
- 已验证所有土壤质地、所有滴头流量和所有施水量。
- 已实现地下埋设滴头源项。
- 已完成真实田间湿润锋或含水量剖面校准。
- `clay_loam=20.0 cm`是HYDRUS公开图标定值。
- 当前网格能表达任意连续湿润半径。
- 当前累计有效供水时间仍是HYDRUS SurfaceDrip宽度曲线的工程近似，不是HYDRUS压力头场、入渗能力和边界条件的完整迭代求解。

当前可以谨慎声称：

- MAIZSIM已经支持HYDRUS SurfaceDrip风格的地表湿润宽度时间曲线近似。
- 精细模式的目标湿润宽度现在由累计有效供水时间驱动，压力不足会减慢后续扩展，而不会让目标宽度随瞬时压力因子下降而回缩。
- 45个真实模型算例水量闭合、宽度不越界。
- 壤土和砂壤土短时算例能达到当前有限地表范围和部分边界覆盖可表达的HYDRUS目标宽度；壤土大目标会被模型左边界裁剪。
- 二维土壤水分图显示滴灌节点下方出现局部增湿，并已在图中标出地表滴灌源区范围。
- 根系二维图可以用于判断滴灌增湿区和根区的空间关系。

若要把结论升级为“与HYDRUS二维湿润体形态对比通过”，还需要补充：

- MAIZSIM Drip1-like/Drip2-like同条件专用算例，使用官方HYDRUS相同土壤参数、初始压力头、几何类型、施水量和输出时刻。
- 同一初始含水量、同一土壤水力参数、同一流量、同一施水量、同一几何边界。
- 用`hydrus_2d_comparison.py`生成地表湿润宽度、最大湿润深度、湿润面积、峰值位置、阈值湿润区交并比，以及`theta`场MAE/RMSE。

## 后续建议

短期建议：

- 把`tmp/codex_precision_drip_validation/`下的CSV和PNG作为当前审计工件保留。
- 把`tmp/codex_hydrus_official_exports/`下的官方HYDRUS Drip1/Drip2导出CSV和PNG作为下一轮同条件对比的参考基准。
- 若要写论文或报告，明确区分“HYDRUS曲线校准的地表边界近似”和“完整HYDRUS二维流场复现”。
- 为壤土大目标被地表边界裁剪的问题补一组更宽、滴头居中的短时网格，以区分域边界限制和真实湿润体宽度。
- 若要让图更接近HYDRUS二维剖面，应增加同等初始含水量、同等流量、同等施水量、无作物或固定根系的短时对照算例；对官方Drip1/Drip2还必须处理`Kat=1`轴对称几何和MAIZSIM边界通量单位换算。
- 若压力补偿场景成为重点，应继续增加强压力不足、脉冲压力和长时低流量算例，并考虑输出累计有效供水时间作为诊断字段。

长期建议：

- 补做更多土壤质地的HYDRUS标定曲线，不要只依赖土壤名称；应按`theta_r`、`theta_s`、`alpha`、`n`、`Ks`等水力参数分组。
- 若目标转为地下滴灌，应新增独立地下源项或边界源项，而不是复用地表`DripSpreadMode=1`。
- 若目标是田间真实性，应引入实测湿润锋、剖面含水量或滴头流量数据做参数校准。

## 参考资料

- HYDRUS特殊边界条件说明：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- Lazarovitch, N.等. 2023. Modeling of irrigation and related processes with HYDRUS. <https://www.pc-progress.com/Documents/Jirka/Lazarovitch_et_al_2023.pdf>
- Kandelous, M. M.等. 2011. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation. <https://link.springer.com/article/10.1007/s00271-009-0205-9>
- Kandelous, M. M.和Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D. <https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
- HYDRUS 2D/3D Technical Manual, Surface Drip Irrigation with Dynamic Evaluation of the Wetted Area. <https://www2.pc-progress.com/downloads/Pgm_Hydrus3D5/HYDRUS_Technical_Manual_2D3D_V5.pdf>
