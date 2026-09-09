# 本地微波吸收分析软件

当前为 Phase 1 / v0.2：CSV/Excel、已观察格式的 `.memp`、ε/μ 绘图、单层金属背板 RL、EAB、二维/三维图和可追溯运行记录。GUI 在 Phase 4；未知 `.sdat` 尚不解析。

## 安装与运行

使用 Python 3.11 或以上版本，在项目目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run_analysis.py "你的文件.memp" --imaginary-convention loss
```

本次开发环境已在 `.venv` 配置，可直接运行最后两条命令。`loss` 在真实文件定义未确认时仅是显式假设，默认结果标注待验证。只有获得外部定义后才添加 `--convention-confirmed`；该开关不代表完成商业软件对照。

使用合成样品试运行：

```powershell
.\.venv\Scripts\python.exe run_analysis.py sample_data/synthetic_constant.csv --imaginary-convention loss --convention-confirmed
```

如果终端中文乱码，可先执行 `$env:PYTHONIOENCODING='utf-8'`。结果文件始终按 UTF-8 保存。

```powershell
.\.venv\Scripts\python.exe run_analysis.py "data.csv" --imaginary-convention loss --thickness-min 1 --thickness-max 5 --thickness-step 0.01 --curve-thickness 2 --frequency-min 2 --frequency-max 18
```

标准 CSV/Excel 列为 `frequency_ghz, eps_real, eps_imag, mu_real, mu_imag`。非标准列通过 `--column-map mapping.json` 显式映射，例如 `{"frequency_ghz":"Frequency", "eps_real":"e1", "eps_imag":"e2", "mu_real":"m1", "mu_imag":"m2"}`，并指定 `--frequency-unit Hz` 等单位。Excel 用 `--sheet 工作表名` 选择工作表。CSV 默认逗号分隔，可指定 `--delimiter` 与 `--encoding`。

## 科学约定

[COMMON] 时间因子 `exp(+jωt)`，εr=ε′−jε″、μr=μ′−jμ″。内部虚部字段保存损耗系数，`loss` 直接保留，`signed` 将文件带符号虚部取负一次。负数不取绝对值、不裁剪。ε/μ 为相对量，无量纲。

[COMMON] 模型为法向入射、均匀单层材料、理想金属背板。f 由 GHz 转为 Hz，d 由 mm 转为 m，c=299792458 m/s，Z0≈376.730313668 Ω。

```text
n = sqrt(μr εr)
z = Zin/Z0 = (μr/n) tanh[j (2πfd/c) n]
RL = 20 log10 |(z-1)/(z+1)|
```

[COMMON] 用 `μr/n` 保持阻抗与传播根一致；普通正参数区与 sqrt(μr/εr) 形式一致。零参数附近通过 tanh(x)/x 级数求有限极限。计算数组 shape 为 `(厚度点数, 频率点数)`。结果极小值仅针对当前扫描网格，不宣称连续域最优。

## EAB 与插值

[COMMON] EAB 始终是固定厚度下 RL≤−10 dB 的最大连续频段宽度；分离的 4–6 GHz 与 10–13 GHz 给出 EAB=3 GHz，而不是 5 GHz。程序保存全部连续区间、并列最宽区间以及测量边界标记。

`--eab-crossing linear` 为默认：对相邻有效 RL 点之间的阈值交点作线性估计。`--eab-crossing sample` 仅使用达标采样点首尾。两者均不补缺失数据；缺失数据插值在本阶段始终 OFF。孤立阈值触点宽度为 0。并列带宽判断的浮点容差为 1e-12 GHz，仅用于判断并列，不改变阈值条件。

`--threshold -15` 等自定义阈值生成独立的指定阈值最大连续带宽，同时仍保存标准 −10 dB EAB。跨扫描厚度频段并集叫 Cumulative Frequency Coverage，绝不当作固定厚度 EAB。最大 EAB 延伸到测量边界时，只能报告当前频率范围内的带宽。

`summary.json` 保存全局 RLmin、标准 EAB、所选阈值带宽、各厚度的全部区间与累计覆盖。`thickness_summary.csv` 每行一个厚度，包含 RLmin、所有并列极小值频率、标准 EAB 和阈值带宽。`analysis_record.txt` 提供简明字段及完整记录。

## 质量控制与输出

读取时检查缺失、非数值、NaN、无限值、非正/重复/非递增频率；出现这些错误即停止，不静默排序、删除或补值。负参数只警告并保留，不能仅凭符号判断机理。文件结构一致不等于物理测量有效；CSV/Excel 没有声明点数时不能证明未被截断。

每次输出到 `output/sample_样品名/时间_唯一编号/`。包含解析数据、频率裁选后数据、RL 矩阵、厚度统计、指定厚度曲线、PNG 图和 JSON/TXT 分析记录。原始文件只读，分析记录包含源 SHA-256、解析映射、单位、符号转换、实际扫描网格、版本、Git 状态、依赖版本、警告、结果哈希及成功/失败状态。

图默认 600 dpi，使用 `--dpi`、`--width`、`--height`、`--linewidth`、`--cmap` 调整。二维等高图的颜色为离散等高带；三维颜色为每个面的四角 RL 均值，禁用光照和降采样，共享归一化范围。精确零反射保留 `-inf`，当前不自动裁剪其绘图范围。

真实 `.memp` 文件虚部定义和商业软件对照尚未确认，结果和图均标为待验证。原始真实数据不提交 Git。

## 模块阅读顺序

`core/units.py` → `core/parser.py` / `validation.py` → `electromagnetic.py` → `rl_calculator.py` → `eab.py` → `plotting/` → `run_analysis.py`。函数用中文说明输入、输出和物理意义。命令行入口只组织流程，核心计算不依赖界面。

## 当前验收范围

50 项自动测试覆盖解析、符号、单位、可解析 RL、极小值、EAB 连续区间、颜色映射、失败记录和重复运行隔离。真实文件已在临时 loss 假设下完成 201×401 网格运行及 600 dpi 图像检查。测试通过不代表已验证商业软件一致性。

本阶段没有 GUI、批量分析、完整 Excel 报告、自动插值或 Phase 2 损耗机理图。ε′/μ′ 不存在跨材料通用的“明显异常”上限；当前报告负值、近零值与非有限值，不把未经校准的数值阈值伪装成物理判据。
