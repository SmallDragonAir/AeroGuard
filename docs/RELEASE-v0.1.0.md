# AeroGuard v0.1.0

AeroGuard is a local, explainable diagnostics & health-check tool for **Microsoft Flight Simulator (MSFS / MSFS 2024) Community add-ons**. It verifies that installed packages agree with their own metadata, finds cross-package conflicts/dependencies, and offers transactional, rollback-safe local add-on management.

**This is the first distributable release for Windows.**

---

## English

### ✨ Highlights

- **Single-file executable** — `AeroGuard.exe` (~12 MB). Double-click to launch; no Python required.
- **One binary, four frontends** — desktop GUI plus `scan` / `manage` / `history` CLI sub-commands.
- **Bilingual UI (中文 / English)** — auto-detects the OS language; switch instantly from inside the GUI.
- **Read-only by default** — scanning never modifies add-on files; management/install actions require explicit commands and are transactional.

### 📦 Download & Install

**Assets:** `AeroGuard.exe` (Windows 10/11 x64, single file)

```text
AeroGuard.exe                               # open the desktop UI
AeroGuard.exe gui --lang en                 # desktop UI in English
AeroGuard.exe scan <Community> --mode full --json     # full scan + JSON report
AeroGuard.exe manage <Community> <command>  # add-on management CLI
AeroGuard.exe history <Community> <command> # history / baseline CLI
AeroGuard.exe --help                        # usage
```

### 🚀 Feature Overview

**Package consistency diagnostics (quick / full scans)**
- `manifest.json` / `layout.json` parsing and structure checks
- Missing files, file-size mismatches, and files not listed in `layout.json`
- Duplicate paths and invalid Layout entries
- Unreadable tree paths are flagged as “scan incomplete” instead of false “missing”
- Every rule carries a severity (ERROR / WARNING / INFO) with full details + preview
- Missing / size-mismatched / unlisted files classified by potential runtime impact (MSFS-aware path semantics)
- Large size-mismatch batches are stratified-sampled; CRLF→LF line-ending normalization is recognized and transparently downgraded

**Cross-package relationship analysis** (part of `scan`; use `--no-relationships` to skip for speed)
- VFS resource path overlap / override candidates (honors declared dependencies, global overrides, and Package Order Hints)
- Airport duplication candidates (multi-signal, conservative heuristics: package name / title / layout paths)
- Dependency resolution (in-root / out-of-scope / dependency cycles)

**Desktop GUI (native Tk, no third-party runtime)**
- Five tabs: Issues · Conflicts & Dependencies · Add-on Management · Scan Errors · History & Baselines
- Background-thread scans; double-click any row to inspect full JSON; export reports
- Profile applies are dry-run first, then confirmed; installs are inspected → confirmed → transactional → rollbackable
- Language dropdown (中文 / English) switches the UI instantly without restart

**CLI**
- `scan` (main): interactive / non-interactive, JSON reports (`schema_version: 1`), UTF-8 output
- `manage`: inventory · enable · disable · quarantine · restore · profile-save · profile-apply · check · install · rollback · versions · note-* (local knowledge records)
- `history`: record · list · baseline-set · compare (compact snapshots + named-baseline diffs)

**Performance**
- Full scans build per-package file indexes concurrently (I/O-bound): a real 280+ add-on Community went from ≈35 s to ≈21 s
- Per-package traversal hot-spot statistics exposed in the terminal and JSON

### 🔐 Safety & Boundaries

- Scanning is strictly read-only; AeroGuard never executes third-party `.exe/.dll/.bat/.cmd/.ps1` code
- Install-source validation rejects ZIP path traversal, duplicate paths, symlinks, and encrypted entries; archive size limits enforced
- Full consistency inspection runs on a staging copy before any install; replaced versions are kept per-transaction under `backups/`; rollback refuses to overwrite if installed metadata changed
- Replacement/rollback are transactional with automatic undo on failure
- State, disabled packages, profiles, and backups live in `.aeroguard/` next to the Community
- Sources containing executables require an explicit `--allow-executables`
- No network activity at runtime; history and notes stay on disk

### ⚠️ Known Limitations

- Operation error messages in `manage`/`history` and the structural headings of CLI text reports are currently Chinese-only (GUI chrome and diagnostic text are fully bilingual)
- An anomaly is not proof of failure — some add-ons regenerate files at runtime; report message language is the language active when the scan ran
- Some antivirus products may flag PyInstaller single-file executables — add the folder to exclusions if so
- “Online ecosystem” roadmap items (online rule library, cloud known-issue DB, trusted publisher system, Hub, updater) are not implemented yet; see `docs/roadmap-online-services.md`

### 🧪 Tests & Build

```powershell
python -m unittest discover            # 151 tests
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

Runtime: Windows + Python 3.12 for development; the distributed exe needs no Python. Standard library only.

### 📄 License

GNU General Public License v3.0 — see the repository `LICENSE`.

---

## 中文

### ✨ 亮点

- **单文件可执行程序** — `AeroGuard.exe`（约 12 MB）。双击即用，无需安装 Python。
- **一个文件、四种入口** — 桌面界面 + `scan` / `manage` / `history` 三个 CLI 子命令。
- **中英文双语界面** — 自动跟随操作系统语言，也可在界面内即时切换。
- **默认只读** — 扫描从不修改插件文件；管理 / 安装操作需显式命令，且全程事务化、可回滚。

### 📦 下载与使用

**Assets：** `AeroGuard.exe`（Windows 10/11 x64，单文件）

```text
AeroGuard.exe                               # 打开桌面界面
AeroGuard.exe gui --lang zh                 # 桌面界面（中文）
AeroGuard.exe scan <Community> --mode full --json     # 完整扫描 + JSON 报告
AeroGuard.exe manage <Community> <子命令>    # 插件管理 CLI
AeroGuard.exe history <Community> <子命令>   # 历史 / 基线 CLI
AeroGuard.exe --help                        # 用法说明
```

### 🚀 功能总览

**插件包一致性诊断（快速 / 完整扫描）**
- `manifest.json` / `layout.json` 解析与结构检查
- 缺失文件、文件大小不一致、未登记到 layout.json 的文件
- 重复路径与无效 Layout 条目
- 无法读取的文件树路径标记为“扫描不完整”，避免误报缺失
- 每条规则带严重等级（ERROR / WARNING / INFO），提供完整明细与展示预览
- 缺失 / 大小不一致 / 未登记文件按潜在运行影响分类（含 MSFS 目录语义）
- 大批量大小差异分层抽样；可识别 CRLF→LF 换行规范化特征并透明降级

**跨 Package 关系分析**（随 `scan` 运行；可用 `--no-relationships` 跳过以提速）
- VFS 资源路径重叠 / 覆盖候选（识别依赖声明、全局覆盖与 Package Order Hint）
- 机场重复候选（包名 / 标题 / layout 路径多信号，保守启发式）
- 依赖分析（当前根目录内解析 / 范围外 / 依赖环）

**桌面 GUI（原生 Tk，无第三方运行时依赖）**
- 五个页签：问题 · 冲突与依赖 · 插件管理 · 扫描异常 · 历史与基线
- 后台线程扫描；双击任意行查看完整 JSON；导出报告
- Profile 先 dry-run 预演再确认应用；安装先检查 → 确认 → 事务安装 → 可回滚
- 头部语言下拉框（中文 / English）无需重启即可切换

**CLI**
- `scan`（main）：交互 / 非交互、JSON 报告（schema_version 1）、UTF-8 输出
- `manage`：inventory · enable · disable · quarantine · restore · profile-save · profile-apply · check · install · rollback · versions · note-*（本地已知结论）
- `history`：record · list · baseline-set · compare（紧凑快照 + 命名基线差异）

**性能**
- 完整扫描跨包并行建立文件索引（I/O 密集）：真实 280+ 插件 Community 实测约 35s → 约 21s
- 每个插件的遍历热点统计在终端与 JSON 中均可查看

### 🔐 安全与边界

- 扫描严格只读；AeroGuard 从不执行第三方插件中的 `.exe/.dll/.bat/.cmd/.ps1` 等代码
- 安装源校验：拒绝 ZIP 路径穿越、重复路径、符号链接与加密条目，并有归档大小上限
- 安装前在暂存副本上执行完整一致性检查；替换下来的原版本按事务保留在 `backups/`；安装后元数据若变化则拒绝回滚覆盖
- 替换与回滚均事务化，失败自动复原
- 状态、禁用包、Profile 与备份存于 Community 同级的 `.aeroguard/`
- 含可执行文件的安装源需显式 `--allow-executables`
- 运行时无任何网络行为；历史与结论全部保存在本地

### ⚠️ 已知限制

- `manage` / `history` 的操作错误消息与 CLI 文本报告的结构性栏目文字目前仍为中文（GUI 界面与检测说明已完整双语）
- 检出异常 ≠ 插件必然故障（部分插件运行期会自更新文件）；报告内说明文字的语言为扫描时的语言
- 部分安全软件可能对 PyInstaller 单文件 exe 误报——请将该目录加入排除项
- “在线生态”路线项（在线规则库、联网版已知异常库、可信发布者体系、插件 Hub、更新器）尚未实现，规划见 `docs/roadmap-online-services.md`

### 🧪 测试与构建

```powershell
python -m unittest discover            # 151 项测试
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

运行环境：Windows + Python 3.12 用于开发；分发的 exe 无需 Python。纯标准库。

### 📄 开源许可证

GNU General Public License v3.0 —— 详见仓库 `LICENSE`。
