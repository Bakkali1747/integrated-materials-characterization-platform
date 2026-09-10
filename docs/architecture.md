# 架构与阶段边界

命令行和 PySide6 桌面 GUI 复用核心模块，不将界面状态放入物理计算。GUI Phase 1 调用关系见 [GUI 使用说明](gui_usage.md)，当前 Phase 2 见 [完整科研图/S参数/比较](gui_phase2.md)，不使用 Streamlit。

数据流：只读原始文件 → parser 显式映射/单位/虚部转换 → validation → 标准化 SampleData → RLResult → EAB/绘图/结果记录。

- core/models.py：数据对象，矩阵方向为 (Nd,Nf)。
- core/units.py：展示单位与 SI 制之间的转换，厚度网格。
- core/parser.py：CSV、Excel（xlsx/openpyxl、xls/xlrd）、已观察中文表头的 memp；不解析未知 sdat。
- core/validation.py：阻止错误数据进入计算，警告不改变原数据。
- core/electromagnetic.py：复数构造唯一入口。
- core/rl_calculator.py：独立的输入阻抗/RL 和极小值定位。
- core/mechanism.py：损耗角、衰减、C0、四分之一波长估算及网格极小值对照。
- core/impedance.py：最佳 RL 点的完整归一化复阻抗。
- core/batch.py：目录发现、清单校验、逐文件解析配置。
- core/sdat_inspector.py：只读无语义结构诊断，不能用于 S 参数计算。
- core/sparameter_mapping.py / sparameter_parser.py / sparameters.py：独立配置、候选解析与 S 参数计算，三层分离。
- run_sparameters.py：候选 S 参数独立入口，状态、源文件哈希和 QC 全部记录。
- plotting：只使用核心结果，所有图统一坐标单位、配色规范。
- export/provenance.py：每次独立目录、来源哈希、版本、配置、失败记录。
- export/phase2_export.py：组织 Phase 2 数据表与绘图，不实现物理公式。
- export/excel_export.py：按项目 Python/openpyxl 技术栈导出批次汇总快照。
- run_batch.py：逐样品故障隔离、公共配置、原生采样比较与汇总。
- run_analysis.py：组织一次分析，不作为数值算法实现位置。

Phase 2 已实现阻抗图/衰减/损耗角/Cole-Cole/C0/四分之一波长。Phase 3 已实现批量/比较，v0.5 新增用户提供的候选 sdat 语义映射；厂商列顺序仍待外部确认。后续规划（当前不实现）：Phase 4 GUI/完整 Excel 报告/完整图片导出；Phase 5 CST 对照。VSM、XRD、Raman、多层结构分别增加独立模块，不修改单层公式含义。

本阶段提前支持这份 memp 是用户确认的范围调整。正式发布依据 VERSIONING.md，阶段结束后等待用户验收。
