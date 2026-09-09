# Phase 3 批量处理与样品比较

## 目录方式

将原始文件放在 Raw_Data 或其子目录。运行：

```powershell
.\.venv\Scripts\python.exe run_batch.py --directory Raw_Data --imaginary-convention loss
```

目录模式把相对路径（去掉扩展名）作为样品名，避免不同子目录下同名文件混淆。重复名称必须改用清单明确命名，不自动覆盖。同一目录配置只适合共享虚部约定、标准列名的文件；异构文件使用下面的清单。

## 清单方式

使用 JSON 指定样品名称、文件路径及逐文件解析配置。路径相对于清单文件，而不是运行命令时所在目录：

```json
{
  "parser_defaults": {"imaginary_convention": "loss", "convention_confirmed": false},
  "analysis": {
    "thickness_min": 1,
    "thickness_max": 5,
    "thickness_step": 0.01,
    "curve_thickness": 2,
    "frequency_min": 2,
    "frequency_max": 18,
    "threshold": -10,
    "eab_crossing": "linear",
    "quarter_wave_orders": [1]
  },
  "samples": [
    {"name": "CIP-1um", "path": "Raw_Data/CIP-1um.memp"},
    {"name": "CIP-SiO2", "path": "Raw_Data/CIP-SiO2.xlsx",
      "parser": {"sheet": "Sheet1", "frequency_unit": "Hz",
        "column_map": {"frequency_ghz":"Frequency", "eps_real":"e1", "eps_imag":"e2", "mu_real":"m1", "mu_imag":"m2"}}}
  ],
  "compare_samples": ["CIP-1um", "CIP-SiO2"]
}
```

上述名称和路径为配置示例，不代表文件已存在。`convention_confirmed` 必须为 JSON 布尔值，不能写字符串 `"false"`。确认前保持 false。

```powershell
.\.venv\Scripts\python.exe run_batch.py --manifest batch.json
.\.venv\Scripts\python.exe run_batch.py --manifest batch.json --compare CIP-1um CIP-SiO2 --dpi 600
```

`--compare` 仅选择绘图曲线，不跳过其他样品的分析。比较顺序遵循选择顺序。目录模式默认扫描 1–5 mm / 0.01 mm，清单模式可配置全部公共分析选项；每个成员记录实际展开后的配置。

## 输出与比较规则

批次独立保存在 `output/batch/时间_唯一编号/`：

- `samples/`：每个样品的 Phase 1–2 数据、图像和独立记录。
- `all_samples_summary.xlsx` / `.csv`：逐样品汇总。
- `comparison/`：ε′、ε″、μ′、μ″、两种 tanδ、α、C0、RL、EAB 共十项图像与对应长表 CSV。
- `batch_record.json` / `.txt`：批次配置、逐文件状态、清单哈希、版本、比较说明及汇总哈希。

Excel 为 Python 科学计算的结果快照，不是在工作簿中重新计算复数公式。Summary 位置列展示首个并列最优结果；RL_minima / EAB_bands 保存所有并列结果，Provenance 保存来源、警告及配置。失败样品数值为空，不以零填充。Summary 的 Calculation status 仅表示软件计算是否成功，Validation 列单独标明外部验证状态。

[COMMON] EAB 一律为固定厚度 RL≤−10 dB 的最大连续带宽。比较 RL 使用相同指定厚度，不拿各样品不同最佳厚度的曲线冒充同厚度对照。各曲线保留自己的频率点，无自动插值或外推。频率网格不一致时明确提示；不能据不同测量范围的汇总直接作同条件排名。

单文件失败后继续其余样品，未选中或失败的比较样品明确记录。命令行退出码：全部成功为 0，部分失败为 2，全部失败或批次流程失败为 1。修改后的已保存数据哈希不匹配时拒绝继续比较。

## sdat 当前边界

已观察的 sdat 为 Cluster XML 元数据 + 九列文本数值。结构检查可以保存 `sdat_structure.json` 和 `sdat_uninterpreted_columns.csv`，列名仅为 column_1…column_9。

材料批次入口仍不为 sdat 计算 RL/EAB，含 sdat 时会显示该成员不适用并提供结构诊断。v0.5 根据用户提供的候选映射增加了独立 `run_sparameters.py`，可显式计算候选 S 参数与 R/T/A，见 `docs/sparameters.md`。厂商 S21/S12 顺序仍待确认，D 的物理意义仍不推断。

## 验收示例

```powershell
.\.venv\Scripts\python.exe run_batch.py --manifest sample_data/batch_example.json
```

此清单使用两个明确标注 SYNTHETIC 的人工样品，仅验证软件比较流程，不用于材料机理或性能结论。
