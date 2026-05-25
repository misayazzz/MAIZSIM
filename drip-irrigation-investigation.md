# MAIZSIM滴灌实现调查与验证记录

记录日期：2026-05-24

最新更新：2026-05-25

当前状态：detached HEAD `199627a`基础上继续实现精细地表滴灌；本轮改动尚未提交。

## 当前结论

当前已经实现的是“地表滴灌边界增强/重分配”的工程版本：滴灌仍作为地表点源Neumann通量边界进入MAIZSIM水分过程，但已从“只扩不缩的动态湿润半径”增强为可扩可缩、且受物理最大湿润宽度约束的地表湿润范围，并在G05中输出独立诊断量。

最新补充：`DripWetWidthMax`已用HYDRUS官方SurfaceDrip公开算例做第一版校准。砂壤土采用`16.3 cm`，壤土采用`39.7 cm`；HYDRUS公开图中没有黏壤土目标，因此黏壤土仍显式使用`20.0 cm`兼容fallback，不能称为HYDRUS标定值。HYDRUS标定后的二维补验显示，当前壤土和砂壤土代表算例有清晰局部增湿和根区重叠，但实际湿润宽度仍停留在中心地表节点`4.84 cm`，没有触发到`16.3 cm`或`39.7 cm`上限。

一句话定位：这是地表点源滴灌增强，不是地下埋设滴头源项模型。

补充定位：二维含水量和根系图可以证明滴灌输入对土体水分和根区环境有影响，但当前实现不应描述为严格物理意义上的局部滴灌湿润体模型。修订前的对照分析显示，湿润宽度容易在当前10个地表节点网格上扩展到全地表边界；本轮修订后，更准确的表述是“带物理宽度上限的地表边界源项动态重分配近似”。

## 主要改动范围

本轮核心改动文件：

- `Soil Source/Drip.FOR`
- `Soil Source/PuSurface.ins`
- `Soil Source/OUTPUT.FOR`
- `Soil Source/Watmov.for`
- `DA_Framework/base_runs/SingleLayerLoam2D/LOAM2D.drp`
- `DA_Framework/da_framework/hydrus_drip_calibration.py`
- `DA_Framework/da_framework/drip_validation.py`
- `DA_Framework/da_framework/drip_regression.py`
- `DA_Framework/tests/test_drip_validation.py`
- `DA_Framework/tests/test_drip_regression.py`
- `示例输入/ExcelInterface-master/tools/maizsim_inputs/drip.py`

前序滴灌链路改动仍包括：

- `Soil Source/2DMAIZSIM.FOR`已启用`Call Drip()`。
- `Soil Source/Init.for`已初始化`QAct(:)=0.`，避免首次湿润范围判断读取未初始化实际边界通量。
- Excel/Python输入链路已支持`Drip`、`DripNodes`和`.drp`生成。

## 当前Fortran行为

### 调用位置

主时间步中`Call Drip()`位于天气、灌溉、漫灌和耕作处理之后，作物生长、根系吸水、地表覆盖和`WaterMover()`之前。

这意味着滴灌在水分求解前写入地表边界输入；`WaterMover()`随后计算当前步实际入渗、边界切换和径流。

### 输入读取

`.drp`格式保持向后兼容：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes
node_1 node_2 ... node_n
```

扩展压力字段格式为：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax
node_1 node_2 ... node_n
```

扩展湿润宽度字段格式为：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax
node_1 node_2 ... node_n
```

字段含义：

- `wAppl`按`cm/hr`解释。
- Fortran内部将`wAppl`换算为`cm/day`边界通量。
- 滴灌节点必须是`abs(CodeW)==4`的地表水分边界节点。
- 旧6字段事件仍可读取；11字段事件用于压力近似；12字段事件在压力字段之后增加`DripWetWidthMax`。
- `DripWetWidthMax`单位为`cm`，表示单个滴头事件允许动态扩展到的最大地表湿润宽度。未提供或为`0`时，Fortran使用内部默认上限，目前为`min(20 cm, 0.5 * 地表水分边界总宽度)`，且不会小于滴头中心边界段自身宽度。
- 当前回归矩阵会显式写入HYDRUS校准或fallback宽度，不依赖Fortran省略输入时的`20 cm`默认值。
- 当前代码和Python生成器按最多75个事件、每事件最多150个节点处理。

`.drp`文件头已经从旧的`max=25`和固定`45 x 30 cm area`说明更新为当前边界宽度解释。

### 可扩可缩湿润范围

`Drip.FOR`为每个事件、每个中心滴头节点维护`WetRadius(jj,in)`：

- 若当前湿润范围内累计`RO`超过上一滴灌通量的5%或数值容差，湿润半径向相邻地表边界节点扩展一格。这里的`RO`来自`WaterMover()`确认的地表入渗受限/径流信号，避免用裸`Q - QAct`数值差直接触发横向扩展。
- 若当前湿润范围连续两个滴灌调用周期内无上述入渗受限信号，湿润半径收缩一格。
- 半径始终限制在`0 <= WetRadius <= MaxRadius`；`MaxRadius`现在由地表端点上限和`DripWetWidthMax`共同约束，不再允许无物理宽度上限地扩展到整个地表边界。
- `Max_nodes=150`只限制单个事件可列出的滴头中心数，不限制每个中心节点的动态宽度计算。
- 事件结束后强制`WetRadius=0`，同时清除收缩计数，避免下一事件继承旧湿润范围。
- 扩展和收缩只改变滴灌通量分配，不直接强行改写`WaterMover()`的边界求解逻辑。

通量分配保持水量守恒：

- 先计算中心滴头需求通量`SourceDemandFlux = wAppl / (1/24) * Width(center)`。
- 根据压力因子得到实际进入边界的`SourceFlux`。
- 按当前湿润范围内各地表边界段总宽度`TotalWidth`分摊为面通量；`TotalWidth`不会超过`DripWetWidthMax`允许的离散边界段组合。

### 压力近似

当前压力修正仍是地表源项近似：

- `DripMode=0`：无压力修正，压力因子为1。
- `DripMode=1`：用地表源节点压力头做背压近似。
- `DripMode=2`：低于`DripPcMin`时按指数缩放，作为压力补偿近似。
- `DripPcMax`目前仍只是输入、校验和存储字段，Fortran逻辑尚未使用上限压力补偿。

## G05新增诊断

`PuSurface.ins`扩展了滴灌输出公共变量，`OUTPUT.FOR`在G05末尾新增以下列：

- `DripDemand`：本输出间隔内压力修正前的请求滴灌量，网格平均`mm`。
- `DripInput`：本输出间隔内压力修正后实际写入地表边界的滴灌量，网格平均`mm`。
- `DripPressureLoss`：`DripDemand - DripInput`，表示压力修正导致未供给的水量，网格平均`mm`。
- `DripHydraulicExcess`：`WaterMover()`求解后，按滴灌通量占比分摊的地表水力未入渗诊断量，网格平均`mm`。
- `DripWetNodesMean`：输出间隔内湿润地表节点数均值。
- `DripWetNodesMax`：输出间隔内湿润地表节点数最大值。
- `DripWetWidthMean`：输出间隔内湿润地表宽度均值，单位`cm`。
- `DripWetWidthMax`：输出间隔内湿润地表宽度最大值，单位`cm`。
- `DripPressureFactorMean`：输出间隔内压力因子均值。
- `DripPressureFactorMin`：输出间隔内压力因子最小值。
- `SeasDrip`：季节累计滴灌输入，网格平均`mm`。

注意：

- `CumRain`仍会包含通过`Varbw_Air`进入的滴灌水量；区分滴灌水量应看`DripInput`和`SeasDrip`。
- `DripPressureLoss`是“压力修正后未供给”的水，不进入水分边界。
- `DripHydraulicExcess`是求解后诊断量，不是新增水源或水汇；它用于判断滴灌覆盖节点上有多少潜在入流没有被当前步实际接纳。

## Python输入和验证链路

`maizsim_inputs/drip.py`当前负责：

- 校验Excel中的`Drip`和`DripNodes`表。
- 解析`.grd`中的地表边界节点和`Width`。
- 优先使用`DripNodes.nodes`显式节点。
- 没有显式节点时，用`Drip.Distance`映射最近地表边界节点。
- 写出旧6字段、扩展11字段或带`DripWetWidthMax`的12字段`.drp`。

`drip_validation.py`当前负责：

- 解析`.drp`旧6字段、扩展11字段和扩展12字段。
- 计算理论网格平均滴灌需求量。
- 读取G05水量列和新增滴灌诊断列。
- 支持按日期比较基线与滴灌算例差值。

`drip_regression.py`当前负责：

- 构造3种土壤、3种网格、5类场景的45个真实模型回归矩阵。
- 按土壤把HYDRUS校准或fallback的`DripWetWidthMax`写入每个滴灌场景。
- 运行真实`2dMAIZSIM.exe`。
- 校验`G03/G05`存在。
- 校验新增G05诊断列为硬契约，缺列会失败。
- 校验`DripDemand`、`DripInput`、`DripPressureLoss`闭合。
- 校验湿润节点/湿润宽度均值不超过最大值。
- 校验压力因子在`0`到`1`之间。
- 校验非压力场景压力损失接近0、压力因子接近1。
- 校验压力修正场景不会超过对应未修正场景。

`hydrus_drip_calibration.py`当前负责：

- 固化HYDRUS SurfaceDrip公开图数字化目标。
- 砂壤土：HYDRUS 2 h饱和半径约`8.15 cm`，映射为`DripWetWidthMax=16.3 cm`。
- 壤土：HYDRUS 2 h饱和半径约`19.85 cm`，映射为`DripWetWidthMax=39.7 cm`。
- 黏壤土：HYDRUS公开SurfaceDrip图无目标，返回`20.0 cm`fallback并标记来源为`fallback_no_hydrus_surface_drip_target`。

## HYDRUS标定DripWetWidthMax

### 标定依据

HYDRUS Technical Manual 2D/3D V5在“Surface Drip Irrigation - Dynamic Evaluation of the Wetted Area”中说明：地表滴灌通量先施加到代表滴头的单个边界节点；若接纳该通量需要正压力头，则该节点改为零压力头边界，并把未接纳的超额通量继续施加到相邻节点，直到通量被接纳并得到湿润半径。

Lazarovitch等2023年公开资料的SurfaceDrip示例使用HYDRUS土壤库中的砂壤土和壤土，滴头流量为`2 L/h`，总施水量为`4 L`，Figure 8给出饱和区半径随时间变化。这里把Figure 8数字化，并把`DripWetWidthMax`定义为地表全湿润宽度：

```text
DripWetWidthMax = 2 * HYDRUS saturated-zone radius
```

数字化工件：

- `tmp/codex_hydrus_calibration/Lazarovitch_et_al_2023.pdf`
- `tmp/codex_hydrus_calibration/page30-030.png`
- `tmp/codex_hydrus_calibration/hydrus_surface_drip_digitized_targets.csv`
- `tmp/codex_hydrus_calibration/hydrus_surface_drip_calibration_summary.csv`
- `tmp/codex_hydrus_calibration/hydrus_surface_drip_digitized_targets.png`

### 标定结果

| 土壤 | HYDRUS条件 | 2 h饱和半径 | MAIZSIM `DripWetWidthMax` |
| --- | --- | --- | --- |
| `sandy_loam` | `2 L/h`，总`4 L` | `8.15 cm` | `16.3 cm` |
| `loam` | `2 L/h`，总`4 L` | `19.85 cm` | `39.7 cm` |
| `clay_loam` | HYDRUS公开图无目标 | 无 | `20.0 cm` fallback |

解释：

- 砂壤土和壤土现在是HYDRUS公开SurfaceDrip图约束下的第一版标定值。
- 黏壤土不是HYDRUS标定值，保留`20.0 cm`只是为了继续覆盖当前回归矩阵中的低导水率入渗受限行为。
- MAIZSIM当前网格用离散地表边界段表示湿润宽度。例如基础网格中心节点宽度为`4.84 cm`，相邻一圈总宽度为`15.08 cm`，因此`16.3 cm`目标在当前基础网格上会离散为不超过`15.08 cm`的一圈扩展。
- 壤土`39.7 cm`略大于基础网格总地表宽度`38.1 cm`，严格复现HYDRUS壤土2 h目标需要更宽或更细的地表网格；当前回归中壤土没有触发横向扩展，因此该上限没有造成满宽扩散。

## 已运行验证

### 构建

命令：

```powershell
MSBuild.exe .\maizsim07.sln /p:Configuration=Release /p:Platform=x64
```

结果：

- 构建成功。
- 输出`build/maizsim/x64/Release/2dMAIZSIM.exe`和`Maizsim.dll`。
- 0个错误。
- 保留项目既有C++/Fortran警告。

### Python单元测试

命令：

```powershell
pixi run --manifest-path pixi.toml python -m unittest discover -s DA_Framework\tests
```

结果：

- 66个测试通过。

滴灌相关快速测试：

```powershell
pixi run --manifest-path pixi.toml python -m unittest DA_Framework.tests.test_drip_validation DA_Framework.tests.test_drip_regression DA_Framework.tests.test_maizsim_drip_inputs
```

结果：

- 31个测试通过。

### 输入dry-run

命令：

```powershell
pixi run --manifest-path pixi.toml check
```

结果：

- 配置校验通过。
- dry-run完成，未复制宏工作簿，未调用Excel，未改写运行文件。

### 真实模型回归矩阵

命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.drip_regression --workspace tmp\codex_drip_regression_hydrus_calibrated --keep-workspace --timeout-seconds 300
```

结果：

- 45个真实模型运行全部通过。
- 范围：3种土壤、3种网格、5类场景。
- 场景：`baseline`、`long_low_single`、`long_multi_node`、`long_high_single`、`long_pressure_single`。
- JSON摘要已保存到`tmp/codex_hydrus_calibration/hydrus_calibrated_regression_summary.json`。
- 本轮显式滴灌湿润宽度上限：`sandy_loam=16.3 cm`，`loam=39.7 cm`，`clay_loam=20.0 cm fallback`。

矩阵总量：

- `DripInput = 3116.089 mm`
- `DripDemand = 3116.232 mm`
- `DripPressureLoss = 0.144 mm`
- `DripHydraulicExcess = 2.758 mm`
- 理论需求量`expected_drip = 3115.502362 mm`
- `Runoff = 141.776 mm`

关键回归现象：

- 所有基线算例`DripInput=0`、`DripDemand=0`。
- 所有非压力滴灌场景`DripPressureLoss=0`，压力因子为1。
- 壤土和砂壤土单滴头场景基本保持单地表节点湿润，`DripWetNodesMax=1`。
- 砂壤土所有滴灌场景`DripWetWidthMax`最高为`8.475 cm`，低于HYDRUS标定上限`16.3 cm`。
- 壤土所有滴灌场景`DripWetWidthMax`最高为`8.475 cm`，低于HYDRUS标定上限`39.7 cm`。
- 黏壤土单滴头场景因入渗受限扩展到相邻节点，`DripWetNodesMax=3`，`DripWetWidthMax`为`11.31`到`18.85 cm`，低于`20.0 cm`fallback上限。
- 黏壤土多节点基础网格场景最大湿润宽度为`19.31 cm`，仍低于`20.0 cm`fallback上限。
- 压力修正场景没有超过对应未修正高强度场景。
- `DripHydraulicExcess`只在部分入渗受限场景出现，量级远小于总滴灌需求，作为诊断量合理。

## 修订前问题定位

修订前，为区分“算例本身导致的水分响应”和“当前代码机制导致的湿润范围铺开”，补充运行了13个真实模型算例，并形成8组`drip - baseline`差值对照：

- 土壤对照：`loam`、`sandy_loam`、`clay_loam`。
- 强度对照：`long_low_single`、`long_high_single`。
- 网格宽度对照：`narrow_x075`、`base_x100`、`wide_x125`，用于检查黏壤土高强度场景是否只是特定横向尺度导致。
- 这不是完整的3土壤×3网格×2强度全因子矩阵；设计重点是基础网格下的土壤/强度对照，加上黏壤土高强度的网格宽度敏感性。

本地生成的诊断工件位于`tmp/codex_drip_contrast_figures/`：

- `drip_contrast_summary.csv`：8组差值对照的汇总数据。
- `drip_contrast_summary.png`：湿润宽度比例、满宽天数、峰值含水量差值和水力超量。
- `drip_contrast_delta_theta_soil_intensity_0612.png`：2007-06-12土壤和滴灌强度二维含水量差值。
- `drip_contrast_delta_theta_grid_0612.png`：2007-06-12黏壤土高强度网格宽度二维含水量差值。

关键数值结论：

- 所有8组非基线对照的`DripWetWidthMax / surface_width`均为`1.0`。
- 所有8组对照的满宽天数均为`45`天。
- 活跃滴灌日的平均湿润宽度比例为`0.9507`到`0.9919`，说明不是偶发瞬时铺满，而是大部分滴灌活动期间接近满宽。
- 峰值`Δθ`随土壤和强度变化明显：砂壤土低强度约`0.0625`，砂壤土高强度约`0.0915`，壤土高强度约`0.124`，黏壤土高强度约`0.168`到`0.180`。
- `DripHydraulicExcess`和径流主要出现在黏壤土场景：黏壤土低强度`DripHydraulicExcess=0.101 mm`、`Runoff=12.853 mm`；黏壤土高强度约`0.320 mm`、`15.583 mm`。壤土和砂壤土对应对照中这两项为`0`。

由此可分开判断：

- 滴灌是否有作用：有。二维`Δθ`图显示滴灌相对基线增加了表层到根区上部含水量，且土壤和强度变化会改变增湿幅度。
- 湿润范围为何看起来横向铺开：主要不是单一黏壤土高强度算例导致。即使换成壤土、砂壤土、低强度，或把横向网格缩放到`0.75`和`1.25`，湿润宽度最大值仍达到整个地表边界。
- 更准确的解释：算例条件决定`Δθ`大小、径流和入渗受限强弱；当前湿润范围扩展算法和10个地表节点的离散尺度决定了`DripWetWidth`容易扩到满宽。

修订前代码证据：

- [Soil Source/Drip.FOR](<Soil Source/Drip.FOR>)将所有`abs(CodeW)==4`的地表水分边界节点纳入`DripSurfNode`/`DripSurfBnd`，并按横向位置排序。
- 扩展触发条件较宽：当前湿润范围内任一节点满足`hNew >= 0`、`RO > DripTol`或`Q - QAct > DripTol`，就设置`NeedExpand=1`。
- 扩展上限`MaxRadius=max(CenterPos-1,DripSurfCount-CenterPos)`来自地表节点端点，不是物理湿润半径或滴头控制宽度。因此达到上限时，`LeftPos=1`、`RightPos=DripSurfCount`，等价于覆盖全部地表水分边界。
- 扩展后按`TotalWidth=sum(Width(...))`计算活动地表宽度，并用`AddRate=SourceFlux/TotalWidth`把滴灌通量近似均匀分摊到活动宽度内。
- [Soil Source/Watmov.for](<Soil Source/Watmov.for>)中的`QAct`和`RO=max(Q-QAct,0)`会作为下一次`Drip()`判断的入渗受限信号，因此长期滴灌事件会持续推动或维持扩展。
- [Soil Source/OUTPUT.FOR](<Soil Source/OUTPUT.FOR>)输出的`DripWetWidthMean`和`DripWetWidthMax`是上述边界重分配宽度诊断，不是独立反演得到的实测湿润体宽度。

因此，修订方向是：保留HYDRUS式地表边界动态重分配思想，但增加物理湿润宽度上限，并把扩展触发收紧到`WaterMover()`确认的`RO`入渗受限信号。

## 修订后二维验证

修订后使用`tmp/codex_drip_regression_bounded_ro`中的真实模型输出重新生成二维图和汇总数据。图件位于`tmp/codex_drip_bounded_figures/`：

- `bounded_drip_soil_summary.csv`：砂壤土、壤土、黏壤土基础网格高强度滴灌对照汇总。
- `bounded_drip_summary_bars.png`：最大湿润宽度、活跃平均宽度、峰值`Δθ`和峰值根系响应。
- `bounded_theta_delta_soils_dates.png`：2007-05-29、2007-06-12、2007-06-30三种土壤的二维`Δθ = drip - baseline`。
- `bounded_root_density_soils_dates.png`：同日期滴灌算例二维根系密度`RDenM + RDenY`。
- `bounded_root_delta_soils_dates.png`：同日期二维根系密度差值`drip - baseline`。

关键结果：

- 砂壤土：`DripWetWidthMax=4.84 cm`，`DripWetNodesMax=1`，没有`DripHydraulicExcess`或径流；峰值`Δθ=0.1398`。
- 壤土：`DripWetWidthMax=4.84 cm`，`DripWetNodesMax=1`，没有`DripHydraulicExcess`或径流；峰值`Δθ=0.1930`。
- 黏壤土：`DripWetWidthMax=15.08 cm`，`DripWetNodesMax=3`，`DripHydraulicExcess=0.286 mm`、`Runoff=11.797 mm`；峰值`Δθ=0.2420`。
- 三种土壤的活跃平均湿润宽度都约为`4.84`到`4.91 cm`，说明扩展只在入渗受限时短时发生，不再长期铺满整个地表。

二维图判断：

- `bounded_theta_delta_soils_dates.png`显示滴灌增湿集中在滴头附近并向下传播，2007-06-12最明显，2007-06-30仍有根区水分差异，但不再表现为全地表同幅增湿。
- `bounded_root_density_soils_dates.png`显示根系分布主要由作物生长阶段控制，2007-06-30根系集中在约`0`到`35 cm`土层。
- `bounded_root_delta_soils_dates.png`显示滴灌相对基线改变根系空间分布，但响应滞后于土壤水分变化，且不是简单“哪里滴水哪里立即长根”。

当前结论：修订后的代码更接近HYDRUS地表滴灌边界处理思路。它仍是地表边界近似，不是地下滴头内部源项模型；但相对于修订前，横向湿润范围已经受到物理宽度上限和`RO`触发条件约束，二维土壤水分图与根系图也显示出更合理的局部响应。

## HYDRUS标定后二次二维补验

为回答“壤土和砂壤土是否已通过算例和二维图像细致验证”，补充使用`tmp/codex_drip_regression_hydrus_calibrated`中的HYDRUS标定版真实模型输出，重新生成壤土和砂壤土的二维图件和汇总表。分析脚本为`tmp/codex_hydrus_2d_validation.py`，图件和CSV位于`tmp/codex_hydrus_2d_validation/`：

- `hydrus_calibrated_delta_theta_root_overlay_top60.png`：2007-05-20、2007-06-01、2007-06-15上层`0`到`60 cm`的二维`Δθ = drip - baseline`，并叠加根系密度等值线。
- `hydrus_calibrated_theta_drip_top60.png`：同日期滴灌算例二维`theta`。
- `hydrus_calibrated_root_density_top60.png`：同日期滴灌算例二维根系密度`RDenM + RDenY`。
- `hydrus_calibrated_wetting_diagnostics_loam_sandy.png`：壤土和砂壤土`DripWetWidthMax`、`DripWetNodesMax`时间序列，并标出HYDRUS宽度上限。
- `hydrus_calibrated_2d_validation_summary.csv`：二维补验定量摘要。
- `hydrus_calibrated_stress_spread_summary.csv`：补充高强度应力算例摘要。

二维图中红色倒三角、红色虚线和`drip node 7`文字统一标出滴灌入水位置；虚线表示该地表滴灌节点在剖面中的横向位置。

二维补验关键数值：

| 土壤 | 日期 | 峰值`Δθ` | 上层`0-60 cm`平均`Δθ` | 根系加权`Δθ` | 正增湿-根系重叠指数 |
| --- | --- | --- | --- | --- | --- |
| `sandy_loam` | 2007-05-20 | `0.0870` | `0.0052` | `0.0000` | `0.000` |
| `sandy_loam` | 2007-06-01 | `0.1399` | `-0.0007` | `-0.0032` | `0.068` |
| `sandy_loam` | 2007-06-15 | `0.0910` | `0.0111` | `0.0149` | `0.753` |
| `loam` | 2007-05-20 | `0.0970` | `0.0071` | `0.0000` | `0.000` |
| `loam` | 2007-06-01 | `0.1828` | `-0.0003` | `-0.0017` | `0.074` |
| `loam` | 2007-06-15 | `0.0940` | `0.0183` | `0.0274` | `0.768` |

解释：

- 两种土壤的峰值`Δθ`都出现在滴灌节点`7`对应的地表位置`x=12.24 cm`、深度`0 cm`，说明滴灌输入确实在二维含水量场中产生局部增湿。
- 2007-06-01上层平均`Δθ`略为负，但峰值`Δθ`仍为正，说明滴灌改变了空间分布，而不是让全剖面均匀变湿。
- 到2007-06-15，根系已经集中在约`0`到`30 cm`土层，正增湿区和根区的重叠指数升至约`0.75`，说明滴灌效应已经进入主要根区。
- 这批代表算例不能证明`16.3 cm`和`39.7 cm`上限的物理充分性，因为壤土和砂壤土实际`DripWetNodesMax=1`，`DripWetWidthMax=4.84 cm`，没有触发横向扩展。

补充高强度应力算例用于检查“是否只是常规算例太弱”：在基础网格上把`wAppl`提高到`2.0 cm/hr`，持续2007-05-01到2007-05-05，仍得到：

| 土壤 | `DripInput` | `DripHydraulicExcess` | `DripWetNodesMax` | 实际`DripWetWidthMax` | 配置上限 |
| --- | --- | --- | --- | --- | --- |
| `sandy_loam` | `243.892 mm` | `0.001 mm` | `1` | `4.84 cm` | `16.3 cm` |
| `loam` | `243.916 mm` | `0.430 mm` | `1` | `4.84 cm` | `39.7 cm` |

因此，当前壤土和砂壤土验证结论应写成：

- 已验证HYDRUS标定宽度被正确写入`.drp`，且真实模型回归不越界。
- 已验证二维含水量场和根系分布图中能看到滴灌导致的局部增湿及后期根区重叠。
- 尚未验证壤土和砂壤土会按HYDRUS上限扩展到`16.3 cm`或`39.7 cm`，因为当前`RO`触发条件和这些土壤的入渗能力使活动宽度保持在单中心地表节点。
- 若目标是精细复现HYDRUS湿润半径曲线，需要专门构造更细地表网格和HYDRUS同条件对照，而不是只依赖当前作物季节长程回归算例。

## 全面综合验证

进一步对HYDRUS标定版45个真实回归算例做矩阵级、二维空间级和触发条件级综合验证。验证脚本为`tmp/codex_hydrus_comprehensive_validation.py`，输出位于`tmp/codex_hydrus_comprehensive_validation/`：

- `case_matrix_diagnostics.csv`：45个算例的水量闭合、湿润宽度、压力因子和上限比例。
- `spatial_delta_root_diagnostics.csv`：每个土壤、网格、滴灌场景在2007-05-20、2007-06-01、2007-06-15的二维`Δθ`、正增湿范围和根区重叠。
- `source_trigger_diagnostics.csv`：滴灌源节点`hNew`、水力超量、径流和湿润宽度扩展天数。
- `validation_check_summary.csv`：综合检查项的通过/需复核状态。
- `case_matrix_wet_width_vs_limit.png`：各土壤、网格、场景的实际最大湿润宽度与配置上限。
- `case_matrix_water_balance.png`：滴灌输入残差、水力超量和径流诊断。
- `spatial_delta_root_metrics.png`：基础网格低/高强度场景的二维峰值`Δθ`、根区重叠和正增湿深度。
- `source_trigger_diagnostics.png`：源节点压力头、水力超量和宽度扩展触发关系。
- `delta_theta_high_single_all_soils_0601.png`：2007-06-01基础网格低/高强度三种土壤二维`Δθ`对照。

二维`Δθ`对照图中同样用红色倒三角、红色虚线和`drip node 7`文字标出滴灌发生位置，便于直接判断增湿区是否位于滴灌节点下方。

综合检查结果：

| 检查项 | 数值 | 状态 | 解释 |
| --- | --- | --- | --- |
| 算例数量 | `45` | pass | 覆盖3种土壤、3种网格、5类场景。 |
| `DripDemand - DripInput - DripPressureLoss`最大绝对残差 | `0.001 mm` | pass | 滴灌需求、实际输入和压力损失闭合。 |
| 湿润宽度上限越界数 | `0` | pass | 所有算例实际湿润宽度均未超过配置上限。 |
| 壤土/砂壤土宽度扩展算例数 | `0` | review | 两个HYDRUS标定土壤的宽度上限没有被动态触发。 |
| 黏壤土宽度扩展算例数 | `12` | pass | 黏壤土所有非基线场景均触发有界横向扩展。 |
| 二维正增湿记录数 | `108` | pass | 所有选定日期、土壤、网格、滴灌场景均检测到局部正增湿。 |
| 后期壤土/砂壤土根区重叠最小比例 | `1.0` | pass | 2007-06-15基础网格高强度场景中，正增湿节点均落在已有根系节点内。 |

矩阵级关键数值：

| 土壤 | 最大实际湿润宽度 | 最大上限比例 | 最大`DripHydraulicExcess` | 最大径流 |
| --- | --- | --- | --- | --- |
| `sandy_loam` | `8.475 cm` | `0.520` | `0.007 mm` | `0.000 mm` |
| `loam` | `8.475 cm` | `0.213` | `0.006 mm` | `0.000 mm` |
| `clay_loam` | `19.31 cm` | `0.965` | `0.289 mm` | `13.528 mm` |

触发条件诊断：

- 壤土和砂壤土12个非基线场景均没有横向扩展，最大源节点日输出`hNew`仍为负值，分别约`-23.5 cm`和`-18.3 cm`；最大单日`DripHydraulicExcess`仅`0.006`到`0.007 mm`。
- 黏壤土12个非基线场景均出现横向扩展，最大扩展天数为`5`天，最大单日`DripHydraulicExcess`约`0.114 mm`，说明当前`RO`触发逻辑能在低导水率、入渗受限条件下启动扩展。
- 2007-06-01基础网格高强度场景中，峰值`Δθ`均在滴灌节点下方地表：砂壤土`0.1399`、壤土`0.1828`、黏壤土`0.2000`。正增湿最大深度约为砂壤土`29.8 cm`、壤土`27.5 cm`、黏壤土`20.0 cm`。

综合判断：

- 数值闭合和上限约束可靠：当前实现没有水量闭合异常，也没有湿润宽度越界。
- 二维水分响应可靠：滴灌局部增湿在所有选定二维对照中可检测，并随土壤、网格和强度改变。
- 根区影响有证据：后期正增湿区与根区重叠明显，说明滴灌效应不是只停留在表面诊断列。
- HYDRUS宽度标定仍未被充分动态验证：壤土和砂壤土的`16.3 cm`、`39.7 cm`当前只是写入并作为保护上限存在，真实运行没有扩展到该上限。若论文或报告中需要声称“复现HYDRUS湿润半径”，必须补做专用HYDRUS同条件短时算例和更细地表网格验证。

## 公开资料依据

当前思路与HYDRUS地表滴灌动态湿润区思想一致：先把滴灌通量给滴头边界节点；若该节点需要正压才能接纳指定通量，则切换或扩展到相邻边界节点，把超额通量继续分配，直到通量被接纳并得到湿润范围。Gärdenäs等2005年也描述了通过计算湿润地表面积实现可变积水边界。

参考资料：

- HYDRUS Technical Manual 2D/3D V5：<https://www.pc-progress.com/downloads/Pgm_Hydrus3D5/HYDRUS_Technical_Manual_2D3D_V5.pdf>
- Lazarovitch, N., Šimůnek, J., Shani, U., & Or, D. 2023. Modeling of irrigation and related processes with HYDRUS. <https://www.pc-progress.com/Documents/Jirka/Lazarovitch_et_al_2023.pdf>
- Gärdenäs, A. I., Hopmans, J. W., Hanson, B. R., & Šimůnek, J. 2005. Two-dimensional modeling of nitrate leaching for various fertigation scenarios under micro-irrigation. <https://www.pc-progress.com/Documents/Jirka/Agri_water_manag_2005_FREP.pdf>
- HYDRUS water boundary conditions：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/WaterFlowBoundaryConditions1.html>

## 当前限制

仍未完成或不属于本轮范围的内容：

- 未实现地下滴灌源项。
- 未实现严格HYDRUS式地下埋设滴头物理模型。
- `DripPcMax`尚未实际参与Fortran压力补偿。
- 未与实测湿润体剖面、土壤含水量剖面或滴头实测出流做参数校准。
- `DripHydraulicExcess`是滴灌归因诊断，不替代完整地表径流质量平衡。
- `DripWetWidthMax`目前只完成HYDRUS SurfaceDrip公开图中砂壤土和壤土两个目标的第一版校准；黏壤土、其它流量、其它施水量和其它滴头间距仍需要额外HYDRUS工程或实测数据。
- 壤土和砂壤土HYDRUS宽度上限在当前代表算例中没有被实际触发；这些上限当前主要作为防止过度横向扩展的物理保护边界，而不是已被完整湿润半径曲线验证的动态响应。
- Fortran省略输入时的`20 cm`仍是兼容旧`.drp`的内部fallback，不应解释为通用实测滴灌湿润体宽度。
- 当前10个地表节点网格较粗，连续HYDRUS半径会被离散成若干边界段宽度；若要严格拟合半径曲线，需要更细的地表网格或专门的HYDRUS对照网格。

## 后续建议

短期建议：

- 保存`drip_regression.py`输出JSON和关键G05样本，形成审计级验证工件。
- 决定是否实现`DripPcMax`上限压力补偿；若暂不实现，应在用户输入文档中明确说明。
- 若要继续提高可解释性，可增加一个只读报告脚本，自动汇总G05中的滴灌诊断列。
- 扩展HYDRUS标定矩阵，至少补齐黏壤土、不同滴头流量、不同施水量和不同滴头间距。
- 若需要更精细的地表湿润体，可进一步把活动宽度内的均匀分摊改成按距离和局部入渗能力加权分配。

长期路线：

- 若目标转为地下滴灌，应新增独立地下源项数组，而不是复用本轮地表边界逻辑。
- 地下滴头背压、压力补偿和湿润体形态应基于HYDRUS对照算例或实测数据重新设计。
