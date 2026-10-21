# 实测 S 参数表征与论文报告（v0.10.0）

本版不改变 RL/EAB/阻抗核心公式；S 参数仍为 `candidate_high_confidence`，不冒充厂商确认。

## 实测 S 参数：屏蔽效能与 Smith 图

逐点表新增：

- `SE_R_db` = −10 log10(1−R)
- `SE_A_db` = −10 log10(T/(1−R))
- `SE_T_db` = SE_R + SE_A = −10 log10(T)

其中 R=|S11|²、T=|S21|²。公式基于功率波与相容端口归一化假设；归一化尚未外部确认。
当 R≥1 时 SE_R/SE_A 无定义，保存空值并计数；T=0 时 SE_T=+inf，不裁剪。QC 报告新增
`se_undefined_count` 与 `se_definition`。

S 参数页面新增：

- “Shielding effectiveness (SE)”图：SE_R / SE_A / SE_T 三条曲线；
- “Smith chart”：归一化反射系数平面上的 S11/S22 轨迹与电阻/电抗网格；
- 逐点表增加 SE 三列，仍最多预览前 2000 行。

CLI 的 `run_sparameters.py` 同步生成 `figures/SE.png` 与 `figures/smith.png`。

## 期刊图尺寸

参数面板新增“论文图尺寸”：

- 屏幕 / 默认：7.0 × 4.8 in，11 pt；
- 期刊单栏：3.5 × 2.6 in，8 pt；
- 期刊双栏：7.0 × 4.0 in，9 pt。

单栏/双栏使用色盲友好色板（Okabe–Ito）。该预设只影响新分析生成的图，不改变已有运行。

## 单样品分析报告

入口：

```powershell
.\.venv\Scripts\python.exe run_report.py --run "output/sample_S/20260101T000000_abcd" --output "D:\reports\S.docx"
```

- 生成同基名的 DOCX 与 PDF（`--format docx|pdf|both`）。
- 历史结果页加载运行后，点击“导出分析报告…（DOCX + PDF）”。
- 报告内容：基本信息、结果摘要、ε/μ、RL 曲线、RL 二维图、多厚度叠图（存在时）、
  质量警告、方法与模型边界、追溯信息。
- 正文中文、图内标签英文；报告只保留源文件名与 SHA-256，不写本地绝对路径。
- DOCX 可编辑；PDF 由 ReportLab 直接生成，不依赖 LibreOffice。
- 验证状态、PENDING/candidate 结论不会因生成报告而升级。

## 当前边界

- 不做 NRW 反演 ε/μ；S 参数仍只做候选映射、R/T/A、SE 与一致性筛查。
- 报告面向单样品 ε/μ 分析；S 参数报告与批量报告尚未合并到同一模板。
- 方法段落是通用模型说明，不替代论文中针对具体样品的方法描述。
