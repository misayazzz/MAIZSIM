# Mode6 HYDRUS-style地表滴灌活动边界设计

## 状态

本文最初是`DripSpreadMode=6`的实现设计草案。截至2026-06-07，当前实现已支持`DripSpreadMode=0/5/6`，并继续拒绝已废弃的`1/2/3/4`。`Mode6`已作为MAIZSIM/2DSOIL框架内的HYDRUS-style地表滴灌近似实现；它不是HYDRUS完整地表径流、地下滴灌模型或HYDRUS数值内核复刻。

当前实现要点：

- `Drip.FOR`读取和校验`DripSpreadMode=6`，用`DripSourceWidth`把`wAppl`转换为滴头总供水率，并登记中心地表边界和候选活动范围。
- 低流量或保守容量估计显示中心节点可承受时，`Watmov.for`在Richards求解中恢复基础`Q/CodeW`，应用`Mode6`通量边界或`h=0`头边界，求解后用`QAct`计算实际接纳量，再把剩余流量递推给下一候选环。
- 高流量场景若直接活动重解会使当前WaterMover出现ORTHOMIN发散或近零步长，`Drip.FOR`先用保守容量阈值`0.01 * Ks`估计需要的候选湿润带；当需要预展开时，使用现有稳定的地表源路径施加到预展开边界，并在`Watmov.for`已有实际入渗核算处记录`Mode6`的accepted/remaining诊断。
- 达到`DripWetWidthMax`、地表边界或内部迭代上限后仍未接纳的剩余水量，优先进入`DripSurfaceStorage`，超出暂存容量的部分进入`DripSurfaceRunoff_Flux`。
- `OUTPUT.FOR`的G05新增`DripMode6Accepted`、`DripMode6Remaining`、`DripMode6HeadNodes`、`DripMode6FluxNodes`、`DripMode6Iterations`和`DripMode6ClosureResidual`。
- Python输入生成和验证工具接受`0/5/6`，`Mode5/Mode6`均要求正`DripSourceWidth`；未写`DripSpreadMode`但写`DripSourceWidth`时仍默认写出`Mode5`。

## 已验证行为

2026-06-07在本次50 mm二维作物半域算例中运行了壤土和砂壤土验证，基础目录为`D:\Codex\codex_mode6_soil_test_20260606`。每种土壤均运行`baseline`、`Mode6 drip`和`Flood flux`三组；滴灌事件为`05/18/2007 00:00`到`05/22/2007 00:00`，`DripSourceWidth=1.0 cm`，`DripWetWidthMax=38.1 cm`，滴头位于左边界节点`1`，未对供水量自动折半。所有6个case的stdout均结束于`Finished at 39224.0000000000`。

| 土壤 | 处理 | G05输入或供水 | G05实际入渗 | G05 Mode6剩余 | 最大湿润宽度 | 近地表剖面结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 壤土 | Mode6 drip | `DripInput=50.042 mm` | `DripActualInfil=42.572 mm` | `8.812 mm` | `38.1 cm` | `theta_mean_top100=0.2732` |
| 壤土 | Flood flux | `50 mm`漫灌目标 | G05总`infil=86.711 mm` | 不适用 | 全地表 | `theta_mean_top100=0.2896` |
| 砂壤土 | Mode6 drip | `DripInput=50.042 mm` | `DripActualInfil=43.570 mm` | `7.632 mm` | `38.1 cm` | `theta_mean_top100=0.1592` |
| 砂壤土 | Flood flux | `50 mm`漫灌目标 | G05总`infil=86.620 mm` | 不适用 | 全地表 | `theta_mean_top100=0.1748` |

图像输出已生成：

- `D:\Codex\codex_mode6_soil_test_20260606\codex_mode6_vs_flood_theta_50mm.png`
- `D:\Codex\codex_mode6_soil_test_20260606\codex_mode6_vs_flood_delta_theta_50mm.png`

这组算例说明：在左边界滴头、半域宽度`38.1 cm`、`DripWetWidthMax`覆盖全地表时，`Mode6`会扩展到全宽；但达到上限后仍有约`7.6`到`8.8 mm`未被土壤接纳，进入地表暂存或径流诊断。因此Mode6水分剖面比漫灌略干。这是当前MAIZSIM/2DSOIL求解器内的可闭合近似结果，不应解释为HYDRUS官方算例精度验证。

2026-06-06在HUTD06短窗算例中运行了三组`Mode6`地表滴灌验证，事件窗口为`04/01/2006 00:00`到`04/01/2006 04:00`，中心节点为`7`。验证文件放在HDD的`D:\Codex\codex_mode6_validation_20260606`下，解析后已清理临时目录。

| 算例 | `wAppl` | `DripWetWidthMax` | G05结果摘要 |
| --- | ---: | ---: | --- |
| low | `0.20 cm/h` | `30.0 cm` | `DripInput=0.227 mm`，`DripActualInfil=0.227 mm`，`DripMode6Remaining=0`，两类闭合残差为`0` |
| high_limited | `5.00 cm/h` | `12.0 cm` | `DripInput=5.460 mm`，`DripActualInfil=5.460 mm`，`DripMode6Remaining=0`，两类闭合残差为`0` |
| extreme_limited | `200.0 cm/h` | `4.84 cm` | `DripInput=215.378 mm`，`DripActualInfil=28.216 mm`，`DripMode6Remaining=188.572 mm`，`DripSurfaceRunoff=187.164 mm`，两类闭合残差为`0` |

同一验证中，G03二维`theta`输出显示灌后正`delta theta`湿润体存在并可审阅：low算例灌后最大`delta theta=0.203`、最深正变化约`63.0 cm`；high_limited算例灌后最大`delta theta=0.202`、最深正变化约`63.0 cm`；extreme_limited算例灌后最大`delta theta=0.203`、最深正变化约`63.0 cm`。这些结果用于工程闭合和二维输出冒烟验证，不作为HYDRUS benchmark精度结论。

## 背景

当前`DripSpreadMode=0`是旧格式兼容路径：水从指定地表节点进入，水量按中心边界段`Width(CenterBnd)`解释，并用`RO`触发简单扩展或收缩。

当前`DripSpreadMode=5`是动态局部地表源近似：`DripSourceWidth`定义滴头供水源measure，`DripWetWidthMax`限制最大湿润斑宽度，模型按局部接纳能力和`CoverMeasure`分配通量；当接纳能力不足时，使用局部暂存和释放诊断维持闭合。

`Mode6`的目标不是继续微调`Mode5`，而是实现更接近HYDRUS SurfaceDrip思想的活动边界算法：给定滴头总流量，从中心地表节点开始尝试入渗；若某节点无法接纳给定通量，则把该节点切换为`h=0`的定水头边界，计算其实际入渗量，并把剩余流量继续递推给邻近地表节点，直到总流量被接纳或达到设定上限。

## 设计目标

1. 只实现地表滴灌，不实现地下滴头内部源项。
2. 保留`Mode0`兼容路径和`Mode5`当前近似路径，不用`Mode6`替换它们。
3. 让`Mode6`在Richards方程求解层动态切换地表节点边界条件，而不是在`Drip.FOR`中预先估计湿润宽度。
4. 使用`DripSourceWidth`把输入`wAppl`转换为滴头总供水率，避免水量依赖网格边界段宽度。
5. 输出可审计诊断：总需求、实际入渗、剩余未接纳水量、活动头边界节点数、活动通量节点数、湿润宽度、活动边界迭代次数和闭合残差。
6. 对`KAT=1`轴对称算例，所有候选边界段和水量分配都必须使用轴对称measure，不能把`DripSourceWidth`简单解释为二维slab宽度。

## 非目标

1. 本阶段不实现地下滴灌的压力-流量特征函数。
2. 本阶段不引入新的第三方数值库。
3. 本阶段不重写整个`WaterMover`，只在现有边界条件和迭代结构中增加活动边界循环。
4. 本阶段不恢复已删除的`DripSpreadMode=1/2/3/4`。
5. 本阶段不把地表积水在地表水模块中二次横向铺开；`Mode6`应优先由活动边界扩展来接纳水量，超过上限后再计入滴灌专属暂存或径流诊断。

## 当前代码基础

当前水分求解器已经具备实现`Mode6`的基础：

- `CodeW > 0`表示定水头边界，`CodeW < 0`表示定通量边界。
- 地表通量边界使用`CodeW=-4`。
- 地表定水头边界可使用`CodeW=4`。
- `WaterMover`会计算定水头或地表节点的实际边界通量`QAct`。
- 当前地表通量超出实际入渗能力时，已有`RO=max(Q-QAct,0)`形式的超量诊断。
- `Drip.FOR`已经能把滴灌输入转成地表边界通量，并写入`VarBW`和`Q`。
- `PuSurface.ins`已有滴灌诊断和局部暂存相关公共数组，可作为新增`Mode6`诊断数组的存放位置。

这些基础说明`Mode6`可实现，但实现位置必须进入`WaterMover`的Richards边界处理层。只在`Drip.FOR`中新增一个分配分支，无法实现HYDRUS-style活动边界。

## 输入契约

建议把`Mode6`作为新的显式模式：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode DripSourceWidth
```

字段规则：

- `DripSpreadMode=6`表示HYDRUS-style地表活动边界。
- `DripSourceWidth`必须为正，用于把`wAppl`转换成滴头总供水率。
- `DripWetWidthMax`可为0；为0时使用内部默认上限或整段地表边界上限。
- `Num_nodes`和后续节点列表仍表示滴头中心节点。
- `DripMode=1/2`可继续作为入口压力修正，用于先修正滴头总供水率；它不是地下滴头回压模型。
- `DripMode=3`不应自动恢复。若需要直接源项或旁路求解，应另立设计。

输入层需要同步更新：

- Fortran读取和校验允许`DripSpreadMode=6`。
- Python输入生成器允许`0/5/6`，拒绝`1/2/3/4`。
- `.drp`解析器允许`0/5/6`。
- `Mode5`和`Mode6`都要求正的`DripSourceWidth`。
- 若填写`DripSourceWidth`但省略`DripSpreadMode`，仍建议默认写成`Mode5`，不要静默默认到`Mode6`，因为`Mode6`会改变求解器行为。

## 核心算法

`Mode6`应按“活动边界重解”实现，而不是按预估湿润宽度一次性分配。

### 1. 生成滴头总供水率

对每个活动滴灌事件和中心节点，先计算总供水率：

```text
SourceRate = wAppl / PERIOD
SourceDemandFlux = SourceRate * DripSourceWidth
```

若启用`DripMode=1/2`，先计算压力修正因子`PressureFactor`，然后：

```text
SourceDemandFlux = SourceDemandFlux * PressureFactor
```

这里的`SourceDemandFlux`是滴头在当前事件中的总供水率，后续活动边界循环负责决定这些水由哪些地表边界段接纳。

### 2. 构造候选地表边界序列

从滴头中心边界段开始，按地表位置向外构造候选序列。

二维slab情形：

- 第0环：中心边界段。
- 第1环：左邻和右邻中存在的边界段。
- 第2环：再向外的左邻和右邻。
- 依次扩展，直到达到`DripWetWidthMax`、地表边界尽头或内部最大安全半径。

轴对称`KAT=1`情形：

- 若滴头位于对称轴附近，候选序列应只向外扩展。
- 每个候选边界段的measure必须按轴对称几何解释。
- 不能把节点间距直接当作slab宽度。

候选序列需要记录：

- 边界段编号`k`。
- 对应节点`n=KXB(k)`。
- 几何measure。
- 与中心的距离或环编号。
- 是否已被激活为通量边界。
- 是否已被锁定为`h=0`头边界。

### 3. 初始通量边界

第一轮只把总供水率分配给中心边界段：

```text
CodeW(center_node) = -4
Q(center_node) = Q(center_node) + SourceDemandFlux
```

如果存在多个滴头事件同时作用于不同中心节点，先采用保守策略：同一时间步内不允许两个`Mode6`滴头的候选活动范围重叠。若检测到重叠，输入层或运行时应报错。等单滴头算法稳定后，再设计重叠滴头的水量合并规则。

### 4. 求解并判断接纳能力

运行Richards求解后，读取每个活动节点的实际边界通量`QAct`。

对当前仍为通量边界的节点，判断给定通量是否被完全接纳：

```text
Excess = max(Q_assigned - QAct, 0)
```

若`Excess <= tolerance`，该节点接纳成功。

若`Excess > tolerance`，说明该节点无法接纳给定通量，应执行边界切换：

```text
CodeW(node) = 4
hNew(node) = 0.0
```

然后把该节点标记为头边界节点。该节点之后不再被强制给定通量，而是在`h=0`条件下由求解器计算实际入渗量。

### 5. 递推剩余流量

每次求解后，计算已被活动边界接纳的水量：

```text
AcceptedFlux = sum(max(QAct(node), 0) over active drip nodes)
RemainingFlux = SourceDemandFlux - AcceptedFlux
```

若`RemainingFlux <= tolerance`，该滴头在当前时间步完成分配。

若`RemainingFlux > tolerance`，激活下一个候选环，把剩余水量分配给新激活的边界段。分配策略建议从简单可审计规则开始：

- 若新环只有一个边界段，全部剩余流量给该边界段。
- 若新环有左右两个边界段，按边界measure比例分配剩余流量。
- 已经锁定为`h=0`的边界段不再分配强制通量。

然后重新运行Richards求解。重复“求解、切换、递推”直到满足闭合或达到候选上限。

### 6. 达到上限后的剩余水量

如果达到`DripWetWidthMax`或地表边界尽头后仍有`RemainingFlux > tolerance`，不能继续凭空消失。

建议处理为：

- 优先计入`DripSurfaceStorage`，上限为当前活动边界measure乘以`CriticalH`。
- 超过暂存上限的部分计入`DripSurfaceRunoff_Flux`。
- 同时输出`DripMode6Unaccepted_Flux`或等价诊断，方便验证。

这一步是MAIZSIM框架内对HYDRUS活动边界无法继续扩展时的闭合处理，不应被解释为HYDRUS原始算法的完整地表径流模型。

## 与`Mode5`的区别

| 项目 | `Mode5` | `Mode6` |
| --- | --- | --- |
| 核心思想 | 预先选择局部湿润区间并按`CoverMeasure`分配通量 | 在Richards求解过程中动态切换通量边界和`h=0`头边界 |
| 活动区确定 | 由`DripSourceWidth`、`DripWetWidthMax`和局部接纳能力近似确定 | 由每轮求解得到的`QAct`和剩余流量递推确定 |
| 边界类型 | 主要仍是地表通量边界 | 通量边界和`h=0`头边界混合 |
| 剩余水量 | 局部暂存、释放和超量诊断 | 优先扩展活动边界，达到上限后才进入暂存或径流 |
| 实现层级 | 主要在`Drip.FOR`中分配，`WaterMover`做后处理 | 必须进入`WaterMover`的边界条件迭代和重解流程 |
| 物理表述 | MAIZSIM动态局部地表源近似 | HYDRUS-style地表活动边界近似 |

## 建议代码结构

### `Drip.FOR`

职责应从“直接分配最终地表通量”改为“为`Mode6`登记滴头需求”：

1. 读取并校验`DripSpreadMode=6`。
2. 对每个活动`Mode6`事件计算`SourceDemandFlux`。
3. 构造或登记中心边界段、最大候选范围和事件编号。
4. 不直接写最终`DripRate`。
5. 设置`DripBypassRunoff=1`，避免通用地表径流模块提前把滴灌水横向铺开。

### `PuSurface.ins`

需要新增公共数组或标志，建议先采用边界段维度和事件维度分离的方式：

```fortran
Integer DripMode6Active
Integer DripMode6Count
Integer DripMode6CenterBnd(Max_times,Max_nodes)
Integer DripMode6LeftBnd(Max_times,Max_nodes)
Integer DripMode6RightBnd(Max_times,Max_nodes)
Real DripMode6DemandFlux(Max_times,Max_nodes)
Real DripMode6RemainingFlux(Max_times,Max_nodes)
Real DripMode6AssignedRate(NumBPD)
Integer DripMode6FluxActive(NumBPD)
Integer DripMode6HeadActive(NumBPD)
```

实际实现时可根据现有数组容量和Fortran公共块限制调整命名和维度。关键原则是：`WaterMover`必须知道哪些边界段属于当前`Mode6`活动集，以及每个滴头还有多少剩余流量。

### `WaterMover`

`WaterMover`应新增一个活动边界求解循环。建议放在时间步内、普通边界条件求解之外的一层小循环中：

```text
prepare base Q and CodeW
initialize Mode6 active set

repeat until all Mode6 sources closed or max_active_iterations reached:
    restore base Q and CodeW
    apply non-drip boundary additions
    apply Mode6 head-active nodes as CodeW=4, hNew=0
    apply Mode6 flux-active nodes as CodeW=-4 with assigned Q
    solve Richards equation with current boundary set
    compute QAct
    update accepted flux and remaining flux for each Mode6 source
    convert overloaded flux nodes to head-active nodes
    activate next candidate ring for remaining flux

if remaining flux persists:
    close through drip storage/runoff diagnostics
```

必须设置最大活动边界迭代次数，例如：

```text
max_active_iterations = min(number_of_surface_boundary_segments, 50)
```

超过上限时应停止扩展并把剩余水量计入诊断，不能无限重解。

### `OUTPUT.FOR`

G05建议新增或复用以下诊断：

- `DripDemand`
- `DripInput`
- `DripActualInfil`
- `DripSurfaceRunoff`
- `DripStorageChange`
- `DripMode6Accepted`
- `DripMode6Remaining`
- `DripMode6HeadNodes`
- `DripMode6FluxNodes`
- `DripMode6Iterations`
- `DripWetWidth`
- `DripClosureResidual`

若不希望立即扩展G05列，也至少应保证已有闭合列能覆盖`Mode6`：

```text
DripBoundaryInClosure = DripDemand - DripPressureLoss - DripInput
DripBoundaryAccClosure = DripInput - DripActualInfil
                       - DripHydraulicExcess - DripStorageChange
                       - DripSurfaceRunoff
```

## 关键实现细节

### 符号约定

当前代码中，滴灌入渗通量以`Q(n)>0`的形式进入地表节点，并会把`CodeW(n)`设为`-4`。实现`Mode6`时必须沿用这个约定，否则`RO`、`QAct`和G05闭合会出现符号错误。

### 头边界水头

HYDRUS SurfaceDrip描述中，无法接纳强制通量的节点会切换为`h=0`。因此`Mode6`的头边界建议使用：

```text
CodeW(node) = 4
hNew(node) = 0.0
```

不要直接使用`CriticalH`作为活动边界头值。`CriticalH`更接近MAIZSIM地表暂存或积水上限诊断；若把活动边界直接设为`CriticalH`，会改变HYDRUS-style算法含义。

### 与降雨、蒸发和自动灌溉的叠加

`Mode6`实现初期应限制同一地表边界段同时存在复杂外部输入：

- 若同一时间步同一边界段已有正降雨或自动灌溉通量，应先记录并合并到背景通量，再单独统计滴灌贡献。
- 若蒸发需求存在，`Mode6`活动节点应优先满足滴灌边界条件，避免蒸发潜势把活动头边界改写成普通大气边界。
- 若覆盖物或地表径流模块会修改`VarBW`，需要在`Mode6`活动边界循环中固定滴灌贡献，避免每次重解重复累加。

### 多滴头处理

第一版建议只支持活动范围不重叠的多个滴头。判断方法：

1. 为每个`Mode6`滴头预估最大候选边界范围。
2. 若两个滴头候选范围重叠，报错并提示用户减小`DripWetWidthMax`、错开时间或改用`Mode5`。
3. 后续版本再实现重叠活动集的水量合并。

这样可以避免两个滴头同时把同一个节点切换为头边界后难以区分各自接纳量。

### 时间步控制

活动边界算法会增加重解次数。为避免单步内边界切换过多，建议：

- 若`Mode6`活动边界迭代次数超过阈值，缩短下一水分时间步。
- 若某时间步出现大量剩余未接纳水量，缩短下一水分时间步。
- 保留当前`NextTime`事件起止时间控制，确保滴灌开始和停止时刻被精确切分。

## 测试计划

### 输入和解析测试

1. `.drp`解析器接受`DripSpreadMode=6`和正`DripSourceWidth`。
2. `.drp`解析器拒绝`Mode6`缺失或非正`DripSourceWidth`。
3. Python输入生成器允许`0/5/6`，继续拒绝`1/2/3/4`。
4. 未填写`DripSpreadMode`但填写`DripSourceWidth`时仍默认`Mode5`，不默认`Mode6`。

### Fortran契约测试

1. `Drip.FOR`允许`DripSpreadMode=6`。
2. `Mode6`不会走`Mode5`的`CoverMeasure`预分配分支。
3. `Mode6`会设置活动边界登记数组，而不是直接写最终`DripRate`。
4. `WaterMover`包含`Mode6`活动边界循环、头边界切换和剩余流量递推逻辑。

### 数值单元场景

1. 低流量场景：中心节点一次接纳全部水量，不扩展。
2. 高流量场景：中心节点切换为`h=0`，剩余水量向邻近节点扩展。
3. 上限场景：达到`DripWetWidthMax`后仍有剩余水量，剩余量进入暂存或径流诊断。
4. 压力修正场景：`DripMode=1/2`先降低总供水率，活动边界使用修正后的需求。
5. 轴对称场景：候选measure和闭合按轴对称几何计算。

### 回归和验收

1. 旧6字段`.drp`仍默认`Mode0`并可运行。
2. `Mode5`现有测试全部通过。
3. `Mode6`G05闭合残差小于设定容差。
4. 与HYDRUS surface drip benchmark比较湿润宽度、湿润深度、储水增量和入渗总量。
5. 输出二维`theta`和`delta theta`图，确认湿润体形态不是仅靠输入量闭合伪造。

## 风险和处理

### 风险1：活动边界重解导致收敛变差

处理：

- 限制每个时间步最大活动边界迭代次数。
- 必要时缩短下一时间步。
- 对边界切换使用容差，避免节点在通量和头边界之间来回跳变。

### 风险2：`CodeW`和`Q`在多次重解中被重复累加

处理：

- 每轮活动边界重解都从`BaseQ`和`BaseCodeW`恢复。
- 滴灌贡献使用单独的`DripMode6AssignedRate`或等价数组记录。
- 不直接依赖上一轮已经改写的`VarBW`作为下一轮基础。

### 风险3：与普通地表径流模块重复计算横向铺展

处理：

- `Mode6`活动期间设置`DripBypassRunoff=1`。
- 活动边界优先扩展接纳水量。
- 只有达到活动上限后的剩余水量才进入滴灌专属暂存或径流诊断。

### 风险4：多滴头活动范围重叠导致归属不清

处理：

- 第一版禁止`Mode6`滴头候选范围重叠。
- 输入或运行时检测到重叠则报错。
- 后续版本再实现合并活动集。

### 风险5：轴对称measure处理错误

处理：

- 单独写`KAT=1`测试。
- 所有候选宽度、`DripSourceWidth`和`QAct`闭合都用measure表述。
- 文档和输出避免把轴对称结果简单称为普通二维宽度。

## 分阶段实施建议

### 阶段1：输入契约和文档

- 更新输入校验，允许`DripSpreadMode=6`。
- 新增解析和输入生成测试。
- 不改变求解器行为。

### 阶段2：活动边界数据结构

- 在`PuSurface.ins`增加`Mode6`公共数组。
- `Drip.FOR`登记活动滴头需求和候选范围。
- 添加Fortran契约测试，确认`Mode6`不走`Mode5`最终通量分配。

### 阶段3：`WaterMover`活动边界循环

- 在单滴头、无重叠、无复杂降雨条件下实现活动边界重解。
- 支持通量边界到`h=0`头边界切换。
- 支持剩余流量向下一候选环递推。

### 阶段4：诊断和闭合

- 增加或复用G05闭合列。
- 输出活动节点数、活动宽度、迭代次数和剩余流量。
- 建立`Mode6`水量闭合测试。

### 阶段5：真实算例验证

- 选择一个低流量单节点接纳算例。
- 选择一个高流量扩展算例。
- 选择一个达到`DripWetWidthMax`的上限算例。
- 与HYDRUS surface drip结果对比湿润宽度、湿润深度、入渗总量和二维湿润体形态。

## 成功标准

`Mode6`可视为初步实现成功，需要同时满足：

1. 输入层只接受`0/5/6`，继续拒绝`1/2/3/4`。
2. `Mode6`不会使用`Mode5`的预分配近似作为核心算法。
3. 单滴头低流量场景不扩展且水量闭合。
4. 单滴头高流量场景会把中心节点切换为`h=0`，并把剩余水量递推给邻近节点。
5. 达到最大活动范围时，剩余水量进入可审计的暂存或径流诊断。
6. `Mode0`和`Mode5`现有测试不退化。
7. G05能解释`DripDemand`、`DripActualInfil`、`DripSurfaceRunoff`、`DripStorageChange`和闭合残差。
8. 至少一个真实二维算例能输出可审阅的湿润体几何图和储水增量图。

## 需要进一步确认的问题

1. `Mode6`第一版是否强制禁止多滴头活动范围重叠。
2. `Mode6`达到上限后的剩余水量，是优先进入`DripSurfaceStorage`，还是直接进入`DripSurfaceRunoff_Flux`。
3. `h=0`头边界是否需要在MAIZSIM当前水头符号和地表积水逻辑中做额外偏移。
4. 真实验收算例应优先使用哪个HYDRUS surface drip案例作为benchmark。
5. 是否需要新增单独输出文件记录每个时间步的活动边界节点序列。
