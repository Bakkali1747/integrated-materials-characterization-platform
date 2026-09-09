# 架构与阶段边界

Phase 1 使用命令行，后续 Streamlit 界面复用核心模块，不将界面状态放入物理计算。

数据流：只读原始文件 → parser 显式映射/单位/虚部转换 → validation → 标准化 SampleData → RLResult → EAB/绘图/结果记录。

- core/models.py：数据对象，矩阵方向为 (Nd,Nf)。
- core/units.py：展示单位与 SI 制之间的转换，厚度网格。
- core/parser.py：CSV、Excel、已观察中文表头的 memp；不解析未知 sdat。
- core/validation.py：阻止错误数据进入计算，警告不改变原数据。
- core/electromagnetic.py：复数构造唯一入口。
- core/rl_calculator.py：独立的输入阻抗/RL 和极小值定位。
- plotting：只使用核心结果，所有图统一坐标单位、配色规范。
- export/provenance.py：每次独立目录、来源哈希、版本、配置、失败记录。
- run_analysis.py：组织一次分析，不作为数值算法实现位置。

后续规划（当前不实现）：Phase 2 阻抗图/衰减/损耗角/Cole-Cole/C0/四分之一波长；Phase 3 已核实的 sdat/批量/比较；Phase 4 GUI/Excel 报告/完整图片导出；Phase 5 CST 对照。VSM、XRD、Raman、多层结构分别增加独立模块，不修改单层公式含义。

本阶段提前支持这份 memp 是用户确认的范围调整。正式发布依据 VERSIONING.md，阶段结束后等待用户验收。
