# PySide6 桌面 GUI · Phase 1

版本 v0.6.0。第一阶段只提供单样品 ε/μ → RL/EAB 的可视化操作。S 参数图、多样品比较、批量界面、完整质量控制、历史结果和设置页按后续阶段开放，当前导航明确提示未实现。不使用 Streamlit，不打包 EXE。

## 启动

在项目目录的 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe run_gui.py
```

新环境先安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gui.txt
```

现有 `run_analysis.py`、`run_batch.py`、`run_sparameters.py` 保持可用。CLI 不需要 PySide6。

## 试用步骤

1. 首页点击“单样品分析”，选择或拖入文件。可多选，也可选择文件夹（仅当前目录，不递归）。先用 `sample_data/synthetic_constant.csv` 试用；该数据是合成测试数据，不是真实材料。
2. 查看文件表中的格式、大小、解析状态、频率与点数。相同目录内同名文件分组，独立文件子项保留各自来源；不同名称不推断为同一样品。
3. 选择一个 `.memp`、`.csv`、`.xlsx` 或 `.xls` 子项。`.sdat` 仅通过现有候选 parser 显示导入信息，不能启动 ε/μ RL 分析；S 参数绘图属于 Phase 2。
4. 设置样品名称、扫描厚度、曲线厚度和阈值。默认 1–5 mm、步长 0.01 mm、曲线 2 mm、阈值 −10 dB。频率裁选默认关闭，默认使用全部原始点。
5. 点击“开始分析”。修改参数不会自动计算。任务期间输入锁定，进度表示阶段完成情况；取消在一次核心调用/文件写入完整结束后生效。
6. 在图类型菜单选择 ε′/ε″、μ′/μ″、指定厚度 RL 曲线或 RL 二维图。工具栏支持缩放和平移。第一阶段不提供二维 hover。
7. 右侧显示已完成运行的快照，包括全部并列 RLmin、最大 EAB 对应厚度/频段、指定厚度 EAB 和所有连续频带。当前输入改变不会修改已完成摘要；重新点击分析生成新运行。
8. “打开结果文件夹”打开该次已完成运行。“保存当前图片”可导出 PNG/TIFF/PDF/SVG，默认 600 dpi。请保存到分析运行目录以外，避免改变已记录的产物哈希。

## 文件配置与验证状态

CSV/Excel 默认要求列名 `frequency_ghz, eps_real, eps_imag, mu_real, mu_imag`。可在导入前提供 JSON 列映射（内部名 → 文件列名）与频率单位。CSV 暂用逗号分隔，Excel 暂用第一个工作表；更多编码/分隔符/工作表选项可继续使用 CLI。

`.memp` 仍采用原已观察中文表头，单位固定 GHz，不接受覆盖列映射。`.xls` 新增 xlrd 引擎；其余处理复用同一正式 parser。`sample_data/synthetic_legacy.xls` 为三行合成数据，用于真实 BIFF 文件读取测试。

[KNOWN] `.memp` 的真实虚部定义和商业软件对照仍待确认。GUI 默认显式临时选择 `loss`，也可选择 `signed`，不提供把真实数据直接升级为已验证的开关。内部约定仍为 ε′−jε″、μ′−jμ″。`signed` 的转换由原 parser 完成一次。

[KNOWN] `.sdat` 始终显示 `candidate_high_confidence`；S21/S12 顺序尚未厂商确认。解析成功不等于完成科研验证。候选/待验证用黄色，解析失败用红色。

[COMMON] 标准 EAB 使用 −10 dB 的最大连续带宽；用户修改阈值时另外报告“指定阈值连续带宽”。不把分离频段相加称为 EAB。沿用核心 linear 阈值交点方法，与缺失数据插值不同。缺失数据插值始终 OFF。

## 结果与错误

每次运行通过现有 `new_run` 创建唯一目录，保存 `parsed_data.csv`、`electromagnetic_parameters.csv`、`RL_matrix.csv`、`RL_curve.csv`、`summary.json`、四类基本 PNG 及 `analysis_record.json/txt`。记录含原文件 SHA-256、源行、软件版本、Git 状态、parser 版本、参数快照、实际网格、虚部约定、验证状态和产物哈希。未用于该次分析的 SDAT schema 标为 `not_applicable`，不把其他来源混入记录。

失败/取消也记录状态；已经生成的数据保留，但不能当作成功报告。上一次成功结果仍可查看。关闭运行中窗口会请求安全取消，待任务结束后再次关闭。后台异常完整写入 `logs/app.log`，界面只展示样品/问题/建议，不弹出 traceback。

## GUI 与 core 调用关系

`MainWindow → SingleSamplePage → AnalysisWorker(QThread) → analysis_controller`

- 导入调用 `core.parser.read_sample` 或独立 `core.sparameter_parser.read_sparameters`。
- 单样品调用 `thickness_grid / make_complex / scan_rl / minimum_points / summarize_bandwidths / absorption_bands`。
- 图形调用 `plot_parameters / plot_rl_curve / plot_rl_2d`。后台生成 Agg Figure，完成后主线程附加 `FigureCanvasQTAgg`；不改原绘图模块的 Agg 后端。
- 追溯调用 `export.provenance.new_run / write_record / artifact_hashes`。
- 独立图片导出重新使用已有结果调用正式绘图 API，不重复计算，采用临时文件写完后替换目标。

GUI 控制器只编排 Phase 1 所需产物，不调用 CLI `main()`，也不包含科学公式。等价性测试比较 GUI 和 CLI 导出的 RL 矩阵及 EAB 摘要。GUI 代码不反向进入 core。

## 测试

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:QT_QPA_PLATFORM
```

`offscreen` 仅用于自动测试；Windows 正常启动请使用默认平台。自动测试不比较图像像素。实际中文布局另外使用 Windows Qt 平台检查。
