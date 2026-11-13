# 项目与样品工作区

v0.13.0 实现 PRD Phase A 的本地数据基础。桌面界面的“工作区”页面用于创建项目、创建样品，并给样品关联 Electromagnetic、VSM 或 XRD 测试文件。

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

## 科研状态

平台级状态统一为 `VALIDATED`、`PENDING`、`WARNING`、`NOT COMPUTABLE`、`UNSUPPORTED` 和 `FAILED`。Phase A 新添加的测试默认为 `PENDING`；仅建立文件关联不会把任何仪器格式或科学算法自动升级为 `VALIDATED`。

## 当前边界

工作区已经能够创建项目、创建样品、添加三类 Measurement，并在样品详情中查看所有表征。现有电磁分析仍可从“电磁性能”页面独立使用；把分析结果自动挂载到 Measurement 属于 Phase B。VSM 和 XRD 的解析、分析、绘图、导出及报告分别属于 Phase C 和 Phase D。
