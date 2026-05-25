# 精细滴灌湿润体模型设计

## 背景

当前MAIZSIM滴灌实现已经具备地表节点滴灌输入、水量诊断、压力修正和`DripWetWidthMax`宽度上限。现有验证表明滴灌会在二维含水量场中产生局部增湿，但壤土和砂壤土代表算例的实际活动宽度仍停留在中心地表边界段，约`4.84 cm`。这说明当前实现更像“有上限的地表边界源项重分配近似”，不能支撑“精细模拟滴灌二维湿润体并与HYDRUS图像对比”的结论。

目标是新增一个HYDRUS-style精细地表湿润体模式，使滴灌源区随事件进程、土壤标定宽度和网格离散动态扩展，并输出足够的数值和二维图像证据。

## 设计目标

1. 保留旧`.drp`输入和当前兼容行为，避免破坏已有算例。
2. 新增可选精细模式，用于HYDRUS二维湿润体对照。
3. 让实际地表活动宽度不是只在`RO`出现后才扩展，而是随滴灌事件时间和HYDRUS标定曲线动态增长。
4. 活动源区内的滴灌通量按距离加权分配，中心节点最大，两侧递减，避免机械式横向平均铺开。
5. G05继续报告实际活动宽度、湿润节点数、输入量、压力损失和水力超量。
6. 验证必须包含真实模型算例、二维`theta`和`delta theta`图、根系分布叠加图，以及论文依据核对。

## 非目标

1. 本轮不实现地下埋设滴头内部源项模型。
2. 本轮不重写MAIZSIM的Richards方程求解器。
3. 本轮不新增第三方数值依赖。
4. 本轮不宣称完全替代HYDRUS，只实现可审计的HYDRUS-style地表滴灌近似，并用公开HYDRUS资料和二维图像验证其合理性。

## 输入格式

旧6字段、11字段和12字段`.drp`继续有效。新增精细模式采用向后兼容扩展：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode
```

字段含义：

- `DripSpreadMode=0`：兼容模式。沿用当前`RO`触发扩展逻辑。
- `DripSpreadMode=1`：HYDRUS-style动态湿润源区模式。

如果旧输入没有`DripSpreadMode`，默认取`0`。

## HYDRUS-style动态宽度

在`DripSpreadMode=1`时，每个滴灌事件按累计有效供水时间计算目标活动宽度。累计有效时间按上一时间段压力修正因子累加，因此压力不足会减慢后续扩展，但不会让已经形成的目标宽度回缩。

基础规则：

- 事件相对时间为`elapsed_h = DripEffHours`。
- 事件总时长为`duration_h = (tAppl_stop - tAppl_start) * 24`。
- 目标宽度随事件进程单调增加，最大不超过`DripWetWidthMax`。
- 对已有HYDRUS数字化土壤目标，使用分段线性曲线：
  - 砂壤土：来自`hydrus_surface_drip_digitized_targets.csv`的`target_full_wet_width_cm`。
  - 壤土：来自同一文件的`target_full_wet_width_cm`。
- 对无HYDRUS曲线的土壤或普通输入，使用保守幂律：

```text
target_width = max(center_width, DripWetWidthMax * sqrt(progress))
progress = min(1, elapsed_h / reference_duration_h)
```

其中`reference_duration_h`默认为事件时长；如果事件时长很长，使用`2 h`作为短时标定参考，再保持上限。

网格离散规则：

- 以滴头节点横坐标为中心构造连续目标区间。
- 按相邻地表节点中点重构每个表面边界控制区间。
- 目标区间与控制区间求交得到`CoverWidth`；边缘边界段允许部分覆盖。
- 实际输出宽度为`CoverWidth`之和，而不是完整边界段`Width(k)`之和。
- 如果HYDRUS目标区间超出模型有限地表范围，实际可表达宽度会被域边界裁剪。

## 通量分配

当前实现把活动源区内的通量均匀分配为`SourceFlux / TotalWidth`。新模式改为距离加权分配。

权重定义：

```text
distance = abs(x(node) - x(center_node))
half_width = max(0.5 * TargetWetWidth, 0.5 * Width(center))
raw_weight = max(0, 1 - distance / half_width)
```

然后按覆盖面积归一化，并把结果换回完整边界段上的通量密度：

```text
weighted_area = sum(raw_weight(k) * CoverWidth(k))
DripRate(k) += SourceFlux * raw_weight(k) * CoverWidth(k) / weighted_area / Width(k)
```

这样每个时间步总输入仍严格守恒：

```text
sum(DripRate(k) * Width(k)) = SourceFlux
```

兼容模式继续使用均匀分配。

## Fortran改动范围

主要文件：

- `Soil Source/Drip.FOR`
- `Soil Source/PuSurface.ins`
- `Soil Source/OUTPUT.FOR`，仅在需要新增诊断列时修改。

核心改动：

1. 在公共数组中新增`DripSpreadMode(Max_times)`。
2. `.drp`读取逻辑支持第13字段，旧格式默认`0`。
3. 在活动滴灌循环中新增目标宽度计算。
4. `DripSpreadMode=1`时用目标宽度确定`WetRadius`，而不是等待`RO`触发。
5. `DripSpreadMode=1`时使用目标区间与边界控制区间的部分覆盖宽度确定活动范围。
6. `DripSpreadMode=1`时使用`CoverWidth × 距离权重`分配`DripRate`、`DripDemand_Rate`和`DripPressureLoss_Rate`。
7. 保持`DripInput_Rate`、`DripHydraulicExcess`和G05水量闭合逻辑不破坏。

## Python改动范围

主要文件：

- `DA_Framework/da_framework/hydrus_drip_calibration.py`
- `DA_Framework/da_framework/hydrus_2d_comparison.py`
- `DA_Framework/da_framework/drip_regression.py`
- `DA_Framework/tests/test_drip_regression.py`
- 新增或升级验证脚本，放在`tmp/codex_...`或稳定模块中，文件名包含`codex_`。

核心改动：

1. 将HYDRUS数字化时间序列固化为可调用函数。
2. 回归场景增加`DripSpreadMode=1`的精细算例。
3. 增加短时2 h HYDRUS对照算例，和长季节作物算例分开。
4. 生成逐边界段部分覆盖明细CSV，用于核对`covered_fraction`、`node_weight`和`flux_fraction`。
5. 生成二维`theta`、`delta theta`、根系叠加和湿润宽度时间序列图。
6. 增加HYDRUS二维`theta` CSV导入和MAIZSIM `G03`插值对比工具，用于外部HYDRUS数值场到位后的直接对比。
7. 增加图像质量检查：PNG非空、非纯色、滴头标记存在、地表滴灌源区范围标记存在、活动湿润区位于滴头附近。

## 验证矩阵

最小必要验证：

1. 单元测试：
   - `.drp`旧格式仍可解析。
   - 第13字段`DripSpreadMode`可解析并写出。
   - HYDRUS宽度曲线插值单调、不越上限。
   - 加权通量归一化守恒。

2. 编译验证：
   - Release x64构建通过。

3. 真实模型短时HYDRUS对照：
   - 砂壤土、壤土。
   - 单滴头，2 h，4 L等效输入。
   - 对比实际`DripWetWidthMax`与HYDRUS目标宽度的域裁剪值、旧完整段表达值和新部分覆盖表达值。
   - 输出`theta`和`delta theta`二维图。
   - 当外部HYDRUS二维CSV可用时，输出`theta`场MAE/RMSE、湿润区交并比、湿润宽度/深度和三联图。

4. 长季节作物算例：
   - 3种土壤、3种网格、至少5类场景。
   - 验证水量闭合、湿润宽度不越界、局部二维增湿、根区后期重叠。

5. 图像审查：
   - 滴头位置用红色倒三角和虚线标出。
   - 地表滴灌源区范围用红色水平线标出。
   - 图中必须能看到增湿区以滴头为中心或近中心展开。
   - 不应出现整幅图均匀增湿或远离滴头的主增湿峰。
   - 根系图应和水分图分开展示，并提供叠加图判断根区重叠。

## 论文和资料核对

实现后需要核对以下依据：

1. HYDRUS官方特殊边界条件说明：Surface Drip Irrigation从单个边界节点施加通量，若需要正压力头才能接纳，则切换为零压力头并把超额通量施加到相邻节点，直到通量被接纳并得到湿润半径。
2. HYDRUS技术手册：该动态湿润面积方法仅适用于二维或轴对称情形，且湿润面积随灌水进行连续增加。
3. 滴灌湿润体对比文献：HYDRUS-2D常用二维水分运动和湿润锋宽度/深度评估滴灌模型，不能只看总水量。

## 验收标准

目标完成需要同时满足：

1. 基线改动已提交，且新改动在其后可追踪。
2. 新精细模式代码实现完成并默认不破坏旧输入。
3. 单元测试和真实模型回归通过。
4. 2 h HYDRUS对照中壤土和砂壤土实际活动宽度接近目标曲线的离散网格表达，而不是停在`4.84 cm`。
5. 二维图显示湿润体位于滴头下方，横向扩展随土壤和时间变化合理。
6. 根系二维图和叠加图能支持滴灌湿润区与根区关系判断。
7. 文档更新为最新结论，并明确当前仍是HYDRUS-style地表边界近似，不是完整地下滴头源项模型。
8. 最终结论引用外部资料，并说明本次改动与文献机制的一致点和差异点。
