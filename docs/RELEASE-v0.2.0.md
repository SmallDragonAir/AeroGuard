# AeroGuard v0.2.0

AeroGuard is a local, explainable diagnostics & management tool for **MSFS / MSFS 2024 Community add-ons** — bilingual (中文 / English), read-only by default, and now with report export, single add-on checks, per-rule handling guidance, and an explicit update check. / AeroGuard 是面向 MSFS / MSFS 2024 Community 插件的本地诊断与管理工具，中英双语、默认只读；本版新增报告导出、单插件校验、逐条处理建议与显式检查更新。

---

## English

### ✨ Highlights of v0.2.0
- **Single add-on check** — `manage verify PACKAGE` or the "Verify selected add-on" button: a read-only consistency check of one installed package (findings, impact, local notes, overrides).
- **Report export: JSON / Markdown / HTML** — Markdown and standalone HTML reports include **per-rule handling guidance** (what it means, what to do, safety notes) for forum posts, author reports, or your own records.
- **Check for updates** — an explicit, read-only check of the latest AeroGuard release. It never downloads or replaces files, and it is the **only** network operation in the whole app.
- **Local knowledge & rule overrides** — `manage note-*` records known findings; `manage override-*` can ignore or downgrade a rule for a specific add-on. Both are surfaced in reports and in the GUI issues table.
- **Complete bilingual coverage** — GUI, CLI text reports, operation error messages, and every `--help`/argument description now follow the selected language. The GUI asks whether to re-scan when you switch language so messages/reasons also switch.
- **UI quality-of-life** — severity row colours, a Notes column, live filtering, and sortable table headers on the Issues and Conflicts tabs.

### 📦 Package contents
- `AeroGuard.exe` — single-file Windows app (GUI + `scan` / `manage` / `history` / `check-update`)
- `README.md` (bilingual), `LICENSE` (GPL-3.0)

```text
AeroGuard.exe                                 desktop GUI
AeroGuard.exe gui --lang en                   GUI in English
AeroGuard.exe scan <Community> --mode full --json --markdown --html
AeroGuard.exe manage <Community> verify PACKAGE
AeroGuard.exe manage <Community> override-add PACKAGE --rule RULE --action ignore
AeroGuard.exe history <Community> compare stable --mode full
AeroGuard.exe check-update                    read-only update check
```

### 🔐 Unchanged guarantees
- Scanning is strictly read-only; third-party code (`.exe/.dll/.bat/...`) is never executed
- Management/install/rollback remain transactional, with backups kept
- No telemetry; the only network access is the explicit update check

### 🧪 Tests
`python -m unittest discover` → **215 tests**. Build: `powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1`.

---

## 中文

### ✨ v0.2.0 亮点
- **单插件快速校验** —— `manage verify 包名` 或界面"检查选中插件"按钮：对单个已安装插件做只读一致性检查（问题、影响、本地备注与覆盖）。
- **报告导出 JSON / Markdown / HTML** —— Markdown 与独立 HTML 报告附带**逐条处理建议**（含义、处理步骤、安全提示），便于发帖、反馈作者或自行留档。
- **检查更新** —— 显式、只读地查询 AeroGuard 最新发布；不下载、不替换任何文件，且是全程序**唯一**的联网操作。
- **本地已知结论与规则覆盖** —— `manage note-*` 记录已知结论；`manage override-*` 可按（插件, 规则）忽略或降级，并在报告与界面问题表中体现。
- **中英双语全覆盖** —— GUI、CLI 文本报告、操作错误消息、各 `--help` 与参数说明均随语言切换；切换语言时界面会询问是否重扫，让说明文案一并切换。
- **界面体验** —— 严重等级行配色、备注列、实时筛选、问题/冲突表格表头排序。

### 📦 包含内容
- `AeroGuard.exe` —— Windows 单文件程序（GUI + `scan` / `manage` / `history` / `check-update`）
- `README.md`（双语）、`LICENSE`（GPL-3.0）

```text
AeroGuard.exe                                 桌面界面
AeroGuard.exe gui --lang zh                   中文界面
AeroGuard.exe scan <Community> --mode full --json --markdown --html
AeroGuard.exe manage <Community> verify PACKAGE
AeroGuard.exe manage <Community> override-add PACKAGE --rule RULE --action ignore
AeroGuard.exe history <Community> compare stable --mode full
AeroGuard.exe check-update                    只读检查更新
```

### 🔐 安全承诺不变
- 扫描严格只读；从不执行第三方代码（.exe/.dll/.bat…）
- 管理 / 安装 / 回滚仍为事务化并保留备份
- 无遥测；唯一联网操作是显式的"检查更新"

### 🧪 测试与构建
`python -m unittest discover` → **215 项测试**。构建：`powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1`。

---

### Version note / 版本说明
Built from `version.py` = `0.2.0`; the exe carries FileVersion/ProductVersion 0.2.0.
请以本页附件中的 `AeroGuard.exe` 为准（更新检查只提示，不下载）。
