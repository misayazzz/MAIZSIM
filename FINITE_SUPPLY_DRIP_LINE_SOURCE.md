# MAIZSIM有限供水等效滴灌线源

## 适用范围

本模块只适用于二维笛卡尔竖直剖面，即网格参数`KAT=2`。计算域是滴灌带一侧的半域，滴灌带固定在地表对称轴`x=0`。一个滴头及其间距代表沿垄向周期排列的滴头；模型按半域折算供水，不把滴头的三维点源流量直接当作二维边界通量。

模块保留原Mode6的Newton非线性求解、通量边界与`h=0`水头边界切换、步内质量闭合和失败重算。不存在Mode5、动态湿润半径、湿润节点逐步扩展或向全地表扩展。求解失败不会回退到其他模式、跳过时间步或放宽闭合阈值。

## `.drp`输入格式

文件开头仍为事件数，随后每个事件使用一行8个字段和一个节点列表：

```text
***** Fixed-contact half-domain drip
Number of Drip irrigations(max=75)
1
Start_Date Start_hour Stop_Date Stop_hour EmitterFlowLph EmitterSpacingCm ContactWidthCm Num_nodes
'04/01/2006' 0 '04/02/2006' 0 0.28125 30 2 1
Drip application nodes
1
```

| 字段 | 单位 | 含义和约束 |
| --- | --- | --- |
| `Start_Date`, `Stop_Date` | 日期 | 事件起止日期；结束时刻必须晚于开始时刻 |
| `Start_hour`, `Stop_hour` | h | 当日小时，可为小数 |
| `EmitterFlowLph` | L/h | 单个滴头流量，必须大于0 |
| `EmitterSpacingCm` | cm | 沿滴灌带的滴头间距，必须大于0；所有事件相同 |
| `ContactWidthCm` | cm | 半域内从`x=0`起的固定物理接触宽度；所有事件相同且不得超出地表 |
| `Num_nodes` | 1 | 必须恰为1 |
| 节点号 | - | 必须是唯一的`x=0`地表节点；所有事件相同 |

事件不得重叠。旧格式字段`wAppl`、`DripMode`、`DripWetWidthMax`、`DripSpreadMode`和`DripSourceWidth`不再接受。

## 半域供水换算

设滴头流量为`q_e`（L/h），滴头间距为`s_e`（cm）。模型使用的半域线供水率为：

```text
Q_half = q_e * 1000 * 24 / (2 * s_e)
```

其中`Q_half`的单位是cm2/day，即每1 cm垄向代表长度的二维截面供水体积率。因子`1/2`表示仅模拟滴灌带一侧。

若目标是在宽度`W`（cm）的半域上、持续`t_e`（h）施加等效水深`D`（cm），输入滴头流量应为：

```text
q_e = 2 * s_e * D * W / (1000 * t_e)
```

例如`W=37.5 cm`、`D=3 cm`、`s_e=30 cm`、`t_e=24 h`时，`q_e=0.28125 L/h`，半域累计输入为`112.5 cm2`，等效30 mm。

## 固定接触区和局部积水

模型启动时只离散一次物理区间`[0, ContactWidthCm]`。每个地表节点获得其边界控制段与该区间的交叠测度；边缘控制段允许部分覆盖。所有外部供水、重供的积水和最终积水都按这些固定测度守恒分配。网格细化可以改变接触节点数，但接触测度之和必须保持等于`ContactWidthCm`。

每个已接受的Richards子步满足以下物理账本：

```text
available volume = old ponding + external emitter input
new raw ponding = available volume - accepted infiltration
new ponding = min(new raw ponding, contact measure * hCritS)
overflow = max(new raw ponding - contact measure * hCritS, 0)
```

`hCritS`来自`WaterMovDefault.dat`。积水只保存在固定接触区；达到容量后的水进入滴灌溢流账本，不触发接触区扩展。

## G05输出

滴灌水深量均按整个半域宽度折算为mm。

| 列名 | 含义 |
| --- | --- |
| `DripEmitterInput_mm` | 当前输出区间的外部滴头输入 |
| `SeasDrip_mm` | 累计外部滴头输入 |
| `DripActualInfil_mm` | 当前输出区间已接受入渗 |
| `DripPondingChange_mm` | 当前输出区间局部积水变化，可正可负 |
| `DripOverflow_mm` | 当前输出区间超过局部容量的溢流 |
| `DripPonded_mm` | 输出时刻固定接触区现存积水 |
| `DripLedgerClosure_mm` | `输入 - 入渗 - 积水变化 - 溢流` |
| `DripContactWidth_cm` | 输入的固定物理接触宽度 |
| `DripContactMeasure_cm` | 网格离散后的接触测度和 |
| `DripContactNodes` | 当前网格中具有正接触测度的节点数 |
| `DripPondingCapacity_mm` | 固定接触区积水容量 |
| `DripMode6Available_mm` | Mode6求解器累计可用水量，包含重供积水 |
| `DripMode6Accepted_mm` | Mode6求解器累计接受量 |
| `DripMode6Remaining_mm` | Mode6求解器累计未接受量 |
| `DripMode6HeadNodes` | 时间加权的`h=0`活动节点数 |
| `DripMode6FluxNodes` | 时间加权的通量活动节点数 |
| `DripMode6Iterations` | 时间加权的活动边界迭代次数 |
| `DripMode6ClosureResidual` | `Available - Accepted - Remaining` |
| `DripMode6SolverLimit` | 非零表示求解器限幅，不应作为通过结果接受 |
| `DripMode6BoundaryLimit` | 非零表示固定接触活动集达到边界限额，不应作为通过结果接受 |
| `DripMode6StepCuts` | 重算总次数 |
| `DripMode6NonlinearCuts` | Newton失败导致的重算次数 |
| `DripMode6SupplyCuts` | 供水闭合失败导致的重算次数 |
| `DripMode6MassCuts` | 质量闭合失败导致的重算次数 |
| `DripMode6MinDtDays` | 实际使用的最小Richards子步，单位day |

`WaterMassBalance.out`仍用于核对整个土壤域的逐步和累计水量闭合。滴灌账本闭合不能替代全域水量闭合。

`DripMode6Available_mm`和`DripMode6Remaining_mm`会累计求解过程中再次提供的局部积水，因此是求解器闭合诊断，不是外部水量账本。物理输入、积水和溢流必须使用`DripEmitterInput_mm`、`DripPondingChange_mm`、`DripOverflow_mm`和`DripLedgerClosure_mm`核对，不能把`DripMode6Remaining_mm`直接等同于溢流。

## Python/Excel输入映射

`示例输入/ExcelInterface-master/tools/maizsim_inputs/drip.py`接受以下规范字段及大小写/空格归一化后的别名：

- `EmitterFlowLph`
- `EmitterSpacingCm`
- `ContactWidthCm`
- 起止日期和小时
- 一个`x=0`地表节点；未指定时自动选择

输入器会拒绝旧Mode5/Mode6扩展字段、非笛卡尔网格、非`x=0`滴灌节点、变化的间距或接触宽度、重叠事件以及多节点事件。

## 构建和验证

Windows Release构建：

```powershell
& 'C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe' `
  'Soil Source\2dmaizsim.msbuild.vcxproj' `
  /t:Build /p:Configuration=Release /p:Platform=x64 `
  '/p:SolutionDir=H:\Code\丁一民老师\二维作物模型\MAIZSIM\'
```

从`DA_Framework`运行全部测试：

```powershell
pixi run --manifest-path '..\pixi.toml' pytest -q
```

三种土壤30 mm验证示例：

```powershell
pixi run --manifest-path '..\pixi.toml' python -m da_framework.mode6_30mm_validation `
  --repo-root '..' `
  --workspace 'E:\Codex\codex_mode6_30mm_validation'
```

验证工作目录应按本机规则放在机械硬盘的唯一`codex`目录中。脚本生成每个土壤的baseline与滴灌算例，以及`codex_mode6_30mm_summary.csv`和`codex_mode6_30mm_summary.json`。

三网格和三时间步收敛可以直接运行：

```powershell
pixi run --manifest-path '..\pixi.toml' python -m da_framework.mode6_convergence `
  --repo-root '..' --workspace 'E:\Codex\codex_mode6_grid' --kind grid

pixi run --manifest-path '..\pixi.toml' python -m da_framework.mode6_convergence `
  --repo-root '..' --workspace 'E:\Codex\codex_mode6_time' --kind time
```

网格层级为`0/1/2`，局部细化比为2。时间步上限为`0.001/0.0005/0.00025 day`。收敛报告对30 mm守恒入渗和半域储水积分执行受保护的三层GCI判据；阈值湿润深度、面积和点值仍完整报告，但不会替代积分量判据。

## 2026-08-03验收结果

最终Release二进制在37.5 cm半域、2 cm固定接触区、30 cm滴头间距、24 h输入30 mm的结果如下。

| 土壤 | 输入(mm) | 入渗(mm) | 溢流(mm) | 终端账本误差(mm) | 全域水量残差(mm) |
| --- | ---: | ---: | ---: | ---: | ---: |
| loam | 30.000000 | 30.000000 | 0.000000 | 0.000000 | -0.022538 |
| sandy_loam | 30.000000 | 30.000000 | 0.000000 | 0.000000 | -0.003301 |
| clay_loam | 30.000000 | 24.276868 | 5.723132 | -0.000000070 | -0.001081 |

三个算例的`DripMode6SolverLimit`、`DripMode6BoundaryLimit`、重算次数、滴灌账本最大闭合残差均为0或数值零；接触宽度和离散测度均为2 cm。黏壤土算例实际触发了固定接触区溢流账本，而未扩展接触区。

三网格验收中，接触节点数为`3/5/10`，接触测度始终为2 cm；30 mm入渗在输出精度内不变。半域储水积分的细网格GCI为2.84635%，medium-to-fine相对差为1.47068%。湿润面积的细网格GCI为4.10705%；湿润深度的连续变化量未给出可信的正收敛阶，因此只保留为诊断量，不据此宣称收敛。

三时间步验收中，30 mm入渗、峰值含水量变化、阈值湿润深度和面积在输出精度内不变；半域储水积分的细时间步GCI为0.000106325%，medium-to-fine相对差为0.0000267096%。

每个运行场都按`x=0`镜像重构到完整行间域。镜像节点对最大差为0，完整域储水积分与半域积分之比严格为2.0。该检查证明半域离散和镜像重构一致，不等同于另一次独立全域求解。

## 解释边界

本实现是MAIZSIM/2DSOIL内部的二维笛卡尔、固定接触区、有限供水活动边界近似。内部回归、质量闭合、网格/时间步收敛和半域镜像只能证明实现的一致性与数值行为；在与独立HYDRUS-2D算例、实验数据或田间观测完成校准和验证前，不应把它表述为已复现HYDRUS内核或已具备外部预测精度。
