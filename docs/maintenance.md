# 输出目录维护：查看占用与归档旧运行

该入口只**移动**运行目录，不直接删除；默认只预演。归档后目录结构不变，
`analysis_record.json`、图片、`.data` 与哈希全部保留。

## 查看占用

```powershell
.\.venv\Scripts\python.exe run_maintenance.py --root output --list
```

列出每个运行的样品、日期、状态、占用和相对路径。只识别含
`analysis_record.json` 的运行目录，跳过 `figures`、`*.data` 和 `_archive`。

## 预演与归档

```powershell
# 预演：只显示将移动什么，不改变磁盘
.\.venv\Scripts\python.exe run_maintenance.py --root output --older-than 30

# 确认后真正执行
.\.venv\Scripts\python.exe run_maintenance.py --root output --older-than 30 --apply
```

其他选择条件：

```powershell
.\.venv\Scripts\python.exe run_maintenance.py --root output --status failed --apply
.\.venv\Scripts\python.exe run_maintenance.py --root output --sample CIP --older-than 90 --apply
.\.venv\Scripts\python.exe run_maintenance.py --root output --all --apply
```

`--sample` 为不区分大小写的包含匹配；`--status` 精确匹配。缺少分析日期的运行
不会被“按天数”选中，避免误归档。

## 归档位置与清单

默认归档到 `<root>/_archive`，也可用 `--archive-root` 指定其他位置：

```powershell
.\.venv\Scripts\python.exe run_maintenance.py --root output --older-than 30 --archive-root D:\archive\absorption
```

每次执行都会追加 `_archive/archive_manifest.json`，记录归档时间、原相对路径、
目标路径、样品、状态和字节数。同名目标自动追加时间戳，不覆盖旧归档。
移动后若样品目录已空会被删除。历史页扫描会跳过 `_archive`，不会把归档误当当前结果。

## 安全边界

- 预演不创建归档目录、不移动文件。
- 归档目录不能位于被归档的运行目录内。
- 不是有效运行目录（缺少 `analysis_record.json`）会被拒绝。
- 归档不是删除；确认不再需要后，由用户自行清理归档区。

## 删除到回收站

```powershell
# 预演：只显示将删除什么
.\.venv\Scripts\python.exe run_maintenance.py --root output --older-than 30 --delete

# 确认后移入 Windows 回收站
.\.venv\Scripts\python.exe run_maintenance.py --root output --older-than 30 --delete --apply
```

删除使用 Windows 回收站（`FOF_ALLOWUNDO`），不是不可恢复删除；其他平台会拒绝并提示改用归档。
每次执行追加 `deletion_manifest.json`，记录时间、相对路径、大小和失败项；单个运行失败不影响其他运行。
删除前的预演、筛选和有效运行校验与归档一致。

## 查找重复运行

```powershell
.\.venv\Scripts\python.exe run_maintenance.py --root output --duplicates
```

按“样品 + 源 SHA-256 + 数值配置”分组；每组保留最新一份，列出其余可回收路径和空间。
该命令只报告，不移动或删除；确认后可配合 `--older-than`/`--status` 选择并 `--delete` 或归档。

## GUI 入口

历史结果页扫描目录后，点击“归档旧运行…”：输入天数 → 后台预演 → 弹窗显示将移动的运行数与大小 → 确认后才执行。归档完成后自动重新扫描，并在状态栏显示清单路径。

## 相关

- 批量复用相同源与配置的运行：见 [分享与复用](share_and_reuse.md)。
- 可分享的脱敏运行记录：见 [分享与复用](share_and_reuse.md)。

## 尚未实现

- 不可恢复的直接删除（只提供归档与回收站删除）。

