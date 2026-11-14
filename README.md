# 综合材料表征分析平台

开发者接手、架构、发布流程和后续路线见 [项目交接文档](docs/PROJECT_HANDOFF.md)。

当前为 v0.23.0（Phase D 完成）。v0.13.0 建立了以样品为中心的本地工作区；v0.14.0 接入电磁分析；v0.15.0 增加 schema v1 与 S 参数运行；v0.16.0 新增 VSM；v0.17.0 支持 Lake Shore `.dat`；v0.18.0 新增 XRD 峰分析；v0.19.0 支持真实 Bruker RAW4；v0.20.0 直接解析二进制 RAW4；v0.21.0 增加 Pseudo-Voigt 拟合与仪器展宽；v0.22.0 增加 d 间距参考卡片与多相筛查；v0.23.0 按数据类型重组导航，并为电磁/VSM/XRD/S 参数分别提供单样品、多样品比较和批量分析。原始文件不会被复制、移动或修改。使用说明见 [类型工作区](docs/type_workspaces.md)、[XRD 峰分析](docs/xrd.md)、[VSM 磁滞回线](docs/vsm.md) 与 [项目与样品工作区](docs/workspace.md)。

产品已覆盖 PRD 的电磁、VSM、XRD 三个表征阶段，并把 S 参数作为独立实测类型；Rietveld 精修、任意厂商专有二进制格式和外部物相数据库仍不在当前范围。

新增 [图片配套 Origin 数据](docs/origin_data.md)：图片内容不变，每张输出图片旁额外保存独立 CSV 数据与坐标说明。

新增 [自动多厚度 RL 曲线](docs/multi_thickness_rl.md)：单样品分析后，从图类型列表选择“多厚度 RL 曲线（自动）”，无需逐个输入厚度。新增 [实测 S 参数屏蔽效能/Smith 图与单样品报告](docs/report.md)。

现有电磁科学核心保持不变：分析缓存加入引擎版本，算法或解析语义升级后旧结果自动重算；Excel 列映射预览与正式解析使用相同工作表和表头行。默认“日常模式”，自动从同目录 S 参数夹具读取厚度 D；见 [界面主题](docs/ui_theme.md) 与 [日常流程](docs/daily_workflow.md)。CLI 与 GUI 共用分析服务，摘要、累计覆盖、验证状态和 `thickness_summary.csv` 由同一段代码生成；真实数据虚部定义与商业软件对照仍待外部验证。

无需 Python 的客户端：`output/releases/MaterialsCharacterizationPlatform-Setup-0.23.0-win64.exe`，见 [客户端使用说明](docs/client_usage.md)。发布构建来自干净提交；具体提交见安装目录 `_internal/build_info.json`。

启动桌面界面：`.\.venv\Scripts\python.exe run_gui.py`。新环境安装 `requirements-gui.txt`。具体步骤和阶段边界见 [GUI 使用说明](docs/gui_usage.md)。

## 安装与运行

使用 Python 3.11 或以上版本，在项目目录运行：

```powershell
python -m venv .venv
# 精确复现当前验证环境（推荐）；或使用 requirements.txt 的宽范围
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run_analysis.py "你的文件.memp" --imaginary-convention loss
```

开发环境可安装 `requirements-dev.txt`（锁定依赖 + ruff）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
```

CI 在 GitHub Actions 的 Windows 上对 Python 3.11/3.12 执行 ruff、编译与全量测试（离屏 Qt）。当前开发环境已在 `.venv` 配置，可直接运行最后两条命令。`loss` 在真实文件定义未确认时仅是显式假设，默认结果标注待验证。只有获得外部定义后才添加 `--convention-confirmed`；该开关不代表完成商业软件对照。

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

每次输出到 `output/sample_样品名/时间_唯一编号/`。包含解析数据、频率裁选后数据、RL 矩阵、厚度统计、指定厚度曲线、PNG 图和 JSON/TXT 分析记录。原始文件只读，分析记录包含源 SHA-256、解析映射、单位、符号转换、实际扫描网格、软件与分析缓存版本、Git 状态、依赖版本、警告、结果哈希及成功/失败状态。

图默认 600 dpi，使用 `--dpi`、`--width`、`--height`、`--linewidth`、`--cmap` 调整。二维等高图的颜色为离散等高带；三维颜色为每个面的四角 RL 均值，禁用光照和降采样，共享归一化范围。精确零反射保留 `-inf`，当前不自动裁剪其绘图范围。

真实 `.memp` 文件虚部定义和商业软件对照尚未确认，界面与记录保持待验证，图片不添加 PENDING 标题。原始真实数据不提交 Git。

## Phase 2：阻抗与损耗辅助分析

沿用原命令会自动生成 Phase 2 数据与图。可以选择四分之一波长阶数与阻抗模长显示范围：

```powershell
.\.venv\Scripts\python.exe run_analysis.py "你的文件.memp" --imaginary-convention loss --quarter-wave-orders 1 3 5 --impedance-tolerance 0.1
```

默认 n=1，阶数必须为正奇数且不重复；容差 0.1 表示标出 |z|=0.9、1、1.1 等高线。这是显示范围，不是自动判定“匹配良好”的物理阈值。[COMMON] |z|=1 仍可能反射很强，完整匹配要求 z≈1+j0。输出保留实部、虚部、模长，以及全部网格最佳 RL 点对应的 z。

[COMMON] 使用以下公式（ε″/μ″指内部损耗系数）：

```text
tanδε = ε″ / ε′                           无量纲
tanδμ = μ″ / μ′                           无量纲
A = μ″ε″ - μ′ε′
B = μ′ε″ + μ″ε′
α = sqrt(2) π f/c * sqrt(A + hypot(A,B))    m^-1，f 为 Hz
C0 = μ″ / (μ′² f)                         s，f 为 Hz
tm = n c / [4 f sqrt(|εr||μr|)]             m，展示/导出为 mm
```

[COMMON] α 公式在低损耗区采用等价写法避免相消；此常用非负表达式不能独立证明材料被动性。C0 只能作为辅助证据，不能单独证明涡流机制。Cole-Cole 图只绘制 ε″ vs ε′，不自动计数弛豫、不判断界面极化。tm 是模型估算，与每个厚度的网格 RLmin 位置对照，不要求二者一致。

新增输出：

- `loss_parameters.csv`：原有五列及 tanδ、α、C0、各阶理论厚度。
- `impedance_abs_matrix.csv`、`impedance_real_matrix.csv`、`impedance_imag_matrix.csv`：行厚度 mm、列频率 GHz，阻抗均归一化无量纲。
- `impedance_curve.csv`：指定厚度的复阻抗与模长。
- `quarter_wave_comparison.csv`：逐厚度所有并列 RLmin 的频率、理论厚度及差值。
- `mechanism_notes.txt`：解释边界；摘要和运行记录同样保存这些说明。
- `figures/`：阻抗二维/曲线、RL 与阻抗并排、损耗角、衰减、Cole-Cole、C0、四分之一波长与 RL 叠加图。

派生量分母为零或溢出时保存空值并列出频率，图中断线，不修改原始参数，也不偷偷补值。正实部接近零的警告仍保留。多样品选择与比较入口见 `run_batch.py` 和 `docs/batch_usage.md`。

## 模块阅读顺序

`core/units.py` → `core/parser.py` / `validation.py` → `electromagnetic.py` → `rl_calculator.py` → `eab.py` → `plotting/` → `run_analysis.py`。函数用中文说明输入、输出和物理意义。命令行入口只组织流程，核心计算不依赖界面。

## 当前验收范围

原有 75 项自动测试保持通过，S 参数新增 31 项；当前全量测试为 431 项，覆盖 Phase 1–2、共享分析管线、批次失败隔离、不同网格比较、清单覆盖、并列汇总、Excel 数值类型与表头行、候选 sdat 映射、UTF-8 编码、`-inf` 极限交点、图片溯源、GUI 交互回归、工作区 schema 迁移、电磁/S 参数登记，以及 VSM 单位、磁滞指标、背景扣除、Lake Shore DAT、XRD 峰检测、RAW4 文本/二进制、Pseudo-Voigt 拟合、仪器展宽、d 间距参考卡片、多相组合、类型化导航与批量、背景、参考匹配、报告与工作区闭环。测试通过不代表已确认厂商格式或商业软件一致性。

桌面 GUI 自 v0.6.0 起持续提供；单样品完整 Excel 报告与自动插值仍不在当前范围。ε′/μ′ 不存在跨材料通用的“明显异常”上限；当前报告负值、近零值与非有限值，不把未经校准的数值阈值伪装成物理判据。

## Phase 3 批量入口

```powershell
.\.venv\Scripts\python.exe run_batch.py --directory Raw_Data --imaginary-convention loss
.\.venv\Scripts\python.exe run_batch.py --manifest sample_data/batch_example.json
```

第二条使用明确标注为合成数据的两个样品。公共扫描/频率/阈值设置、逐样品列映射与命名、选择比较样品、输出说明及失败处理见 `docs/batch_usage.md`。各样品的曲线厚度可不同（`.memp` 取同目录夹具 D），比较记录保存 `curve_thickness_mm_per_sample`。含未映射 sdat 的批次会如实标为部分失败，不能视为所有格式都已成功解析。

## 候选 S 参数入口

```powershell
.\.venv\Scripts\python.exe run_sparameters.py "你的文件.sdat" --name CIP_SiO2
```

配置见 `config/sparameter_candidate.json`，详细说明见 `docs/sparameters.md`。状态始终为 `candidate_high_confidence`，不是 manufacturer-confirmed。输出真实复数组、幅度/dB/相位、R/T/A 及逐点筛查标记，不插值、不裁剪负 A。此入口不修改 `.memp` 稳定计算逻辑；材料批量入口不把 S 参数冒充 ε/μ。
