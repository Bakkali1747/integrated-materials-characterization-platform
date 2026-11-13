# 项目与样品工作区

v0.14.0 实现 PRD Phase B：电磁分析已接入样品工作区。桌面界面的“工作区”页面可创建项目、创建样品、关联 Electromagnetic / VSM / XRD 测试，并从 Electromagnetic 测试直接发起分析，完成后自动登记 AnalysisRun。

## 数据组织

工作区使用以下层级：

```text
Project
└── Sample
    ├── Measurement
    └── AnalysisRun
```

源码运行时数据位于项目目录的 `workspace/`，安装版位于 `%LOCALAPPDATA%\IntegratedMaterialsCharacterizationPlatform\workspace`。每个项目、样品、测试和分析运行均保存为独立 UTF-8 JSON 文件。AnalysisRun 是追加记录，同一测试采用不同参数重新分析时不会覆盖旧运行。

## 原始文件保护

添加测试时，平台只保存原始文件的绝对路径和 SHA-256。平台不会自动复制、移动、重命名或修改原始文件。再次核验时可区分 `PASS`、`CHANGED` 和 `MISSING`。

开始工作区分析前会重新核验来源：只要任一原始文件为 `CHANGED` 或 `MISSING`，界面拒绝开始分析。分析完成后登记运行前还会再次比较分析记录中的 SHA-256 与测试登记值；不一致时不写入 AnalysisRun，也不修改测试状态。

## 从测试开始电磁分析

1. 在项目样品表选择样品，进入“样品详情”。
2. 选择一个 Electromagnetic 测试，点击“用此测试开始电磁分析”。
3. 平台切换到“电磁性能”页面并载入该测试的原始文件；参数仍由用户确认。
4. 点击“开始分析”，分析完成后自动创建 AnalysisRun，并把该项目/样品/测试上下文写回工作区。

“核验来源文件”随时显示 `PASS` / `CHANGED` / `MISSING` 计数，不修改原始文件。

阶段 B 只接入 `.memp`、CSV、Excel 的 ε/μ 数据。实测 `.sdat` 仍使用独立“S参数分析”页面；它不会冒充 ε/μ 输入，也尚未自动登记为 AnalysisRun。

## 分析运行记录

每次成功分析生成一条 AnalysisRun，包含：

- 分析类型与引擎版本（软件版本 + 分析缓存版本）。
- 完整数值参数快照。
- 源文件 SHA-256、Git 提交。
- 结果目录、摘要/矩阵等数值产物的绝对路径（`result_refs`）。
- 已保存图片路径（`plot_refs`）。
- 显式导出的图片路径（`export_refs`），在“保存当前图片”或“导出全部图片”后追加。
- 警告列表与平台科研状态。

“样品详情”下方的“分析运行”表列出该测试的全部历史运行，可打开结果目录，或点击“载入运行结果”在电磁性能页面只读恢复已保存数值与摘要。载入使用已保存产物，不重新计算。

## 科研状态

平台级状态统一为 `VALIDATED`、`PENDING`、`WARNING`、`NOT COMPUTABLE`、`UNSUPPORTED` 和 `FAILED`。

- 新添加的测试默认为 `PENDING`。
- 成功分析且没有警告时，测试状态保持 `PENDING`；有警告时为 `WARNING`。
- 失败或取消的运行不登记为 AnalysisRun。
- 仅建立文件关联或完成一次计算都不会自动升级为 `VALIDATED`；`VALIDATED` 仍需外部定义确认或人工评审。

## 当前边界

Phase B 已打通 Measurement → 分析 → AnalysisRun 的闭环。VSM 和 XRD 的解析、分析、绘图、导出及报告分别属于 Phase C 和 Phase D。工作区尚未提供 schema 版本、备份恢复和项目导入/导出界面。
