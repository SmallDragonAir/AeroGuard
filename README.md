# AeroGuard

> 面向 Microsoft Flight Simulator 的本地插件诊断与环境健康检查工具。

AeroGuard 是一个正在开发中的开源 MSFS 插件诊断工具，用于检查 Community 文件夹中的插件包结构、元数据和文件一致性，并以尽可能可解释的方式报告潜在问题。

项目目前仍处于早期开发阶段，现阶段重点是建立可靠、确定性的本地扫描与分析能力。

> ⚠️ AeroGuard 检测到异常，并不等于插件本身存在实际运行故障。

---

## ✈️ AeroGuard 能做什么？

当前版本可以扫描 MSFS Community 文件夹中的插件，并检查：

- `manifest.json` 元数据
- `layout.json` 是否存在
- `layout.json` 是否能够正常解析
- `layout.json` 中是否存在无效条目
- `layout.json` 中是否存在重复路径
- 声明的文件是否真实存在
- 文件实际大小是否与 `layout.json` 一致
- 插件目录中是否存在未登记到 `layout.json` 的文件
- 按插件聚合检测结果
- 按规则统计异常数量
- 异常数量排行
- 重点复核排行
- 缺失 / 大小不一致 / 未登记文件按潜在运行影响分类
- 快速扫描 / 完整扫描
- 可选 JSON 报告输出（含完整明细，便于程序化处理）
- 支持命令行参数非交互运行
- 文件树局部无法读取时标记扫描不完整，避免把未知状态误报为文件缺失
- 记录完整扫描中每个已建立索引插件的遍历耗时，并在终端与 JSON 中提供热点排行数据
- 大批量大小差异经过分层抽样后，可识别 CRLF → LF 换行规范化特征并降级
- 检测多个 Package 声明到同一 VFS 相对路径的资源覆盖候选
- 基于 Package Order Hint、依赖声明与全局覆盖声明识别有意覆盖关系
- 使用包名、标题和 layout 路径多信号识别机场重复候选
- 分析当前扫描根目录内依赖、范围外依赖与依赖环
- 显式启用 / 禁用 Community 包，并保存可重复应用的 Profile
- 把可疑包移入 Community 外的安全隔离区并恢复到原状态
- 对目录或 ZIP 安装源做路径安全、结构与文件一致性检查
- 安装新包或替换旧版本时保留事务备份，并支持安全回滚
- 列出启用、禁用、隔离、备份与已回滚版本
- 使用原生桌面界面执行后台扫描、浏览详情、导出报告和管理插件
- 保存紧凑扫描历史，建立命名环境基线并比较插件、问题、冲突与依赖变化
- 自动忽略 Thumbs.db / .DS_Store 等系统杂物文件

`main.py` 的扫描流程始终只读。`manage.py` 只在用户运行明确的管理子命令时
移动或安装指定包；默认把状态、禁用包和备份存入 Community 同级的
`.aeroguard/`，不修改 `Official*`、`UserCfg.opt` 或模拟器的 `Content.xml`。

---

## 🛡️ 设计原则

AeroGuard 会尽量区分以下几个概念。

### 检测事实（Finding）

扫描器能够确定的客观事实。

例如：

```text
layout.json 声明了某个文件，但实际插件目录中不存在该文件。
```

### 严重等级（Severity）

描述插件包自身的一致性问题有多明显。

当前包括：

```text
ERROR
WARNING
INFO
```

### 潜在运行影响（Impact）

描述某个异常是否可能影响插件在 MSFS 中的实际运行。

当前包括：

```text
POTENTIALLY_RUNTIME
LIKELY_NON_RUNTIME
UNKNOWN
```

其中：

- `POTENTIALLY_RUNTIME`：可能涉及实际运行资源
- `LIKELY_NON_RUNTIME`：更可能属于说明文档、构建工具或安装辅助文件
- `UNKNOWN`：现有规则不足以可靠判断

AeroGuard 不会仅凭本地扫描结果直接认定某个插件开发者发布了损坏的软件。

例如，AeroGuard 更倾向于报告：

> 当前安装的插件内容与其自身元数据存在差异。

而不是：

> 这个插件是坏的。

---

## 🔍 扫描模式

### 快速扫描

主要检查：

- `manifest.json`
- `layout.json`
- Layout 数据结构
- 重复路径
- 无效条目

快速扫描不会遍历整个插件文件树。

适合日常快速检查。

### 完整扫描

包含快速扫描的全部内容，并进一步检查：

- 缺失文件
- 文件大小不一致
- 未登记文件

对于包含大量插件或大量小文件的 Community 文件夹，完整扫描可能需要较长时间。

---

## 🧠 当前架构

```text
AeroGuard/
├── main.py        # CLI 入口：交互 / 命令行参数 / JSON 报告
├── scanner.py     # 发现插件包并读取 manifest 元数据
├── analyzer.py    # 运行确定性一致性检测规则（返回 issues 与性能统计）
├── classifier.py  # 对文件级问题做潜在运行影响分类
├── noise.py       # 基于可复核抽样证据降低高置信度扫描噪音
├── relationships.py # VFS 资源冲突、机场与依赖关系分析
├── report.py      # 纯数据聚合与 JSON 报告文档构造
├── management.py  # 启停、Profile、隔离、安装检查与事务回滚
├── manage.py      # 插件管理 CLI
├── history.py     # 紧凑扫描历史、环境基线与差异比较
├── history_cli.py # 历史 / 基线 CLI
├── gui.py         # Tk 原生桌面界面与后台任务协调
├── AeroGuard.pyw  # Windows 无控制台启动入口
├── tests/         # 自动化测试（stdlib unittest，合成 fixture）
└── tools/dev/     # 开发期一次性调试脚本（非产品代码）
```

### `scanner.py`

负责发现插件包并读取基础元数据，同时保留原始 manifest 供后续功能使用。

### `analyzer.py`

负责运行确定性的插件一致性检测规则。`details` 中始终保存完整明细，
`preview` 提供终端展示用的截断视图；耗时统计通过返回值提供，
不再直接打印到标准输出。完整扫描还会记录每个已建立索引插件的
遍历耗时与文件数，用于定位大型目录热点。

### `classifier.py`

负责根据文件路径、扩展名与目录语义，对缺失文件、大小不一致与
未登记文件逐条进行潜在运行影响分类。

### `noise.py`

负责保守的自动降噪。目前只处理至少 20 项的批量大小差异，并从不同
顶层目录和扩展名中选择最多 64 个代表样本。只有所有样本的大小差都
精确符合 CRLF 转 LF 的换行规范化特征时，才将该问题从 WARNING 降为
INFO；原等级、规则与抽样证据仍会保留在 JSON 报告中。

### `report.py`

提供与展示无关的纯数据聚合（按规则统计、排行、按插件风险等），
并负责构造可序列化的 JSON 报告文档。

### `relationships.py`

负责当前扫描根目录内的跨 Package 分析。资源路径重叠会按 VFS 目录、
声明大小和覆盖意图分级。资源级有意覆盖只接受显式依赖或全局覆盖声明；
Patch Hint 只在同一机场代码候选中作为意图信号，避免把互不相关的包
仅因顺序组相邻而配对。默认优先包只在相同 Package Order Hint 下推断，
并明确标记为默认顺序，因为游戏内仍可重排 Package。

机场识别采用保守启发式：机场标识必须同时获得包名或标题、以及 layout
路径两个来源的支持。`airport_code` 包含 ICAO 与 `5Z5`、`FVM` 这类本地
机场代码。它不会解析 BGL 内部对象，因此未识别不等于不存在机场，识别
结果也仍需在 DevMode VFS/机场工具中确认。

依赖分析只对当前扫描根目录内的包做解析。未在当前目录找到的依赖标记为
`outside_scan_scope`，因为它可能位于 Official、Community2024 或流式包源，
不会直接报告为“缺失依赖”。

### `main.py`

目前作为 AeroGuard 的命令行开发与测试入口，负责参数解析、
运行扫描流程并呈现文本 / JSON 结果。

### `management.py` / `manage.py`

管理器只操作命令行中指定的 Community 根目录。禁用通过把完整包目录移动到
管理状态目录完成，重新启用时移回；移动要求两个目录位于同一磁盘，避免把
跨盘复制误当成原子切换。Profile 记录保存时已知包的启用状态，应用时不会
改变后来新增且未列入 Profile 的包。禁用或应用 Profile 时，如果仍启用的包
显式依赖即将移出的包，事务结果会保留依赖警告。缺失或无法解析 manifest 的
目录会显示在清单中，但不会自动写入 Profile。

安装源可以是一个包目录、包含多个包的目录或 ZIP。管理器拒绝 ZIP 路径穿越、
重复路径、符号链接、加密条目和超过安全上限的归档；随后在暂存区运行完整
一致性检查。包含 `.exe`、`.dll`、`.bat`、`.cmd`、`.msi` 或 `.ps1` 时需要
显式传入 `--allow-executables`，AeroGuard 仍不会执行这些文件。

替换现有包前，原目录会按事务 ID 保存在 `backups/`。回滚不会删除新版本，
而是把它移入 `rolled-back/`；如果新版本的 `manifest.json` 或 `layout.json`
在安装后发生变化，回滚会停止，避免覆盖未知状态。所有备份均保留，当前
不做自动清理。版本字段按 manifest 原文展示，不推断版本先后关系。

### `gui.py` / `AeroGuard.pyw`

原生桌面界面使用本机 Python 3.12 自带的 Tk 8.6，不引入第三方 GUI 依赖。
扫描、安装检查和管理操作在后台线程执行，完整扫描期间窗口仍可响应。界面提供
问题、冲突与依赖、插件管理、扫描异常、历史与基线五个页签，双击表格行可查看
完整 JSON 数据。Profile 会先执行 dry-run 并显示移动数与警告数，再允许应用。

### `history.py` / `history_cli.py`

历史快照不会复制完整报告中的数万条文件明细，而是保存包版本、聚合问题、
扫描错误、资源 / 机场冲突、依赖状态及证据哈希。基线比较分别报告新增、移除
和变化项；扫描模式或 Community 路径不同时会给出兼容性提示。历史与基线
同样写入 `.aeroguard/history/`，已存在的命名基线需要 `--replace` 才会更新。

---

## 🚧 当前开发状态

AeroGuard 目前属于早期实验性项目。

当前 CLI 主要用于：

- 开发扫描引擎
- 验证检测规则
- 收集真实插件样本
- 校准误报
- 测试异常分类逻辑
- 性能分析
- 在明确命令下试验可回滚的本地插件管理

目前尚不建议根据 AeroGuard 的扫描结果直接删除、修改或重新安装插件。

---

## 🗺️ 开发路线

### 第一阶段：插件包诊断

- [x] Community 插件发现
- [x] Manifest 解析
- [x] Layout 解析
- [x] 缺失文件检测
- [x] 文件大小异常检测
- [x] 未登记文件检测
- [x] 无效 Layout 条目检测
- [x] Layout 重复路径检测
- [x] 基础影响分类器
- [x] 按插件聚合检测结果
- [x] 异常数量排行
- [x] 重点复核排行
- [x] 完善影响分类器（缺失 / 大小不一致 / 未登记，基于完整明细与目录语义）
- [x] 优化检测结果表达（统一明细结构、JSON 报告、命令行参数、扫描错误明细）
- [x] 性能分析与优化（per-addon 热点统计、普通目录免重复 realpath）
- [x] 自动化测试（`python -m unittest discover`）
- [x] 降低误报率（高置信度换行规范化识别与透明降级）

### 第二阶段：插件冲突检测

- [x] Package 资源冲突检测（VFS 相对路径索引）
- [x] 机场重复 / 冲突检测（ICAO / 本地机场代码的多信号保守识别）
- [x] 识别有意覆盖关系（依赖、Patch Hint、全局覆盖声明）
- [x] 冲突严重程度分类（作用域、声明大小、覆盖意图）
- [x] 插件依赖关系分析（根目录内解析、范围外标记、依赖环）

### 第三阶段：插件管理

- [x] 插件启用 / 禁用（Community 外同盘移动）
- [x] 插件配置方案（Profile，未列入的后来新增包保持现状）
- [x] 安全隔离（记录原因与原启用状态）
- [x] 安装前检查（目录 / ZIP、安全路径与完整一致性扫描）
- [x] 安装回滚（事务备份、变化保护、回滚版本保留）
- [x] 插件版本管理（当前位置、备份与回滚历史清单）

### 后续计划

- [x] 原生桌面 GUI（Tk、后台扫描、详情、导出与管理操作）
- [x] 扫描历史与环境基线（紧凑快照、命名基线、结构化差异）
- [ ] 可选在线规则库
- [ ] 已知异常数据库
- [ ] 可信发布者体系
- [ ] 插件仓库 / Hub
- [ ] 安装与更新管理

---

## ▶️ 运行

当前开发环境：

- Windows
- Python 3.12

运行：

```powershell
# 原生桌面界面
python gui.py D:\MSFS2024_DATA\Community --mode quick

# Windows 无控制台窗口；也可以在资源管理器中双击 AeroGuard.pyw
pythonw AeroGuard.pyw D:\MSFS2024_DATA\Community

# 交互模式：随后输入 Community 路径并选择 1=快速扫描 / 2=完整扫描
python main.py

# 非交互模式
python main.py D:\MSFS2024_DATA\Community --mode quick
python main.py D:\MSFS2024_DATA\Community --mode full

# 完整扫描并输出 JSON 报告（自动保存到 reports/ 目录）
python main.py D:\MSFS2024_DATA\Community --mode full --json

# 指定 JSON 输出路径
python main.py D:\MSFS2024_DATA\Community --mode quick --json reports\scan.json
```

插件管理命令会修改指定 Community，请先退出模拟器；完成后需要重新启动模拟器
才能让包挂载状态稳定生效。以下命令中的 `PACKAGE` 是 Community 中的包目录名：

```powershell
# 只读查看当前管理清单与版本归档
python manage.py D:\MSFS2024_DATA\Community inventory
python manage.py D:\MSFS2024_DATA\Community versions

# 启用、禁用与隔离
python manage.py D:\MSFS2024_DATA\Community disable PACKAGE
python manage.py D:\MSFS2024_DATA\Community enable PACKAGE
python manage.py D:\MSFS2024_DATA\Community quarantine PACKAGE --reason "待排查冲突"
python manage.py D:\MSFS2024_DATA\Community restore PACKAGE

# 保存、预演并应用 Profile
python manage.py D:\MSFS2024_DATA\Community profile-save flying
# 更新同名 Profile 时显式覆盖
python manage.py D:\MSFS2024_DATA\Community profile-save flying --replace
python manage.py D:\MSFS2024_DATA\Community profile-apply flying --dry-run
python manage.py D:\MSFS2024_DATA\Community profile-apply flying

# 安装前只读检查、安装与按事务 ID 回滚
python manage.py D:\MSFS2024_DATA\Community check D:\Downloads\addon.zip
python manage.py D:\MSFS2024_DATA\Community install D:\Downloads\addon.zip
python manage.py D:\MSFS2024_DATA\Community rollback TRANSACTION_ID
```

需要改用其他状态目录时，把 `--state-dir PATH` 放在 Community 路径之后、
管理子命令之前。状态目录必须位于 Community 外且应与 Community 位于同一磁盘。

扫描历史和环境基线：

```powershell
# 扫描并保存一个紧凑历史快照
python history_cli.py D:\MSFS2024_DATA\Community record --mode full --label "SU4 前"

# 查看历史并把指定快照设为基线
python history_cli.py D:\MSFS2024_DATA\Community list
python history_cli.py D:\MSFS2024_DATA\Community baseline-set stable --snapshot SNAPSHOT_ID

# 重新扫描、比较并同时保存当前快照
python history_cli.py D:\MSFS2024_DATA\Community compare stable --mode full --record
```

基线与当前扫描应使用相同模式；不同模式仍可比较，但结果会明确标记兼容性提示。

运行自动化测试（需要合成 fixture，不需要真实 Community）：

```powershell
python -m unittest discover
```

> 开发期的一次性调试脚本位于 `tools/dev/`，不属于产品代码。

---

## ⚠️ 关于扫描结果

AeroGuard 当前主要检测的是：

> 插件实际文件状态与插件自身元数据之间的一致性。

因此，一个异常并不一定意味着插件无法正常运行。

部分插件可能会：

- 安装后自动生成文件
- 运行后修改文件
- 使用自己的更新程序修改资源
- 保留旧版本 `layout.json`
- 包含开发或打包工具
- 包含不参与实际运行的说明文件
- 使用运行时生成的数据

AeroGuard 会尽量区分这些情况，但当前分类规则仍在开发中。

---

## 🔐 安全原则

AeroGuard 的扫描器遵循：

> 能只读，就不执行。

扫描和管理过程中不会主动运行第三方插件中的：

- `.exe`
- `.bat`
- `.cmd`
- `.dll`
- 其他可执行程序或脚本

未来如果增加第三方诊断程序集成，也应要求：

1. 明确的可信来源
2. 精确的程序白名单
3. 文件完整性验证
4. 用户明确授权

---

## 🤝 参与测试

目前最有价值的帮助包括：

- 提供不同插件的扫描结果
- 使用正版、干净安装环境进行交叉验证
- 报告误报
- 提供特殊 Package 结构样本
- 提出检测规则建议
- 提交代码改进

报告插件相关异常时，建议同时说明：

- MSFS 版本
- 插件版本
- 插件来源
- 是否经过修改
- 是否为干净安装
- AeroGuard 检测结果
- MSFS 中是否真的存在运行异常

---

## 📄 开源许可证

AeroGuard 采用 GNU General Public License v3.0
（GPL-3.0）发布。

你可以自由使用、研究、修改和重新分发 AeroGuard。

如果你修改 AeroGuard 或将其代码组成受 GPL 约束的派生/组合程序并对外分发，
则需要按照 GPL 的要求提供相应源代码并保留相同的自由软件权利。

详见仓库中的 `LICENSE` 文件。

---

## 免责声明

AeroGuard 是独立的社区项目。

本项目与 Microsoft、Asobo Studio 以及各第三方插件开发者不存在官方隶属或合作关系。

Microsoft Flight Simulator 及相关商标归其各自权利人所有。
