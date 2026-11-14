# 综合材料表征分析平台项目交接文档

最后核对日期：2026-11-15  
当前版本：`v0.24.2`  
当前阶段：PRD Phase D 完成  
主仓库：<https://github.com/Bakkali1747/integrated-materials-characterization-platform>

## 1. 项目定位

本项目是面向个人科研使用的 Windows 本地桌面应用，目标是以真实样品为中心，统一管理电磁、VSM、XRD 等材料表征数据、分析运行和科研产物。

项目由原“微波吸收分析软件”演进而来。v0.13.0 新增项目/样品/测试/分析运行四类实体；v0.14.0 接入电磁分析；v0.15.0 增加 schema v1 与 S 参数；v0.16.0 新增 VSM；v0.17.0 支持 Lake Shore `.dat`；v0.18.0 完成 XRD 峰分析；v0.19.0 支持真实 Bruker RAW4 文本；v0.20.0 直接解析二进制 RAW4；v0.21.0 增加 Pseudo-Voigt 拟合与仪器展宽；v0.22.0 增加 d 间距参考卡片与多相筛查；v0.23.0 按数据类型重组导航并补齐四类比较/批量；v0.23.1 类型菜单默认折叠；v0.23.2 更换应用图标；v0.23.3 优化 XRD 交互图谱；v0.24.0 内置 COD 无机物相库自动匹配；v0.24.1 修复无库环境验证状态；v0.24.2 摘要顶部显示 COD 候选。

应用采用新的名称、安装目录、本地数据目录和安装器 AppId，可以和旧版微波吸收分析软件并存，不会覆盖旧应用。

## 2. 当前交付状态

- Git 默认分支：`main`
- v0.24.2 基线提交：`bdf0306`（安装目录 `_internal/build_info.json` 记录同一提交，`dirty=false`）
- 版本标签：`v0.24.2`
- Windows 安装程序：`output/releases/MaterialsCharacterizationPlatform-Setup-0.24.2-win64.exe`
- 安装程序 SHA-256：`e5f7b742997b1d1194d0803d4ee0642718e4b02a7de3107a3f3fe62b5a4c65f1`；同时见 `output/releases/SHA256SUMS-0.24.2.txt`
- 当前已验证测试：`437 passed`
- Ruff：通过
- 源码版和冻结安装版自检：通过（电磁、S 参数、VSM、XRD 四类工作区自动登记）
- 已验证产物：17 类电磁科研图、报告、S 参数、VSM 回线与报告、XRD 图谱与报告、比较、批量、历史和导出
- 真实数据：9 个 Lake Shore VSM DAT；2 组 Bruker RAW4 XRD（二进制直读与 TXT 计数逐点一致；主峰 Pseudo-Voigt 拟合收敛）

原仓库保留为历史远程 `legacy-origin`：

<https://github.com/Bakkali1747/microwave-absorption-analyzer>

后续开发和发布只能推送到新仓库 `origin`，不要把新版本推回 `legacy-origin`。

## 3. 已实现功能

### 3.0 类型化导航与比较/批量

- 左侧导航树按电磁性能、VSM、XRD、S 参数分组，每组包含单样品分析、多样品比较、批量分析；类型默认折叠，点击标题展开。
- 完整模式显示全部二级入口；日常模式只保留电磁/VSM/XRD 单样品与历史结果。
- 电磁比较/批量沿用原有原始文件流程；VSM/XRD/S 参数比较基于已完成运行目录，批量扫描原始文件。
- VSM 比较叠加归一化回滞线；XRD 比较叠加归一化图谱；S 参数比较叠加 S11/S21 dB。
- 批量逐文件独立输出，失败隔离；`batch_record.json` 与 `sources.csv` 记录状态。
- 详细操作见 `docs/type_workspaces.md`。

### 3.1 项目与样品工作区

当前数据层级为：

```text
Project
└── Sample
    ├── Measurement
    └── AnalysisRun
```

已实现：

- 创建和浏览科研项目。
- 创建样品，保存材料体系、批次、组成、制备条件、填料比例、标签和备注。
- 给样品关联 Electromagnetic、VSM、XRD 三类测试文件。
- 保存原始文件绝对路径和 SHA-256，不复制、不移动、不修改原始文件。
- 重新核验来源文件并区分 `PASS`、`CHANGED`、`MISSING`。
- 以追加方式保存 AnalysisRun，避免新分析覆盖历史运行。
- 使用统一科研状态：`VALIDATED`、`PENDING`、`WARNING`、`NOT COMPUTABLE`、`UNSUPPORTED`、`FAILED`。
- v0.14.0 起可从 Electromagnetic Measurement 发起 ε/μ 分析；v0.15.0 增加实测 S 参数分析；成功后自动追加 AnalysisRun。
- AnalysisRun 保存结果目录、数值产物、图片与显式导出文件的绝对路径引用；同一测试重跑不覆盖历史。
- 开始分析与登记运行前两次核验源文件 SHA-256；不一致时拒绝执行或拒绝登记。
- 样品详情可查看该测试的全部历史运行、打开结果目录，或只读载入已保存结果（不重新计算）。
- 分析结论只映射为 `PENDING` 或 `WARNING`，绝不自动生成 `VALIDATED`。
- v0.15.0 新增工作区 schema v1：旧工作区只读校验后迁移，未来版本或损坏文件拒绝打开且不改写。

工作区使用 UTF-8 JSON 文件，不依赖数据库。所有 JSON 写入使用临时文件原子替换。

### 3.2 电磁与微波吸收分析

- 导入 CSV、XLS、XLSX、MEMP。
- 配置工作表、表头行、列映射、频率单位和虚部约定。
- 计算复介电常数、复磁导率、归一化输入阻抗和反射损耗 RL。
- 执行厚度—频率二维扫描。
- 计算固定厚度 EAB、指定阈值带宽和累计频段覆盖。
- 保存最小 RL、全部并列极小值和全部连续达标频段。
- 输出阻抗、损耗角、衰减常数、Cole-Cole、C0 和四分之一波长辅助分析。
- 自动生成多厚度 RL 曲线。
- 每张图片同时生成可供 Origin 使用的独立数据目录。
- GUI 与 CLI 共用 `core/analysis_service.py`，界面层不复制科学公式。

### 3.3 VSM

- 读取 `.csv`、`.xlsx`、`.xls`、`.txt`，以及 Lake Shore 风格 `.dat`。
- DAT 自动识别 `Field(...)` / `Moment(...)` 表头，读取文件头 `Mass(g)`（默认用于质量归一化）与 `Unit=CGS`；`Unit=SI` 明确拒绝。
- 支持 Oe、A/m、kA/m、T、mT 与 emu、A·m²；质量归一化仅在提供质量（用户或 DAT 文件头）时执行。
- 计算 Hc（含 Hc+/Hc−、Oe 与 A/m）、Mr、Ms、方形比、回线闭合差；Hc/Mr 用相邻点线性插值，Ms 明确不是真实饱和。
- 可选高场线性背景扣除：正负高场分别拟合后取平均斜率/截距，记录 R²、系数与点数；默认关闭。
- 缺失/非数值/非有限值直接报错；保留扫描顺序，不排序、不去重、不插值、不裁剪。
- 输出 `parsed_data.csv`、`vsm_metrics.json/csv`、`analysis_record.json/txt`、磁滞回线与原点放大图、可选背景图，以及 DOCX/PDF 报告。
- 可从 VSM Measurement 发起分析并自动登记 `vsm_hysteresis` AnalysisRun；不可计算时登记为 `NOT_COMPUTABLE`。

### 3.4 XRD

- 读取 `.csv`、`.txt`、`.xy`、`.dat` 文本，以及 Bruker RAW4 文本（`;RAW4.00`）和二进制 `.raw`（直接解析；失败时才回退同名 `.txt`）。
- 二进制 RAW4 定位头部几何签名与文件尾部 float32 计数，校验点数、2θ 范围、有限非负计数与整数计数比例；记录几何头/数据偏移。
- 有表头按列名，无表头只接受两列（2θ，强度）；2θ 严格递增；缺失/非数值/非有限值报错。
- RAW4 从 `[RangeHeader]` 读取起始 2θ、步长、声明点数，从 `[Data]` 读取 `Angle, PSD`；从文件头读取波长（A/B 为 1.5418 Å）。
- 峰检测：可选移动平均平滑（默认 5 点，只用于检测与初始 FWHM）+ 地形突出度（默认 5%）+ 最小峰间距；峰位取扫描网格点。
- 可选单峰 Pseudo-Voigt 拟合（局部线性基线）：R² ≥ 0.8 时采用拟合峰位/FWHM/η，否则保留半高插值并标记；结果保存拟合状态、R²、η 与校正尺寸。
- 计算 FWHM、d 间距、Scherrer 表观尺寸与相对强度；可选仪器展宽校正（常数 FWHM 或 2θ–FWHM CSV，Gaussian 平方差），启用后同时保留表观与校正尺寸。
- 可选左右高角度窗口线性背景扣除，默认关闭。
- 可选参考峰列表匹配：支持 2θ 或 d 间距卡片、phase/formula/card 元数据；按 phase 独立匹配后，再按实测峰覆盖度对最多 3 相组合排序；明确不是物相鉴定或定量相分析。
- 默认自动匹配 COD 无机物相库（88,311 相，CC-BY-4.0）；返回前 10 个候选并写入 `phase_library_matching.json`。COD 是开放计算图谱，不是 ICDD PDF 商业卡片；同构相可能并列。
- 输出 `parsed_data.csv`、`xrd_peaks.csv/json`、`phase_matching.json`、图谱/参考相棒图与 DOCX/PDF 报告。
- 可从 XRD Measurement 发起分析并自动登记 `xrd_peaks` AnalysisRun；未检测到峰时登记为 `NOT_COMPUTABLE`。

### 3.5 S 参数

- 解析 S11、S21、S12、S22 的复数、幅度、dB 和相位。
- 计算 R、T、A 和 SE_R、SE_A、SE_T。
- 绘制 S 参数曲线、屏蔽效能图和 Smith 圆图。
- 记录源文件哈希、逐点质量检查和分析状态。
- 支持独立 CLI、GUI 和批量入口。
- v0.15.0 起可从 Electromagnetic Measurement 的 `.sdat` 发起 S 参数分析，完成后登记 `s_parameters` AnalysisRun；QC 警告合并进运行记录。

当前 S 参数字段映射仍是 `candidate_high_confidence`，不是厂商正式确认格式；尚未实现 NRW 反演。

### 3.6 批量、比较、历史与导出

- 单样品、多样品比较和混合批量处理。
- 逐来源故障隔离和协作取消。
- 不同频率网格、不同样品厚度比较。
- 匹配源文件哈希和数值配置时复用已有分析。
- 浏览、筛选和核验历史运行产物。
- 归档旧运行和检查重复结果。
- 导出 PNG、TIFF、PDF、SVG、CSV、Excel。
- 生成 DOCX/PDF 中文单样品报告。
- 导出移除本地绝对路径的可分享运行记录。
- 记录版本、Git 提交、依赖、输入哈希、参数、警告、结果哈希和验证状态。

## 4. 尚未完成的需求

### 4.1 Phase B 已完成，后续增强

v0.14.0 打通了 Measurement → 电磁分析 → AnalysisRun → 结果引用 → 历史查看的闭环；v0.15.0 补上 schema v1 迁移与实测 S 参数运行挂载。以下属于后续增强，不阻塞 Phase C：

- 单样品报告和历史页导出尚未自动追加到 AnalysisRun 的 `export_refs`；从电磁或 S 参数页面保存图片会登记。
- 工作区备份/恢复、项目导入/导出和多用户并发写入尚未实现。
- 运行表暂不支持按状态筛选或删除；AnalysisRun 保持追加语义。

### 4.2 Phase C 已完成，后续 VSM 增强

v0.16.0 已实现 VSM 基础闭环：解析、单位、质量归一化、磁滞指标、可选线性背景、绘图、导出、报告与工作区登记。以下属于后续增强，不阻塞 Phase D：

- 暂不支持 Minor loop、FORC、温度/角度序列和多段扫描的自动分离。
- 背景模型只有关闭与高场线性两种；不提供用户背景文件或多项式模型。
- 尚未自动判定“真实饱和”，Ms 只是当前最大场端值。
- 尚未实现逐点 QC 表格或 VSM 运行历史筛选。

### 4.3 Phase D 已完成，后续 XRD 增强

v0.18.0 已实现 XRD 基础闭环：文本解析、峰检测、FWHM、d 间距、Scherrer 表观尺寸、可选线性背景、参考峰匹配、绘图、导出、报告与工作区登记。以下属于后续增强：

- 不支持除 Bruker RAW4 以外的厂商专有二进制格式；RAW4 直读基于已观察结构，其他版本可能回退同名 TXT 或拒绝。
- 不支持 Rietveld/全谱拟合、Kα2 剥离、仪器展宽校正、织构或应力分析。
- 参考相匹配只使用用户提供的峰列表；未内置 PDF 数据库。
- 尚未实现峰形拟合（Gaussian/Lorentzian/Pseudo-Voigt）与自动背景模型选择。


## 5. 技术栈

| 分类 | 技术 |
| --- | --- |
| 语言 | Python 3.11+ |
| 桌面 GUI | PySide6 |
| 数值计算 | NumPy |
| 表格处理 | pandas |
| 科学绘图 | Matplotlib |
| Excel | openpyxl、xlrd |
| Word 报告 | python-docx |
| PDF 报告 | ReportLab |
| 本地持久化 | UTF-8 JSON |
| 测试 | pytest、pytest-qt |
| 代码检查 | Ruff |
| EXE 打包 | PyInstaller |
| Windows 安装器 | Inno Setup |
| CI | GitHub Actions，Windows，Python 3.11/3.12 |

精确依赖版本见 `requirements-lock.txt`。

## 6. 目录结构

```text
core/
├── common/                 Project、Sample、Measurement、AnalysisRun、schema 与分析运行登记
├── analysis_service.py     GUI/CLI 共用电磁分析服务
├── vsm.py                  VSM 解析、单位、磁滞指标与背景扣除
├── vsm_service.py          VSM 运行、记录与产物
├── xrd.py                  XRD 解析、峰检测、Scherrer 与参考匹配
├── xrd_service.py          XRD 运行、记录与产物
├── parser.py               CSV/Excel/MEMP 解析
├── validation.py           数据质量检查
├── electromagnetic.py      复电磁参数构造
├── rl_calculator.py        输入阻抗与 RL
├── eab.py                  有效吸收带宽
├── mechanism.py            损耗机理辅助量
├── impedance.py            复阻抗
├── batch.py                批量处理
└── sparameter_*.py         S 参数映射、解析和计算

gui/
├── main_window.py          主窗口、导航和任务互斥
├── pages/                  工作区、单样品、VSM、S参数、比较、批量、历史、设置
├── controllers/            GUI 与核心服务的控制层
├── workers/                QThread 后台任务
└── widgets/                公共控件

plotting/                   科学绘图（含 vsm_plot.py）
export/                     数据、报告、追溯和分享导出（含 vsm_report.py）
packaging/                  PyInstaller 和 Inno Setup 配置
tests/                      自动测试
docs/                       架构、使用和科学约定文档
sample_data/                合成验收数据
run_*.py                    GUI 和 CLI 入口（含 run_vsm.py、run_xrd.py）
```

推荐阅读顺序：

1. `README.md`
2. `docs/architecture.md`
3. `docs/workspace.md`
4. `docs/vsm.md`
5. `docs/xrd.md`
6. `core/common/workspace.py`
7. `core/common/workspace_schema.py`
8. `core/common/analysis_link.py`
9. `core/analysis_service.py`
10. `core/vsm.py` / `core/vsm_service.py`
11. `core/xrd.py` / `core/xrd_service.py`
12. `gui/pages/workspace_page.py`
13. `gui/pages/vsm_page.py`
14. `gui/pages/xrd_page.py`
15. `VERSIONING.md`

## 7. 开发与测试

创建环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

常用命令：

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run_gui.py
```

使用合成数据运行 CLI：

```powershell
.\.venv\Scripts\python.exe run_analysis.py sample_data\synthetic_constant.csv --imaginary-convention loss --convention-confirmed
```

## 8. Windows 构建与安装

发布构建使用独立环境 `output/package-env`：

```powershell
.\output\package-env\Scripts\python.exe packaging\build_client.py
```

构建脚本默认拒绝 dirty 工作区。正式构建必须来自已提交的干净状态，并把版本、Git 提交和 dirty 状态写入 `output/packaging/build_info.json`。

主要输出：

```text
output/dist/IntegratedMaterialsCharacterizationPlatform/
output/releases/MaterialsCharacterizationPlatform-Setup-<版本>-win64.exe
```

安装目录：

```text
%LOCALAPPDATA%\Programs\IntegratedMaterialsCharacterizationPlatform
```

用户数据：

```text
%LOCALAPPDATA%\IntegratedMaterialsCharacterizationPlatform\
├── workspace\
├── output\
├── logs\app.log
└── settings\gui.json
```

卸载应用不会删除上述科研数据和日志。

## 9. 科学边界与禁止事项

以下约束必须长期保留：

- 真实 MEMP 文件的虚部定义尚未通过厂商资料或商业软件对照确认，状态保持 `PENDING`。
- SDAT 映射不是厂商正式确认格式。
- 缺失数据插值始终关闭。
- 不得静默排序、删除、补值或裁剪异常数据。
- 负参数只警告并保留，不能简单取绝对值。
- 固定厚度 EAB 与跨厚度累计覆盖不得混为一谈。
- 测试通过不代表完成真实仪器格式或物理结果的外部验证。
- 不得因为文件成功导入就自动提升科研验证状态。
- VSM 的 Ms 只是当前最大场端值，不宣称真实饱和；Hc/Mr 为离散点线性插值。
- VSM 背景扣除默认关闭；启用时必须记录拟合窗口、系数与 R²，不得隐式扣除。
- VSM 的质量归一化只在显式提供质量时执行，不得使用默认质量。
- XRD 峰位取扫描网格点；Pseudo-Voigt 拟合仅在 R²≥0.8 时采用，否则保留半高插值；不得声称完成全谱拟合或 Rietveld。
- XRD 峰检测平滑只用于检测与初始 FWHM，原始强度与导出数据不得被平滑。
- XRD 的 Scherrer 尺寸默认是表观尺寸；仪器展宽校正只在用户提供常数/曲线时启用，并采用 Gaussian 平方差假设。
- 参考匹配与多相组合只是筛查，不是物相鉴定或定量相分析；不得据此宣称样品只含这些相。
- Bruker 二进制 RAW 通过已观察到的 RAW4 几何签名与尾部计数直读；TXT 回退仅用于直读失败，不能保证覆盖所有厂商版本。
- 原始科研文件不提交 Git。

## 10. 当前技术债和风险

- 工作区 schema v1 已有迁移框架，但还没有 v1→v2 的实际结构迁移；新增字段时必须登记迁移并递增版本。
- 工作区尚无多人并发写入控制；AnalysisRun 只追加，导出引用为原地追加。
- 尚无工作区备份、恢复和项目导入/导出界面。
- 单样品报告和历史页导出尚未自动登记到 AnalysisRun。
- VSM/XRD/S 参数比较目前以已完成运行目录为输入，未提供“直接添加原始文件并自动分析后比较”的一步式入口。
- S 参数专用 DOCX/PDF 报告尚未实现；历史页对 S 参数记录只提供记录/图片/核验。
- VSM 的 Lake Shore DAT 支持基于本项目真实文件观察结构；其他厂商/二进制 `.dat` 不解析。Minor loop、FORC、温度/角度序列和用户背景文件尚未实现。
- XRD 仅支持显式文本格式（CSV/TXT/XY/DAT）与已观察结构的 Bruker RAW4；RAW4 直读依赖几何签名与尾部 float32 计数，其他版本或布局会拒绝/回退 TXT。峰形拟合为单峰 Pseudo-Voigt，仪器展宽校正为常数/CSV 的 Gaussian 平方差；不支持 Rietveld、Kα2 剥离与内置 PDF 数据库。
- README 的部分历史章节仍保留旧测试数量或旧阶段描述，需要后续统一清理。
- Windows 安装程序没有商业代码签名，可能显示“未知发布者”。
- 冻结版已在当前开发机验收，但仍需在另一台干净 Windows 电脑验证兼容性。
- v0.14.0 起安装包与 SHA-256 作为 GitHub Release 附件发布；更早版本仍只有源码和标签。
- GitHub Release：<https://github.com/Bakkali1747/integrated-materials-characterization-platform/releases/tag/v0.24.2>

## 11. 版本与发布工作流

每次完成仓库更新后：

1. 只提交本次相关改动，保留并排除用户的无关改动。
2. 在适当时更新版本，并同步检查 `pyproject.toml`、`core/__init__.py`、`packaging/client.iss`、CHANGELOG 和版本测试。
3. 运行 Ruff、编译检查和全量测试。
4. 从干净提交构建 Windows 安装程序。
5. 安装或刷新当前用户版本。
6. 验证安装版本、正常入口和冻结版自检。
7. 推送当前分支到 GitHub `origin`。
8. 正式版本创建并推送对应标签。
9. 发布版本时创建 GitHub Release，上传安装包及 SHA-256。

## 12. 建议的接手步骤

1. 克隆新仓库并确认 `origin` 指向新项目。
2. 安装锁定依赖，运行 Ruff 和全量测试。
3. 启动 GUI，体验工作区“测试 → 电磁 / S 参数 / VSM / XRD 分析 → AnalysisRun → 载入结果”闭环。
4. 阅读 PRD、架构文档、`docs/vsm.md`、`docs/xrd.md` 和本交接文档。
5. 如需继续 XRD：峰形拟合、仪器展宽校正、Kα2 剥离、PDF 数据库匹配与 Rietveld 精修。

