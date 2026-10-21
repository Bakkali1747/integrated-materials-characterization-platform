# v0.9.5 评审问题修复说明

本版按《微波吸收材料分析软件·优化评审报告》处理了 P0/P1 中风险可控、可自动验证的部分；科学公式（RL、EAB 定义、阻抗、S 参数）未改变。

## 已修复

### P0-1 Excel 导入误诊与工作表/表头选择

- 表头先 `strip()`，`NaN` 统一为空字符串；只对非空表头判断重复，空表头不再被误报成“重复列名”。
- 首行只有标题、其余为空时，报错改为：“Excel 第 1 行第 2–8 列为空；这看起来像标题行，不是表头。请指定表头行，或选择包含五列数据的工作表。”
- 新增 `header_row`（0 起始）：标题/说明行可放在表头之前；Excel 源行号随表头行顺延。
- 表头行超出范围、工作表名称或序号不存在、未找到标准列，均给出可操作提示，而不是笼统失败。
- GUI 参数面板新增“Excel 工作表”“Excel 表头行”；列映射预览只读取前 12 行，不再整文件载入。
- CLI 新增 `--header-row`；批次清单的 `parser` 支持 `header_row`。

### P0-4 精确 `-inf` RL 不再中断整次分析

- 阈值跨越涉及 `-inf` 时，交点取该采样点本身，宽度贡献为 0；原始 `-inf` 不裁剪、不替换。
- 频段记录 `uses_infinite_limit`，结果记录 `infinite_limit_crossings_ghz`，便于追溯极限交点。
- `summarize_bandwidths()` 不再因单个厚度出现 `-inf` 而让整次分析失败。
- 有限点之间的线性交点行为不变；`NaN`/`+inf` 仍拒绝。

### P0-3 图片配套数据写入来源与验证状态

- 每个 `.data/metadata.json` 增加 `provenance`：`software_version`、`run_id`、`sample`、`raw_sha256`、`validation_status`、`configuration_sha256`、`analysis_date`、`created_at`、`dpi`。
- 新增 `.data/provenance.json`；图片被单独拷走后仍能核对来源与验证状态。
- `index.csv` 前两列改为 `run_id`、`validation_status`。
- 分析图、S 参数图、理论/实测对照图、单图导出与“导出全部图片”均传入对应记录；没有上下文的独立导出明确写 `validation_status: unknown`。
- 修复 `.data` 路径被同名普通文件占用时的 `NotADirectoryError`，改为清晰的“同名文件占用”错误。

### P1 快速修复

- 批量目录发现支持 `.xls`，与单样品/GUI 一致。
- sdat 无 BOM 时先严格尝试 UTF-8，再退回 GB18030/GBK；UTF-8 中文元数据不再被静默解成乱码。
- 历史页“核验”使用下拉框当前选中项，不再核验上一次加载的运行。
- 厚度滑块初始化到 `curve_thickness` 的网格位置（最近点），并说明“不在扫描网格”的情况。
- 主动取消改为中性提示，不再显示为红色错误。
- GUI 安装全局异常钩子：未捕获异常与 Qt 消息写入 `app.log` 并弹窗给出日志路径。
- S 参数表最多预览 2000 行，完整数据仍保存在 `sparameters_by_frequency.csv`。
- 多厚度 RL 图参考线改用请求阈值，不再固定 −10 dB；四分之一波长图使用记录中的实际阶数。
- `artifact_hashes` 改为分块读取，避免大矩阵/大图一次性占用内存。

### 工程卫生

- 版本一致性测试：`core.__version__`、`pyproject.toml` 与 `client.iss` 默认值必须相同。
- 构建脚本在 Git 工作区有未提交修改时默认失败，需显式 `--allow-dirty` 才生成开发版。
- CSV 导出对以 `= + - @` 开头的用户文本加前导 `'`，防止 Excel 公式注入；纯数值不变。
- 批量记录改为逐样品追加 `members.jsonl`、结束时汇总 `batch_record.json`，避免每完成一个样品就重写整份记录。
- `new_run` 的源文件 SHA-256 改为分块读取，降低大文件哈希时的内存峰值。

### P0-2 单一分析管线（已抽成共享服务）

- 新增 `core/analysis_service.py`：输入校验、`new_run`、读取/裁选、RL/EAB/累计覆盖、数值 CSV 与 `summary.json` 只在这里生成一次。
- `run_analysis.analyze()` 与 `gui.controllers.analysis_controller.analyze_request()` 变为适配层，只负责图组、进度、取消和最终记录。
- 参数错误在创建运行目录之前拒绝，不再留下“参数错误”的失败目录；读取/计算失败仍写 `failed` 记录，主动取消写 `cancelled`。
- 两条入口现在共享同一份 `summary.json` 字段、`thickness_summary.csv` 七列、验证状态与警告文案。
- 跨管线测试断言 `global_minima`、`standard_eab`、累计覆盖及 CSV 列完全一致。

### 管线一致性（P0-2 的可验证部分）

- GUI 现在写出与 CLI 相同的 `cumulative_frequency_coverage` 和 7 列 `thickness_summary.csv`。
- GUI 的 EAB 交点方法、四分之一波长阶数、阻抗容差进入请求快照与运行记录，不再硬编码。
- GUI 验证状态依据 `convention_confirmed` 生成，与 CLI 同一规则。
- GUI 参数面板已暴露 EAB 交点方法、四分之一波长阶数与阻抗显示容差，并同步写入请求和运行记录。
- 跨管线测试新增覆盖：`summary.json` 的 `global_minima`、`standard_eab`、累计覆盖一致，`thickness_summary.csv` 列一致。

### 版本与文档

- 版本号统一为 0.9.5：`core/__init__.py`、`pyproject.toml`、`packaging/client.iss` 默认值一致。
- 修复测试在中文 Windows 默认 GBK 下的 4 项解码失败；读取生成的 JSON 一律显式 `encoding="utf-8"`。

### 输出体积、去重与复用（P1-3）

- GUI 默认分析图 300 dpi；手动“保存当前图片/导出全部图片”至少 600 dpi（用户设置更高时跟随），兼顾预览速度与投稿质量。
- 图片配套 CSV 内容相同的网格按硬链接复用；跨卷或文件系统不支持时自动退回独立副本，不改变数据。
- 批量可按“源 SHA-256 + 数值配置”复用已完成运行（GUI 复选框或 CLI `--reuse`），成员记录 `reused_from`；只复用数值与解析配置一致的运行。单样品页同样提供复选框，命中时加载已有对象并按需重绘图片。
- `run_maintenance.py --duplicates` 按样品、源哈希和配置列出重复运行，报告可回收空间。
- `run_maintenance.py --delete` 将旧运行移入 Windows 回收站，写 `deletion_manifest.json`；单个失败不影响其他运行。

### 分享与底层稳定性（P2）

- 新增 `run_share.py` 与历史页“导出可分享记录…”：移除本地绝对路径，保留文件名、SHA-256、验证状态和摘要；原运行不变。
- 绘图改为未注册到 pyplot 的 `Figure` + Agg canvas，减少后台线程对全局图表的争用。
- RL 归一化阻抗按厚度分块计算（默认 50 万点/块），数值与整块计算逐点一致，降低大网格峰值内存。

## 尚未完成

- **工程化**：安装包签名仍需外部工具与发布流程；依赖锁定、Windows CI 与 ruff 门禁已补充。
- **直接永久删除**：只提供归档与回收站删除，不提供不可恢复的删除入口。

这些项目需要单独的验收标准，不能以本轮“测试通过”代替。

## 验证

- 全量自动测试通过（数量见 CHANGELOG 与 README）。
- 新增测试覆盖：Excel 标题行/重复表头/工作表与表头行错误、`-inf` 极限交点、`.xls` 发现、UTF-8 sdat、`provenance` 与 `index.csv`、同名文件冲突、滑块初始位置、历史核验选中项、网格硬链接去重、批量复用、回收站删除预演/失败隔离、脱敏分享、分块 RL 一致性。
- 真实 `.memp` 虚部定义与商业软件定量对照仍未确认；本版不改变 PENDING/candidate 结论。
