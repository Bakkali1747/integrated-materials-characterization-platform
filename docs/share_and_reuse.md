# 分享副本与批量复用

## 可分享的脱敏记录

```powershell
.\.venv\Scripts\python.exe run_share.py --run "output/sample_S/20260101T000000_abcd" --output "D:\share\S_run"
```

目标目录必须不存在或为空。生成内容：

- `analysis_record.json`（脱敏：绝对路径替换为文件名，保留 `raw_sha256`、验证状态和配置）
- `summary.json`、`summary.csv`、`sources.csv`、`data_quality.json`、`validation_errors.json`（存在时复制；CSV/JSON 逐单元格脱敏）
- `README_SHARE.txt`：运行状态、验证状态、源文件哈希和“图片不在包内”的说明
- `share_manifest.json`：实际复制文件及各自 SHA-256

原运行目录不会被修改；图片默认不包含，避免体积和额外泄露。历史结果页加载运行后，也可点击“导出可分享记录…”选择存放目录。

脱敏只处理明确为路径的字段和以盘符/斜杠开头的字符串；不会猜测普通文本的含义。分享前仍应人工检查警告文本是否含敏感信息。

## 批量复用已完成运行

批量分析在显式开启复用时，会比较：

- 源文件 SHA-256；
- 样品名称；
- 影响数值结果的配置：频率/厚度范围、步长、曲线厚度、阈值、EAB 交点、解析选项、四分之一波长阶数、阻抗容差。

匹配到 `status=success` 的运行时不重新计算，成员记录 `reused_from`，并复用其摘要与 QC。图幅、DPI、入口和快速预览状态不参与匹配。

开启方式：

- GUI 批量页勾选“批量复用相同源 + 配置的已完成运行”；
- GUI 单样品页勾选同一复选框后点击开始分析，命中时直接加载已有运行并按需重绘图片；
- CLI `run_batch.py ... --reuse`；
- CLI 单样品 `run_analysis.py ... --reuse`，命中时直接打印并返回已有运行目录。

维护入口 `run_maintenance.py --duplicates` 会按样品、源哈希和配置列出重复运行，
每组保留最新一份，并报告其余可回收空间。

复用只针对材料 ε/μ 分析；`sdat` 仍独立计算。复用目录可能位于旧的批次目录中，`sources.csv` 会明确写出 `reused_from`，不会复制或改写旧运行。

## 体积相关

- GUI 分析图默认 300 dpi，手动导出至少 600 dpi；CLI 仍默认 600 dpi。
- 相同网格 CSV 在同一卷上使用硬链接；复制 `.data` 到其他磁盘后自然变成独立副本。
- 清理旧运行见 [输出目录维护](maintenance.md)。
