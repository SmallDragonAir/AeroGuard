# flightsim.to v0.2.0 更新说明（可直接粘贴）

> 合规要点：上传的压缩包内即软件本体（`AeroGuard.exe` + README + LICENSE）；
> 仓库地址只作为"源码与文档"来源，不作为下载入口。

---

## English — update for v0.2.0

**AeroGuard — local, read-only diagnostics & management for the MSFS / MSFS 2024 Community folder**

This update adds report export, single add-on checks, per-rule handling guidance, and an explicit update check. UI language can be switched between 中文 and English at any time.

**What's in the upload**
- `AeroGuard-v0.2.0-win64.zip` contains the application itself: single-file `AeroGuard.exe` plus `README.md` and `LICENSE`. Extract and run `AeroGuard.exe` — no separate runtime is required.

**What's new in v0.2.0**
- **Single add-on check** — `manage verify PACKAGE` or the "Verify selected add-on" button runs a read-only consistency check on one installed package.
- **Report export: JSON / Markdown / HTML** — Markdown and HTML reports include per-rule handling guidance (meaning, suggested steps, safety notes), handy for forum posts or reporting to add-on authors.
- **Check for updates** — an explicit, read-only check of the latest AeroGuard release. It never downloads or replaces files and is the only network operation in the app.
- **Local notes & rule overrides** — record known findings and ignore/downgrade a rule for a specific add-on; both appear in reports and in the GUI.
- **Complete bilingual coverage** — GUI, CLI text reports, error messages, and all `--help` text follow the selected language (中文 / English).
- **UI improvements** — severity colours, a Notes column, live filtering, and sortable columns on the Issues and Conflicts tabs.

**Unchanged guarantees**
- Scanning is strictly read-only; third-party code (`.exe/.dll/.bat/...`) is never executed.
- Install/replace/rollback remain transactional with backups kept.
- No telemetry; the only network access is the explicit update check.

**Usage**
- Runs on Windows 10/11 (64-bit); extract the attachment and double-click `AeroGuard.exe`.
- Select a Community folder, run a quick or full scan, and use the management/history tabs as needed.

**Requirements**
- Microsoft Flight Simulator (2020) or MSFS 2024, or any folder containing add-on packages.

**Changelog**
- **v0.2.0** — single add-on check; JSON/Markdown/HTML report export with per-rule handling guidance; explicit read-only update check; local notes & rule overrides surfaced in reports/GUI; full bilingual coverage including CLI and `--help`; severity colours, filtering and sortable tables.
- v0.1.0 — initial release: quick/full scanning, impact classification and noise reduction, conflicts/airports/dependencies analysis, bilingual desktop UI, management CLI with Profiles and transactional install/rollback, history and baselines.

**Integrity**
- `AeroGuard-v0.2.0-win64.zip` SHA-256: `05E0687CBCE315DAF40942FE77DD457A84E084FAB3800BA6B566541D49B983A9`
- `AeroGuard.exe` SHA-256: `14B0877F18808185E5D6520FC5736C62A6154BA15D733E407C568A51BA815113`

**About**
AeroGuard is an independent open-source (GPL-3.0) community project, not affiliated with Microsoft or Asobo Studio. Source code and documentation: https://github.com/SmallDragonAir/AeroGuard

---

## 中文 — v0.2.0 更新说明

**AeroGuard —— MSFS / MSFS 2024 Community 插件的本地一致性检查与管理工具**

本次更新加入报告导出、单插件校验、逐条处理建议与显式检查更新；界面可在中文 / English 之间随时切换。

**上传内容说明**
- `AeroGuard-v0.2.0-win64.zip` 内即为软件本体：Windows 单文件 `AeroGuard.exe`，并附 `README.md` 与 `LICENSE`。解压后双击 `AeroGuard.exe` 即可使用，无需额外运行环境。

**v0.2.0 新增**
- **单插件快速校验** —— `manage verify 包名` 或界面"检查选中插件"按钮，对单个已安装插件做只读一致性检查。
- **报告导出 JSON / Markdown / HTML** —— Markdown 与 HTML 报告附带逐条处理建议（含义、建议步骤、安全提示），便于发帖或反馈给插件作者。
- **检查更新** —— 显式、只读地查询 AeroGuard 最新发布；不下载、不替换任何文件，且是全程序唯一的联网操作。
- **本地已知结论与规则覆盖** —— 记录已知结论，并可按（插件, 规则）忽略或降级；两者都会显示在报告与界面中。
- **中英双语全覆盖** —— GUI、CLI 文本报告、错误消息与全部 `--help` 说明均随语言切换。
- **界面改进** —— 严重等级配色、备注列、实时筛选、问题/冲突表格可点击表头排序。

**安全承诺不变**
- 扫描严格只读；从不执行第三方插件中的任何代码（.exe/.dll/.bat…）。
- 安装 / 替换 / 回滚仍为事务化并保留备份。
- 无遥测；唯一联网操作是显式的"检查更新"。

**使用方法**
- 支持 Windows 10/11（64 位）；解压本页附件，双击 `AeroGuard.exe`。
- 选择 Community 文件夹后运行快速或完整扫描；管理 / 历史页签按需使用。

**系统要求**
- Microsoft Flight Simulator（2020）或 MSFS 2024，或任何包含插件的文件夹。

**更新日志**
- **v0.2.0** —— 单插件校验；JSON/Markdown/HTML 报告导出（含逐条处理建议）；显式只读的检查更新；本地已知结论与规则覆盖并显示在报告/界面；CLI 与 `--help` 在内完整双语；严重等级配色、筛选与表头排序。
- v0.1.0 —— 首个版本：快速/完整扫描、影响分类与降噪、冲突/机场/依赖分析、中英双语桌面界面、带 Profile 与事务化安装回滚的管理功能、历史与基线。

**完整性校验**
- `AeroGuard-v0.2.0-win64.zip` SHA-256：`05E0687CBCE315DAF40942FE77DD457A84E084FAB3800BA6B566541D49B983A9`
- `AeroGuard.exe` SHA-256：`14B0877F18808185E5D6520FC5736C62A6154BA15D733E407C568A51BA815113`

**关于**
AeroGuard 是独立的开源（GPL-3.0）社区项目，与微软、Asobo Studio 无隶属关系。源码与文档：https://github.com/SmallDragonAir/AeroGuard
