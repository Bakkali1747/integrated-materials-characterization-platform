# 候选 sdat S 参数模块

## 使用入口与状态

```powershell
.\.venv\Scripts\python.exe run_sparameters.py "你的文件.sdat" --name CIP_SiO2
```

默认使用 `config/sparameter_candidate.json`。配置层为 `SParameterMapping`，支持 `--schema 自定义.json`；计算函数只消费命名复数组，不知道文件列索引。

`schema_status = "candidate_high_confidence"` 表示用户提供、有物理一致性证据的候选映射，绝非 manufacturer-confirmed。S21 与 S12 的厂商顺序仍未确认。图、逐点 CSV、复数 NPZ 和运行记录都保留状态；一致性检查通过不会自动提升状态。

此入口与 `.memp`、材料 RL 及现有批量流程分开。S 参数不能代替 ε/μ 输入，也不自动生成材料 RLmin/EAB。材料批次入口仍不把 `.sdat` 纳入 RL/EAB 汇总。

## parser 逻辑

1. 只读字节并保存 SHA-256；无 BOM 优先 GB18030，随后 GBK/UTF-8，严格解码不替换乱码。可用 `--encoding` 显式指定；UTF-8 BOM 为明确编码标识。
2. 分离完整 Cluster XML header 与后续 tab-separated 区。保存原始解码 XML 及层级对象，不解释 L/A/B/D 的物理意义或单位。
3. 数值区严格要求九列；缺失、非数值、NaN、无穷值、内部空行、重复或倒序频率均拒绝。保存源行号。
4. 从 schema 读取 0-based 列索引与频率单位，统一 GHz。默认候选文件约束为 201 点、2–18 GHz、步长 0.08 GHz；不匹配时报错。其他已知数据集可显式修改配置，或将非必要网格约束设为 null。
5. 按 schema 构造 `S = real + j*imag`，不套用 `.memp` 损耗系数的负号规则，不插值、不改频率网格。

| 参数 | 实部列 | 虚部列 |
| --- | --- | --- |
| S11 | 1 | 2 |
| S21 | 3 | 4 |
| S12 | 5 | 6 |
| S22 | 7 | 8 |

频率为第 0 列。自定义配置必须明确给出 schema_status 和全部四组映射，列索引不能重用。当前允许 candidate_high_confidence 或 unverified，不接受厂商确认状态。

## 数值与一致性检查

[COMMON] 幅度为 |S|，dB=20log10|S|，phase_deg 是不展开的主值相位（−180° 至 +180°）。零幅度 dB 保留 −inf，物理相位未定义，保存为空值并提示。

[COMMON] 在相容功率波/端口归一化假设下：R=|S11|²、T=|S21|²、A=1−R−T。这些都是无量纲比例；归一化未外部确认时保留该限制。任何负 A 都警告，包括容差内轻微负值，绝不 clip。

筛查条件与默认容差：

- |Sij| ≤ 1 + magnitude_atol，默认 1e-6。
- R+T ≤ 1 + energy_atol，默认 1e-6。
- |S21−S12| ≤ reciprocity_atol + reciprocity_rtol × max(|S21|,|S12|)，默认 atol=0.02、rtol=0.02。

这些容差是可调整的筛查设置，不是厂商判据。用 `--magnitude-atol`、`--energy-atol`、`--reciprocity-atol`、`--reciprocity-rtol` 修改，运行记录保存实际值。相关系数不足两点或序列为常数时返回 null，不伪造相关性。

[COMMON] 单个幅度上限与单端口 R+T 检查不是完整二端口被动性的充分证明；互易性接近也不能唯一确认 S21/S12 列顺序。程序只记录数值检查，不推断材料机理。

## 输出

每次独立保存在 `output/s_parameters/sample_样品名/时间_唯一编号/`：

- `sparameters_by_frequency.csv`：原频率、源行号、schema 状态、四组复数实虚部/字符串/幅度/dB/相位、R/T/A、逐点 QC 标记。
- `sparameters_complex.npz`：频率和真正的四组复数组，附 schema 标识与状态，可用 NumPy 加载。
- `raw_numeric_columns.csv`：未映射的九列数值，列名从 column_0 到 column_8。
- `metadata.xml`：header 的 UTF-8 解码副本，不改原文件。
- `quality_checks.json`：相关系数、复数差、幅度/能量/负 A 异常计数及容差。
- `analysis_record.json` / `.txt`：源哈希、配置、软件版本、Git 提交/工作区状态、结果哈希、候选状态及成功/失败记录。
- `figures/`：幅度、dB、相位、R/T/A，默认 600 dpi；可用 `--no-figures` 只导出数据。

Python 读取 pandas 表时，透射列必须使用 `table["T"]`；`table.T` 在 pandas 中表示转置。

## 回归验证

首行回归片段由用户明确提供。测试既检查近似幅度/dB，也检查从六位小数原始数值算出的 R=0.013771280125、T=0.943756982948、A=0.042471736927，未通过调整常数迎合结果。

新增 31 项参数化测试案例，原有 75 项保持不变，总计 106 项。真实完整文件另做独立运行检查，不把完整原始科研文件提交到 Git。
