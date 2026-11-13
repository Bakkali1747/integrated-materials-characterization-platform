# 综合材料表征分析平台项目交接文档

最后核对日期：2026-11-13  
当前版本：`v0.14.0`  
当前阶段：PRD Phase B  
主仓库：<https://github.com/Bakkali1747/integrated-materials-characterization-platform>

## 1. 项目定位

本项目是面向个人科研使用的 Windows 本地桌面应用，目标是以真实样品为中心，统一管理电磁、VSM、XRD 等材料表征数据、分析运行和科研产物。

项目由原“微波吸收分析软件”演进而来。v0.13.0 在完整保留原有电磁分析能力的基础上，新增项目、样品、测试和分析运行四类平台实体。v0.14.0（Phase B）把现有电磁分析接入该工作区：从 Electromagnetic 测试发起分析，完成后追加 AnalysisRun，并登记结果、图片与导出文件引用。

应用采用新的名称、安装目录、本地数据目录和安装器 AppId，可以和旧版微波吸收分析软件并存，不会覆盖旧应用。

## 2. 当前交付状态

- Git 默认分支：`main`
- v0.14.0 基线提交：`e33b501`（安装目录 `_internal/build_info.json` 记录同一提交，`dirty=false`）
- 版本标签：`v0.14.0`
- Windows 安装程序：`output/releases/MaterialsCharacterizationPlatform-Setup-0.14.0-win64.exe`
- 安装程序 SHA-256：`cee7344ed03da0e4a4a35327559663095a2ff9fc4b6f80d6fd48959f3dd9644f`；同时见 `output/releases/SHA256SUMS-0.14.0.txt`
- 当前已验证测试：`364 passed`
- Ruff：通过
- 源码版和冻结安装版自检：通过（冻结版自检包含工作区自动登记 AnalysisRun）
- 已验证产物：17 类科研图、报告、S 参数、比较、批量、历史和导出

原仓库保留为历史远程 `legacy-origin`：

<https://github.com/Bakkali1747/microwave-absorption-analyzer>

后续开发和发布只能推送到新仓库 `origin`，不要把新版本推回 `legacy-origin`。

## 3. 已实现功能

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
- v0.14.0 起可从 Electromagnetic Measurement 发起分析；分析成功后自动追加 AnalysisRun。
- AnalysisRun 保存结果目录、数值产物、图片与显式导出文件的绝对路径引用；同一测试重跑不覆盖历史。
- 开始分析与登记运行前两次核验源文件 SHA-256；不一致时拒绝执行或拒绝登记。
- 样品详情可查看该测试的全部历史运行、打开结果目录，或只读载入已保存结果（不重新计算）。
- 分析结论只映射为 `PENDING` 或 `WARNING`，绝不自动生成 `VALIDATED`。

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

### 3.3 S 参数

- 解析 S11、S21、S12、S22 的复数、幅度、dB 和相位。
- 计算 R、T、A 和 SE_R、SE_A、SE_T。
- 绘制 S 参数曲线、屏蔽效能图和 Smith 圆图。
- 记录源文件哈希、逐点质量检查和分析状态。
- 支持独立 CLI、GUI 和批量入口。

当前 S 参数字段映射仍是 `candidate_high_confidence`，不是厂商正式确认格式；尚未实现 NRW 反演。

### 3.4 批量、比较、历史与导出

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

v0.14.0 已打通 Measurement → 电磁分析 → AnalysisRun → 结果引用 → 历史查看的闭环，原 Phase B 七步全部实现。以下属于后续增强，不阻塞 Phase C：

- 实测 `.sdat` 的 S 参数运行尚未挂载到 Measurement；目前仍使用独立 S 参数页面。
- 单样品报告和历史页导出尚未自动追加到 AnalysisRun 的 `export_refs`，只有从电磁页面保存图片会登记。
- 工作区尚无 schema 版本、备份恢复和项目导入/导出界面。
- 运行表暂不支持按状态筛选或删除；AnalysisRun 保持追加语义。

### 4.2 Phase C：VSM

当前只能登记 VSM 原始文件。尚需实现格式解析、磁滞回线、Ms/Mr/Hc、背景扣除、质量归一化、绘图、导出和报告。

### 4.3 Phase D：XRD

当前只能登记 XRD 原始文件。尚需实现格式解析、峰检测、峰标注、晶相匹配、晶粒尺寸、绘图、导出和报告。


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
├── common/                 Project、Sample、Measurement、AnalysisRun、分析运行登记
├── analysis_service.py     GUI/CLI 共用分析服务
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
├── pages/                  工作区、单样品、S参数、比较、批量、历史、设置
├── controllers/            GUI 与核心服务的控制层
├── workers/                QThread 后台任务
└── widgets/                公共控件

plotting/                   科学绘图
export/                     数据、报告、追溯和分享导出
packaging/                  PyInstaller 和 Inno Setup 配置
tests/                      自动测试
docs/                       架构、使用和科学约定文档
sample_data/                合成验收数据
run_*.py                    GUI 和 CLI 入口
```

推荐阅读顺序：

1. `README.md`
2. `docs/architecture.md`
3. `docs/workspace.md`
4. `core/common/workspace.py`
5. `core/common/analysis_link.py`
6. `core/analysis_service.py`
7. `gui/pages/workspace_page.py`
8. `gui/pages/single_sample_page.py`
9. `VERSIONING.md`

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
- 原始科研文件不提交 Git。

## 10. 当前技术债和风险

- 工作区尚无正式 `schema_version` 和数据迁移框架（Phase B 已把该事项列为下一步）。
- 工作区尚无多人并发写入控制；AnalysisRun 只追加，导出引用为原地追加。
- 尚无工作区备份、恢复和项目导入/导出界面。
- S 参数运行、单样品报告导出尚未自动登记到 AnalysisRun。
- README 的部分历史章节仍保留旧测试数量或旧阶段描述，需要后续统一清理。
- Windows 安装程序没有商业代码签名，可能显示“未知发布者”。
- 冻结版已在当前开发机验收，但仍需在另一台干净 Windows 电脑验证兼容性。
- GitHub 当前保存源码和标签；安装包尚未作为 GitHub Release 附件发布。

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
3. 启动 GUI，体验工作区“测试 → 电磁分析 → AnalysisRun → 载入结果”闭环。
4. 阅读 PRD、架构文档和本交接文档。
5. 增加工作区 schema 版本与迁移测试，并补上 S 参数运行挂载。
6. 开发 Phase C（VSM），最后开发 Phase D（XRD）。

