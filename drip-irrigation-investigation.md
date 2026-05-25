# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-24

最新更新：2026-05-25

## 当前结论

如果目标只是把滴灌水量接入MAIZSIM，并在季节尺度上检查水量闭合、作物根区水分响应和压力修正，那么上一版“有界地表源项重分配”已经基本够用。

如果目标是精细模拟滴灌湿润体形态，尤其要最终和HYDRUS二维`theta(x,z,t)`图对比，上一版不够，必须改。本轮先补上了“HYDRUS SurfaceDrip地表宽度曲线约束+MAIZSIM内部二维水分/根系响应诊断”的验证基础，并把滴灌扩展为两个模式：

- `DripSpreadMode=0`：保留原来的入渗受限触发扩展模式，用`RO`信号判断是否需要向相邻地表节点扩展。
- `DripSpreadMode=1`：新增HYDRUS SurfaceDrip宽度曲线标定模式，不再等待`RO`触发，而是按累计有效供水时间查HYDRUS SurfaceDrip公开算例的时间-湿润宽度曲线，主动确定当前地表湿润宽度，并在活动范围内按横向距离加权分配滴灌通量。

当前最重要的判断是：

- 滴灌对二维土壤水分场有明确作用；二维`Delta theta = drip - baseline`图显示增湿峰值位于滴灌节点正下方。
- 根系二维图已经叠加到水分增量图中，能判断增湿区和根区是否重叠。
- 新精细模式可以让壤土、砂壤土在短时HYDRUS SurfaceDrip宽度对照算例中达到“当前网格可表达的HYDRUS目标宽度”。
- 这仍不是完整HYDRUS有限元模型，也不是地下埋设滴头源项模型；它是MAIZSIM地表边界上的HYDRUS校准近似。
- 当前还不能声称“已完成MAIZSIM二维湿润体形态与HYDRUS二维图的直接对比”，因为本轮没有HYDRUS二维含水量场`theta(x,z,t)`作为参考。

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
4. 在当前地表边界离散节点中，寻找不超过目标宽度的最大对称活动范围。
5. 对活动范围内节点按横向距离给权重，中心节点权重最高，边缘节点权重较低。
6. 按权重分配`DripRate`、`DripDemand_Rate`和`DripPressureLoss_Rate`，保持水量守恒。

此外：

- Fortran端现在按字段数严格解析`.drp`事件行，只接受6、11、12或13字段；7到10字段、超过13字段、或13字段中出现非数字`DripSpreadMode`都会停止并报错。
- `DripSpreadMode=1`会把HYDRUS曲线拐点`0.03`、`0.05`、`0.10`、`0.20`、`0.30`、`0.50`、`1.00`、`2.00 h`加入`tNext`同步，减少早期湿润宽度跳变。这个同步仍按事件真实经过时间触发；当`PressureFactor < 1`时，它是数值辅助，不等于按累计有效供水时间精确触发每个HYDRUS曲线拐点。

这样做的含义是：湿润范围由累计有效供水时间查询HYDRUS SurfaceDrip宽度曲线驱动，实际可达到的宽度由MAIZSIM地表网格分辨率决定。

2026-05-25补充：上一版使用`EffectiveHours = ElapsedHours * PressureFactor`，在压力因子随时间变化时可能把已经形成的目标宽度向回缩。本版改为累计有效供水时间后，压力不足只会降低后续扩展速率，不会把已累计的有效供水时间清零或缩小。

### Python输入与验证链路

核心文件：

- `DA_Framework/da_framework/hydrus_drip_calibration.py`
- `DA_Framework/da_framework/drip_validation.py`
- `DA_Framework/da_framework/drip_precision_validation.py`
- `DA_Framework/da_framework/drip_regression.py`
- `示例输入/ExcelInterface-master/tools/maizsim_inputs/drip.py`

当前Python链路已经支持：

- 从Excel输入读取`DripSpreadMode`、`SpreadMode`或`WettingMode`。
- 校验`DripSpreadMode`只能为`0`或`1`。
- 写出13字段`.drp`。
- 解析6字段、11字段、12字段和13字段`.drp`。
- 在真实模型回归矩阵中默认写入`DripSpreadMode=1`，用于精细湿润体验证。
- 用`drip_precision_validation.py`复现45算例矩阵、HYDRUS曲线节点宽度表、可输出短时模型宽度对照、二维`Delta theta`根系叠加图和二维形态指标图。

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

## 已完成验证

### 构建和单元测试

命令：

```powershell
pixi run --manifest-path pixi.toml python -m unittest discover -s DA_Framework\tests
```

结果：

- 70个测试通过。

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
| `DripDemand - DripInput - DripPressureLoss`最大绝对残差 | `7.62e-15 mm` | pass |
| 湿润宽度上限越界数 | `0` | pass |
| `DripInput`总量 | `3116.079 mm` | pass |
| `DripDemand`总量 | `3116.232 mm` | pass |
| `DripPressureLoss`总量 | `0.153 mm` | pass |
| `DripHydraulicExcess`总量 | `3.004 mm` | pass |
| 非baseline `Runoff`总量 | `151.185 mm` | diagnostic |

按土壤汇总：

| 土壤 | 最大实际湿润宽度 | 最大湿润节点数 | 配置上限 | 说明 |
| --- | --- | --- | --- | --- |
| `sandy_loam` | `16.29 cm` | `5` | `16.3 cm` | 部分网格/多节点场景可接近上限；宽网格单滴头有3个单节点算例，只能表达中心段宽度。 |
| `loam` | `39.163 cm` | `10` | `39.7 cm` | 基本网格可达到全地表`38.1 cm`，宽网格多滴头场景可到`39.163 cm`。 |
| `clay_loam` | `19.31 cm` | `5` | `20.0 cm` | fallback上限内扩展，伴随径流和水力超量。 |

关键解释：

- 当前45矩阵证明了新精细模式不会破坏水量闭合，也不会超过配置湿润宽度上限。
- 壤土最大宽度接近`39.7 cm`，这是因为HYDRUS SurfaceDrip公开图中壤土2 h饱和半径约`19.85 cm`，映射到地表全宽就是`39.7 cm`。它看起来横向很宽，但在当前采用的HYDRUS SurfaceDrip地表宽度目标下是预期行为，不等于二维`theta`场已经匹配HYDRUS。
- 砂壤土宽度上限小得多，基础网格可表达为`15.08 cm`，宽网格某些单滴头算例只能表达为中心节点`6.05 cm`，这是网格分辨率限制。

### HYDRUS SurfaceDrip短时宽度对照

验证脚本：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.drip_precision_validation
```

输出：

- `tmp/codex_precision_drip_validation/precision_hydrus_curve_width.csv`
- `tmp/codex_precision_drip_validation/precision_hydrus_curve_model_width.csv`
- `tmp/codex_precision_drip_validation/precision_hydrus_curve_width.png`
- `tmp/codex_precision_drip_validation/precision_short_hydrus_width.csv`
- `tmp/codex_precision_drip_validation/precision_short_hydrus_width.png`
- `tmp/codex_precision_drip_validation/precision_pressure_width_diagnostics.csv`

曲线节点覆盖：

- `precision_hydrus_curve_width.csv`记录2种HYDRUS标定土壤、3种网格、8个HYDRUS曲线时间节点，共48条目标宽度和网格可表达宽度记录。
- `precision_hydrus_curve_model_width.csv`对模型稳定可输出的`0.5 h`、`1.0 h`、`2.0 h`做端到端运行，共18个短时模型算例。
- 18个短时模型算例中，MAIZSIM实际最大宽度与网格可表达目标的最大误差为`0.0005 cm`。
- 连续HYDRUS目标与网格可表达目标的最大差值为`13.31 cm`，状态记为`review`，说明这是网格离散能力限制，不是水量闭合错误。

2 h短时对照结果：

| 土壤 | 网格 | HYDRUS目标宽度 | 网格可表达目标 | MAIZSIM实际最大宽度 |
| --- | --- | --- | --- | --- |
| `loam` | `narrow_x075` | `39.7 cm` | `28.575 cm` | `28.575 cm` |
| `loam` | `base_x100` | `39.7 cm` | `38.100 cm` | `38.100 cm` |
| `loam` | `wide_x125` | `39.7 cm` | `34.5625 cm` | `34.563 cm` |
| `sandy_loam` | `narrow_x075` | `16.3 cm` | `11.310 cm` | `11.310 cm` |
| `sandy_loam` | `base_x100` | `16.3 cm` | `15.080 cm` | `15.080 cm` |
| `sandy_loam` | `wide_x125` | `16.3 cm` | `6.050 cm` | `6.050 cm` |

判断：

- MAIZSIM实际宽度和“网格可表达目标”一致，最大误差`0.0005 cm`。
- 不能要求MAIZSIM在粗网格上严格等于连续HYDRUS半径，因为地表边界宽度是离散段。
- 宽网格砂壤土单节点现象不是水量失败，而是下一圈对称节点宽度会超过`16.3 cm`上限，所以只能停在中心节点。

### MAIZSIM内部二维水分和根系响应诊断

输出：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`
- `tmp/codex_precision_drip_validation/precision_spatial_shape_metrics.png`
- `tmp/codex_precision_drip_validation/precision_spatial_delta_root.csv`

图中标识：

- 红色倒三角：滴灌地表位置。
- 红色虚线：滴灌节点横向坐标。
- `drip node 7`：本次代表算例使用的滴灌节点。
- 填色：`Delta theta = drip - baseline`。
- 青色等值线：作物根系分布。

2007-06-01基础网格高强度单滴头结果：

下表指标均来自MAIZSIM内部`drip - baseline`，不是MAIZSIM-HYDRUS差值。

| 土壤 | 峰值`Delta theta` | 峰值距滴头偏移 | 正增湿面积 | 正增湿最大深度 | 深宽比 | 根区加权`Delta theta` |
| --- | --- | --- | --- | --- | --- | --- |
| `sandy_loam` | `0.1329` | `0.0 cm` | `1546.47 cm2` | `55.0 cm` | `1.44` | `0.0091` |
| `loam` | `0.1308` | `0.0 cm` | `2210.62 cm2` | `55.0 cm` | `1.44` | `0.0193` |
| `clay_loam` | `0.1960` | `0.0 cm` | `735.69 cm2` | `35.0 cm` | `1.36` | `0.0102` |

判断：

- 三种土壤的水分增量峰值都在滴灌节点正下方，说明滴灌位置和二维水分响应一致。
- 壤土和砂壤土的正增湿范围较深，黏壤土更集中在浅层且有更强表层增湿，这与导水率差异和径流诊断一致。
- 根系等值线与正增湿区有重叠，且根区加权`Delta theta`均为正，说明滴灌效应不是只停留在地表诊断列。
- 这里的二维图是MAIZSIM内部`滴灌 - baseline`对照，不是`MAIZSIM - HYDRUS`对照。它能回答“滴灌在MAIZSIM里是否产生局部水分响应”，不能单独证明“湿润体形态已经匹配HYDRUS二维图”。
- `positive_delta_x_span_cm`表示长期模拟后水分影响范围，不等于地表滴灌源项宽度；例如壤土和砂壤土可以出现较宽的正增湿影响范围，但这不代表地表源项宽度超过了HYDRUS上限。

图像质量检查：

- `precision_case_widths.png`、`precision_hydrus_curve_width.png`、`precision_short_hydrus_width.png`、`precision_delta_theta_root_overlay_0601.png`、`precision_spatial_shape_metrics.png`均已生成。
- 五张PNG非空，像素标准差分别约为`0.135`、`0.131`、`0.185`、`0.133`、`0.208`。
- 人工查看确认坐标轴、图例、滴灌位置标识和根系等值线可读。
- 图像质量检查只证明当前诊断图可读、非空，不证明HYDRUS二维形态匹配。

关键检查项：

| 检查项 | 数值 | 状态 |
| --- | --- | --- |
| HYDRUS曲线节点模型宽度最大误差 | `0.0005 cm` | pass |
| 连续HYDRUS宽度未被网格表达的最大差值 | `13.31 cm` | review |
| 压力补偿活动期宽度回缩算例数 | `0` | pass |
| 出现压力损失的压力补偿算例数 | `3` | diagnostic |
| 正增湿二维记录数 | `3` | pass |
| 峰值距滴头最大偏移 | `0.0 cm` | pass |
| 正增湿面积非空记录数 | `3` | pass |
| 根区加权`Delta theta`为正记录数 | `3` | pass |

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
- 壤土和砂壤土短时算例能达到当前网格可表达的HYDRUS目标宽度。
- 二维土壤水分图显示滴灌节点下方出现局部增湿。
- 根系二维图可以用于判断滴灌增湿区和根区的空间关系。

若要把结论升级为“与HYDRUS二维湿润体形态对比通过”，还需要补充：

- HYDRUS同条件二维`theta(x,z,t)`输出。
- 同一初始含水量、同一土壤水力参数、同一流量、同一施水量、同一几何边界。
- 对比指标至少包括地表湿润宽度、最大湿润深度、湿润面积、峰值位置、形态长宽比、阈值湿润区重叠度，以及`theta`场的MAE或RMSE。

## 后续建议

短期建议：

- 把`tmp/codex_precision_drip_validation/`下的CSV和PNG作为当前审计工件保留。
- 若要写论文或报告，明确区分“HYDRUS曲线校准的地表边界近似”和“完整HYDRUS二维流场复现”。
- 为砂壤土宽网格单节点问题补一组更细地表网格，以证明这是离散宽度限制。
- 若要让图更接近HYDRUS二维剖面，应增加同等初始含水量、同等流量、同等施水量、无作物或固定根系的短时对照算例。
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
