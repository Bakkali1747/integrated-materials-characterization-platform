# Windows 独立客户端

当前安装包为 GUI Phase 4（v0.9.0），新增持久化设置、全部图片导出及历史视图优化。操作见 `gui_phase4.md`、`gui_phase3.md` 和 `gui_phase2.md`。

## 安装和启动

双击 `MicrowaveAbsorptionAnalyzer-Setup-0.9.0-win64.exe`，按安装向导完成安装。安装到当前用户目录，不需要 Python 或 Git，也不要求管理员权限。可创建桌面快捷方式；安装完成后从桌面或开始菜单打开“微波吸收材料分析软件”。

目标为 Windows 10（1809 或更高）/Windows 11 x64。界面为中文，安装向导按钮使用英文。客户端未做商业代码签名，Windows 可能显示“未知发布者”；请只使用随交付提供哈希的安装文件。

## 数据保存

- 默认分析输出：`%LOCALAPPDATA%\MicrowaveAbsorptionAnalyzer\output`
- 日志：`%LOCALAPPDATA%\MicrowaveAbsorptionAnalyzer\logs\app.log`
- 默认设置：`%LOCALAPPDATA%\MicrowaveAbsorptionAnalyzer\settings\gui.json`；升级和卸载保留用户数据目录。
- 用户可以在单样品页面选择其他输出目录。
- 每次分析独立建目录，仍记录原文件哈希、参数、软件版本、构建提交及验证状态。
- 在 Windows“已安装的应用”中卸载程序；卸载不删除上述科研结果和日志。

安装版与源码版复用同一个计算核心。MEMP 的虚部定义与商业软件对照仍待验证，SDAT 仍为候选字段映射；打包不会改变验证状态。现有功能见 `gui_usage.md`。

## 开发构建

使用项目内隔离的 Python 3.12 环境 `output/package-env`，安装 `packaging/requirements-build.txt` 固定版本依赖，再运行：

```powershell
.\output\package-env\Scripts\python.exe packaging/build_client.py
```

构建脚本生成 `output/packaging/build_info.json`，随后构建 `output/dist/MicrowaveAbsorptionAnalyzer`，最后用 `output/packaging-tools/InnoSetup/ISCC.exe` 生成 `output/releases` 中的安装包。发布构建必须在干净提交上运行；开发构建会准确标记 dirty。

构建脚本清理 PyInstaller 缓存并隔离 PATH，不从外部开发工具中收集同名运行库。Qt 使用 Windows 系统 ICU，禁止捆绑 Poppler 的不兼容版本。

安装包包含 Python 和动态 Qt 依赖及其 distribution 元数据/许可证。不包含用户真实测量文件，仅含合成验收样品。发布产物不纳入 Git。

冻结版自检（开发验收使用，普通用户无需输入）：

```powershell
MicrowaveAbsorptionAnalyzer.exe --self-test "验收输出目录"
```

自检经过真实 Qt 导入和分析按钮、后台任务、四类嵌入图、Excel 导入和四种图片导出，输出 `smoke_report.json`。仍需在其他独立 Windows 电脑上确认兼容性；同机隔离 PATH 验收不等于跨机器实测。
