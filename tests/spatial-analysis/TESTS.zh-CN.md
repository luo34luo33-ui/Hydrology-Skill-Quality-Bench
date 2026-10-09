# 空间分析测试说明

本文档说明 `tests/spatial-analysis/` 中各测试主要验证什么。执行与评分以各任务的 `task.json`、`data/` 和 `expected/` 为准。

## 共同约定

- 每题只执行一个目标 Skill，上游 artifacts 已预置并带真实 SHA-256。
- 连续高程栅格按容差比较；D8、河段、Strahler 和子流域等分类栅格精确比较。
- GeoPackage 按 CRS、属性和规范化几何比较，不比较 SQLite 文件字节。
- 普通输入错误退出码为 1；拓扑验证中的科学 QC 失败退出码为 2。
- 失败题必须保留原生 `result.json`；未被接受为成果的部分文件应清理。

## DEM 分析网格

目标 Skill：`spatial-analysis/prepare-dem-analysis-grid`

| ID | 测试内容 | 预期 |
|---|---|---|
| `hydrodata-dem-grid-001` | 米制 DEM，多个相邻流域面合并并规范化 | `success` |
| `hydrodata-dem-grid-002` | WGS84 DEM，显式授权自动选择当地 UTM | `success` |
| `hydrodata-dem-grid-003` | 英尺高程和显式米制目标 CRS，检查 0.3048 换算 | `success` |
| `hydrodata-dem-grid-004` | 流域本体完整、外扩 buffer 覆盖不足 | `warning` |
| `hydrodata-dem-grid-005` | DEM 缺失 CRS，禁止猜测 | `error` |
| `hydrodata-dem-grid-006` | 流域 Shapefile 缺失 `.prj`，禁止沿用 DEM CRS | `error` |
| `hydrodata-dem-grid-007` | DEM 未完整覆盖真实流域 | `error` |
| `hydrodata-dem-grid-008` | 多波段 DEM，禁止静默选择波段 | `error` |

## DEM 河网提取

目标 Skill：`spatial-analysis/extract-dem-stream-network`

| ID | 测试内容 | 预期 |
|---|---|---|
| `hydrodata-stream-network-001` | 含洼地的规则米制 DEM 和非空分叉河网 | `success` |
| `hydrodata-stream-network-002` | 非正方形像元，按仿射行列式换算阈值并向上取整 | `success` |
| `hydrodata-stream-network-003` | 大片平坦区和局部洼地的固定 Whitebox D8 链 | `success` |
| `hydrodata-stream-network-004` | 阈值超过最大汇水面积，不得自动降低 | `error` |
| `hydrodata-stream-network-005` | 地理坐标 DEM，禁止把角度当米 | `error` |
| `hydrodata-stream-network-006` | 水平单位为英尺的投影 DEM | `error` |
| `hydrodata-stream-network-007` | 多波段分析 DEM | `error` |
| `hydrodata-stream-network-008` | 河网起始面积为零 | `error` |

## HydroBase 拓扑构建

目标 Skill：`spatial-analysis/build-hydrological-topology`

| ID | 测试内容 | 预期 |
|---|---|---|
| `hydrodata-topology-build-001` | Y 形河网的上下游、层级、长度、面积和稳定 ID | `success` |
| `hydrodata-topology-build-002` | 先在完整 buffer 追踪，再把流域外下游映射为出口 0 | `success` |
| `hydrodata-topology-build-003` | 显式 `all-touched` 边界像元纳入规则 | `success` |
| `hydrodata-topology-build-004` | 原样传播上游 buffer 覆盖 warning | `warning` |
| `hydrodata-topology-build-005` | 保留负高程步证据，不伪造正落差 | `warning` |
| `hydrodata-topology-build-006` | 一个核心栅格偏移半像元 | `error` |
| `hydrodata-topology-build-007` | D8 含不支持的编码值 | `error` |
| `hydrodata-topology-build-008` | 河段形成闭合循环 | `error` |
| `hydrodata-topology-build-009` | 流域内河段缺少正子流域映射 | `error` |

## 拓扑独立验证

目标 Skill：`spatial-analysis/validate-hydrological-topology`

| ID | 测试内容 | 预期 |
|---|---|---|
| `hydrodata-topology-validate-001` | 哈希有效的单出口 HydroBase | `success` |
| `hydrodata-topology-validate-002` | 用户确认的合法双出口系统 | `success` |
| `hydrodata-topology-validate-003` | 传播 build 阶段负高程步 warning | `warning` |
| `hydrodata-topology-validate-004` | 实际出口数与确认值不同 | `error`，退出码 2 |
| `hydrodata-topology-validate-005` | 重复 reach ID | `error`，退出码 2 |
| `hydrodata-topology-validate-006` | 下游引用不存在且上下游不互反 | `error`，退出码 2 |
| `hydrodata-topology-validate-007` | 河段循环和拓扑层级不一致 | `error`，退出码 2 |
| `hydrodata-topology-validate-008` | 子流域表面积与裁切栅格计数不一致 | `error`，退出码 2 |
| `hydrodata-topology-validate-009` | 裁切栅格 CRS/仿射网格不一致 | `error`，退出码 2 |
| `hydrodata-topology-validate-010` | build artifact SHA-256 被篡改 | `error`，退出码 1 |
| `hydrodata-terrain-topidx-001` | 哈希互链的 stream/build/QC 单出口漏斗 DEM（12×8 米制网格） | topographic_index.tif / classes / distance 三产物；slope_clipped_cells=1（仅出口） | `success` / 0 |
| `hydrodata-terrain-topidx-002` | 确认平地（第 4–6 行）使 D8 落差为零 | slope_clipped_cells=25 被原生记录但 status 仍为 success；不得扰动平地 | `success` / 0（无原生 warning 通道） |
| `hydrodata-terrain-topidx-003` | D8 指针使两个像元出盆 | 脚本必须拒绝（"exactly one exit cell"）；不产出任何地形成果 | `error` / 2 |
| `hydrodata-forcing-aggregate-001` | 双站泰森聚合到 2 个已验证子流域（P/E0 双层，coverage=1） | subbasin_forcing.csv / weights.csv / coverage.csv；不重分配权重、不补值 | `success` / 0 |
| `hydrodata-forcing-aggregate-002` | 确认 --target basin（P/PET 双层合并单元） | basin_forcing.csv（time,P,PET）；不得自行加权 | `success` / 0 |
| `hydrodata-forcing-aggregate-003` | E0 源缺 station B 最后一个时步 | 脚本必须拒绝（"missing station at one or more steps"） | `error` / 2 |

## 新增测试模板

```markdown
| `hydrodata-空间能力-XXX` | 只描述一个主要输入或科学异常 | 明确允许与禁止的处理策略 | `success` / `warning` / `error` |
```

新增题应使用小型确定性栅格、固定 CRS/仿射/NoData，并同时记录输出语义、原生状态、退出码和失败时禁止交付的文件。
