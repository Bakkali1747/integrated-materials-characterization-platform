# 项目与样品工作区

v0.16.0 在 Phase B 基础上补齐工作区 schema 版本与迁移，接入实测 S 参数和 VSM 磁滞回线分析。桌面界面的“工作区”页面可创建项目、创建样品、关联 Electromagnetic / VSM / XRD 测试，并从 Electromagnetic 或 VSM 测试发起分析，完成后自动登记 AnalysisRun。

## 数据组织

工作区使用以下层级：

```text
Project
└── Sample
    ├── Measurement
    └── AnalysisRun
```

源码运行时数据位于项目目录的 `workspace/`，安装版位于 `%LOCALAPPDATA%\IntegratedMaterialsCharacterizationPlatform\workspace`。每个项目、样品、测试和分析运行均保存为独立 UTF-8 JSON 文件。AnalysisRun 是追加记录，同一测试采用不同参数重新分析时不会覆盖旧运行。

## Schema 版本与迁移

工作区根目录的 `workspace.json` 记录 `schema_version`、布局、创建/迁移时间和软件版本。v0.15.0 的当前版本为 **v1**。

- 全新工作区：自动创建 `workspace.json`。
- v0.13 / v0.14 旧工作区（没有 `workspace.json`）：首次打开时视为 v0，只读校验全部实体 JSON 后写入 v1 标记；已有项目、样品、测试和运行文件不改写。
- 旧工作区存在损坏 JSON：拒绝迁移并显示具体文件，不写入版本标记，避免半个工作区继续运行。
- `schema_version` 高于当前程序：拒绝打开并提示使用更新版本，现有数据不被修改。
- 后续结构变化在 `core/common/workspace_schema.py` 的 `MIGRATIONS` 中按版本追加，并递增 `SCHEMA_VERSION`。

界面顶部显示当前 schema 版本与工作区路径；迁移或新建会明确标注。工作区无法打开时，工作区页面显示原因并禁用写入操作，客户端其他页面仍可使用。

## 原始文件保护

添加测试时，平台只保存原始文件的绝对路径和 SHA-256。平台不会自动复制、移动、重命名或修改原始文件。再次核验时可区分 `PASS`、`CHANGED` 和 `MISSING`。

开始工作区分析前会重新核验来源：只要任一原始文件为 `CHANGED` 或 `MISSING`，界面拒绝开始分析。分析完成后登记运行前还会再次比较分析记录中的 SHA-256 与测试登记值；不一致时不写入 AnalysisRun，也不修改测试状态。

## 从测试开始分析

1. 在项目样品表选择样品，进入“样品详情”。
2. 选择一个 Electromagnetic 测试：
   - 有 `.memp`、CSV 或 Excel 时，可点击“用此测试开始电磁分析”；
   - 有 `.sdat` 时，可点击“用此测试开始S参数分析”。
3. 选择 VSM 测试时，可点击“用此测试开始VSM分析”；磁场/磁矩单位、样品质量与背景扣除仍需在 VSM 页面显式确认。
4. 平台切换到对应页面并载入原始文件；参数仍由用户确认并显式点击开始。
5. 分析完成后自动创建 AnalysisRun，并把项目/样品/测试上下文写回工作区。

“核验来源文件”随时显示 `PASS` / `CHANGED` / `MISSING` 计数，不修改原始文件。日常模式下触发 S 参数分析会临时切换到完整模式以显示该页面。

## 分析运行记录

每次成功分析生成一条 AnalysisRun，包含：

- 分析类型与引擎版本：`electromagnetic_rl`、`s_parameters` 或 `vsm_hysteresis`；引擎版本为软件版本 + 分析缓存/解析器版本。
- 完整数值参数快照：电磁分析保存配置，S 参数保存字段映射、容差与 schema 状态，VSM 保存单位、质量与背景配置。
- 源文件 SHA-256、Git 提交。
- 结果目录、摘要/矩阵等数值产物的绝对路径（`result_refs`）。
- 已保存图片路径（`plot_refs`）。
- 显式导出的图片路径（`export_refs`），在保存当前图片或导出全部图片后追加。
- 警告列表与平台科研状态；S 参数会把逐点 QC 警告合并进运行警告。

“样品详情”下方的“分析运行”表列出该测试的全部历史运行，可打开结果目录，或点击“载入运行结果”按运行类型只读恢复已保存数值与摘要（电磁 / S 参数 / VSM）。载入使用已保存产物，不重新计算。

## 科研状态

平台级状态统一为 `VALIDATED`、`PENDING`、`WARNING`、`NOT COMPUTABLE`、`UNSUPPORTED` 和 `FAILED`。

- 新添加的测试默认为 `PENDING`。
- 成功分析且没有警告时，测试状态保持 `PENDING`；有警告时为 `WARNING`。
- S 参数 schema 仍为 `candidate_high_confidence`，不会因为登记而升级。
- 失败或取消的运行不登记为 AnalysisRun。
- 仅建立文件关联或完成一次计算都不会自动升级为 `VALIDATED`；`VALIDATED` 仍需外部定义确认或人工评审。

## 当前边界

工作区已打通 Measurement → 分析 → AnalysisRun 的闭环，覆盖电磁 ε/μ、实测 S 参数和 VSM 磁滞回线。XRD 的解析、分析、绘图、导出及报告属于 Phase D。工作区备份/恢复、项目导入/导出和多用户并发写入尚未实现。
