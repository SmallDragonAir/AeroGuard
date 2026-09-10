"""AeroGuard 轻量国际化（i18n）支持。

语言解析顺序（从高到低）：
1. 显式传入（--lang / set_language 调用）
2. 环境变量 AEROGUARD_LANG（如 en、zh）
3. 操作系统界面语言（简体/繁体中文 → zh，其余 → en）

用法：

    from i18n import tr, set_language, current_language

    set_language("en")
    tr("gui.button.scan")          # -> "Start scan"
    tr("issue.layout.missing")     # 无占位符
    tr("gui.status.scan_done", addons=282, issues=2)

目录键缺失时回退：优先英文，其次返回键名本身，
保证新代码不会因为漏配键而崩溃。
"""

import os
import re


#: language code -> {"key": (zh, en)} 之外，另有按 (key, lang) 的二维表：
#: 每条文案 = {"zh": ..., "en": ...}
_zh = {}
_en = {}


def _register(key, zh, en):
    _zh[key] = zh
    _en[key] = en


# --------------------------------------------------------------------------
# 通用 / GUI
# --------------------------------------------------------------------------
_register("app.name", "AeroGuard", "AeroGuard")
_register("app.subtitle", "本地、可解释的 MSFS Package 诊断与管理",
          "Local, explainable MSFS Package diagnostics & management")
_register("gui.window.title", "AeroGuard — MSFS 插件诊断与管理",
          "AeroGuard - MSFS addon diagnostics & management")
_register("gui.field.community", "Community", "Community")
_register("gui.lang.label", "语言", "Language")
_register("gui.lang.zh", "中文", "中文")
_register("gui.lang.en", "English", "English")
_register("gui.lang.busy",
          "任务运行中无法切换语言，请等待完成。",
          "Language cannot be switched while a task is running.")
_register("gui.lang.rescan_title", "切换结果语言", "Switch result language")
_register("gui.lang.rescan_text",
          "已载入的结果是用之前的语言生成的。是否立即重新扫描，"
          "让问题说明显示为新语言？",
          "Loaded results were generated in the previous language. "
          "Re-scan now so that messages appear in the new language?")
_register("gui.lang.declined_note",
          "已切换界面语言；已载入结果保持原语言，重新扫描后可显示新语言。",
          "UI language switched; loaded results keep the previous language "
          "until you re-scan.")
_register("gui.button.browse", "浏览…", "Browse...")
_register("gui.button.start_scan", "开始扫描", "Start scan")
_register("gui.button.export_json", "导出报告", "Export report")
_register("gui.prompt.choose_community", "选择 Community 文件夹",
          "Select the Community folder")
_register("gui.status.choose_first",
          "请选择 Community 路径后开始扫描。",
          "Choose a Community path, then start a scan.")
_register("gui.metric.addons", "插件", "Add-ons")
_register("gui.metric.issues", "问题", "Issues")
_register("gui.metric.errors", "错误", "Errors")
_register("gui.metric.warnings", "警告", "Warnings")
_register("gui.metric.resource_conflicts", "资源重叠", "Resource overlaps")
_register("gui.metric.airport_conflicts", "机场重复", "Airport duplicates")
_register("gui.metric.elapsed", "耗时 / 秒", "Elapsed (s)")

_register("gui.tab.issues", "问题", "Issues")
_register("gui.tab.conflicts", "冲突与依赖", "Conflicts & Dependencies")
_register("gui.tab.management", "插件管理", "Add-on Management")
_register("gui.tab.history", "历史与基线", "History & Baselines")
_register("gui.tab.scan_errors", "扫描异常", "Scan Errors")

_register("gui.head.severity", "等级", "Severity")
_register("gui.head.rule", "规则", "Rule")
_register("gui.head.package", "插件", "Add-on")
_register("gui.head.affected", "数量", "Count")
_register("gui.head.impact", "运行影响", "Runtime impact")
_register("gui.head.message", "说明", "Message")
_register("gui.head.type", "类型", "Type")
_register("gui.head.resource", "资源 / 代码", "Resource / code")
_register("gui.head.packages", "涉及插件", "Add-ons involved")
_register("gui.head.reason", "判断", "Reason")
_register("gui.head.status", "状态", "Status")
_register("gui.head.folder", "包目录", "Folder")
_register("gui.head.version", "版本", "Version")
_register("gui.head.title", "标题", "Title")
_register("gui.head.meta_error", "元数据异常", "Metadata error")
_register("gui.head.time", "记录时间", "Recorded at")
_register("gui.head.id", "快照 ID", "Snapshot ID")
_register("gui.head.label", "标签", "Label")
_register("gui.head.mode", "模式", "Mode")
_register("gui.head.addons", "插件", "Add-ons")
_register("gui.head.issues", "问题", "Issues")
_register("gui.head.conflicts", "资源重叠", "Overlaps")
_register("gui.head.error", "异常", "Error")
_register("gui.head.notes", "备注", "Notes")
_register("gui.search.label", "筛选：", "Filter:")
_register("gui.search.clear", "清除", "Clear")

_register("gui.action.refresh_inventory", "刷新清单", "Refresh list")
_register("gui.action.enable", "启用", "Enable")
_register("gui.action.disable", "禁用", "Disable")
_register("gui.action.quarantine", "隔离", "Quarantine")
_register("gui.action.restore", "恢复", "Restore")
_register("gui.action.save_profile", "保存 Profile", "Save Profile")
_register("gui.action.apply_profile", "应用 Profile", "Apply Profile")
_register("gui.action.install_zip", "安装 ZIP", "Install ZIP")
_register("gui.action.install_dir", "安装目录", "Install folder")
_register("gui.action.rollback_install", "回滚安装", "Rollback install")
_register("gui.action.verify", "检查选中插件", "Verify selected add-on")
_register("gui.action.refresh_history", "刷新历史", "Refresh history")
_register("gui.action.record_snapshot", "记录当前结果", "Record current result")
_register("gui.action.set_baseline", "设为基线", "Set as baseline")
_register("gui.action.compare_baseline", "与基线比较", "Compare with baseline")

_register("gui.no_scan_errors", "没有扫描异常。", "No scan errors.")
_register("gui.detail.issue", "检测详情", "Issue detail")
_register("gui.detail.addon", "插件详情", "Add-on detail")
_register("gui.detail.dependency_warnings", "依赖警告", "Dependency warnings")
_register("gui.detail.install_transaction", "安装事务", "Install transaction")
_register("gui.detail.verify", "单插件校验", "Single add-on check")
_register("gui.status.verifying", "正在校验 {package}…",
          "Verifying {package}...")
_register("gui.status.verify_done",
          "{package}：ERROR {error} / WARNING {warning} / INFO {info}",
          "{package}: ERROR {error} / WARNING {warning} / INFO {info}")
_register("gui.export.title", "导出 AeroGuard 报告（JSON / Markdown / HTML）",
          "Export AeroGuard report (JSON / Markdown / HTML)")
_register("gui.export.all_files", "所有文件", "All files")
_register("gui.export.markdown", "Markdown 报告", "Markdown report")
_register("gui.export.html", "HTML 报告", "HTML report")
_register("gui.status.report_saved", "报告已保存：{path}",
          "Report saved: {path}")

_register("gui.err.choose_community", "请先选择 Community 路径",
          "Choose a Community path first")
_register("gui.err.not_dir", "Community 路径不存在或不是目录：{path}",
          "Community path does not exist or is not a folder: {path}")
_register("gui.err.select_management_row",
          "请先在插件管理表格中选择一个包",
          "Select an add-on in the management table first")
_register("gui.err.only_disabled_enable",
          "只有禁用状态的包可以启用",
          "Only disabled add-ons can be enabled")
_register("gui.err.only_enabled_disable",
          "只有启用状态的包可以禁用",
          "Only enabled add-ons can be disabled")
_register("gui.err.only_quarantined_restore",
          "只有隔离状态的包可以恢复",
          "Only quarantined add-ons can be restored")
_register("gui.err.already_quarantined",
          "该包已经位于隔离区",
          "This add-on is already quarantined")
_register("gui.err.task_busy", "已有任务正在运行，请等待完成。",
          "A task is already running; please wait for it to finish.")
_register("gui.err.task_failed", "任务失败。", "Task failed.")
_register("gui.err.render_failed", "结果呈现失败。", "Failed to show result.")
_register("gui.err.need_scan_first", "请先完成一次扫描",
          "Run a scan first")
_register("gui.err.path_changed",
          "路径已改变，请先重新扫描当前 Community",
          "Path changed; re-scan the current Community first")
_register("gui.err.no_snapshot_selected", "请先选择一个历史快照",
          "Select a history snapshot first")
_register("gui.err.snapshot_unavailable", "所选历史快照不可用",
          "The selected history snapshot is unavailable")

_register("gui.status.scan_full", "正在执行完整扫描…", "Running full scan...")
_register("gui.status.scan_quick", "正在执行快速扫描…", "Running quick scan...")
_register("gui.status.scan_done",
          "扫描完成：{addons} 个插件，{issues} 条问题，耗时 {elapsed:.2f} 秒。"
          "双击表格行可查看完整数据。",
          "Scan done: {addons} add-ons, {issues} issues in {elapsed:.2f}s. "
          "Double-click a row to inspect full data.")
_register("gui.status.json_saved", "JSON 报告已保存：{path}",
          "JSON report saved: {path}")
_register("gui.status.refreshing_inventory", "正在刷新插件管理清单…",
          "Refreshing add-on management list...")
_register("gui.status.inventory_done",
          "管理清单：启用 {enabled}，禁用 {disabled}，隔离 {quarantined}，"
          "无效目录 {invalid}。",
          "Inventory: {enabled} enabled, {disabled} disabled, "
          "{quarantined} quarantined, {invalid} invalid.")
_register("gui.status.operation_prefix", "正在执行：{action} {package}…",
          "Running: {action} {package}...")
_register("gui.status.operation_done",
          "操作完成，事务 {tid}{suffix}。重启模拟器后生效。",
          "Done. Transaction {tid}{suffix}. Restart the simulator for "
          "changes to apply.")
_register("gui.status.dependency_warning_suffix", "；依赖警告 {n} 条",
          "; {n} dependency warning(s)")
_register("gui.status.reading_history", "正在读取扫描历史…",
          "Reading scan history...")
_register("gui.status.snapshot_saved", "快照已保存：{sid}",
          "Snapshot saved: {sid}")
_register("gui.status.record_snapshot", "正在保存紧凑扫描快照…",
          "Saving a compact scan snapshot...")
_register("gui.status.baseline_saved", "环境基线已保存：{name}",
          "Baseline saved: {name}")
_register("gui.status.set_baseline_running", "正在设置基线 {name}…",
          "Setting baseline {name}...")
_register("gui.status.compare_running", "正在与基线 {name} 比较…",
          "Comparing with baseline {name}...")
_register("gui.status.baseline_compare_done",
          "基线比较完成：{changes} 项变化，{warnings} 条兼容性提示。",
          "Baseline comparison done: {changes} change(s), "
          "{warnings} compatibility warning(s).")
_register("gui.status.profile_saved", "Profile 已保存：{path}",
          "Profile saved: {path}")
_register("gui.status.save_profile_running", "正在保存 Profile {name}…",
          "Saving Profile {name}...")
_register("gui.status.apply_profile_running", "正在应用 Profile {name}…",
          "Applying Profile {name}...")
_register("gui.status.profile_dry_run", "正在预演 Profile {name}…",
          "Dry-running Profile {name}...")
_register("gui.status.profile_applied_already",
          "Profile {name} 已处于目标状态。", "Profile {name} already applied.")
_register("gui.status.install_done",
          "安装完成，事务 {tid}。重启模拟器后生效。",
          "Install done. Transaction {tid}. Restart the simulator for "
          "changes to apply.")
_register("gui.status.install_running", "正在安装并保存可回滚备份…",
          "Installing and keeping a rollback backup...")
_register("gui.status.inspect_running", "正在暂存并检查安装源…",
          "Staging and inspecting the install source...")
_register("gui.dialog.install_check_title", "安装前检查", "Pre-install check")

_register("gui.dialog.record_history", "记录扫描历史", "Record scan history")
_register("gui.dialog.label_prompt", "可选标签：", "Optional label:")
_register("gui.dialog.set_baseline", "设置环境基线", "Set environment baseline")
_register("gui.dialog.baseline_name", "基线名称：", "Baseline name:")
_register("gui.dialog.compare_baseline", "比较环境基线",
          "Compare with environment baseline")
_register("gui.dialog.baseline_name2", "基线名称：", "Baseline name:")
_register("gui.dialog.save_profile", "保存 Profile", "Save Profile")
_register("gui.dialog.profile_name", "Profile 名称：", "Profile name:")
_register("gui.dialog.apply_profile", "应用 Profile", "Apply Profile")
_register("gui.dialog.profile_name2", "Profile 名称：", "Profile name:")
_register("gui.dialog.apply_profile_confirm",
          "Profile {name} 将移动 {moves} 个包，有 {warnings} 条提示。是否应用？",
          "Profile {name} will move {moves} add-on(s) with {warnings} "
          "warning(s). Apply?")
_register("gui.dialog.inspect_not_passed",
          "安装前检查未通过，Community 未发生变化。",
          "Pre-install check failed; Community was not changed.")
_register("gui.dialog.install_done_offer",
          "包：{packages}\n问题：{issues} 条{note}\n\n是否开始安装？",
          "Add-ons: {packages}\nIssues: {issues}{note}\n\nStart installation?")
_register("gui.dialog.executable_note",
          "\n检测到 {n} 个可执行文件；AeroGuard 只复制、不执行。",
          "\n{n} executable file(s) detected; AeroGuard only copies, "
          "never runs them.")
_register("gui.dialog.rollback_title", "回滚安装", "Rollback install")
_register("gui.dialog.rollback_prompt", "安装事务 ID：", "Install transaction ID:")
_register("gui.dialog.quarantine_reason_title", "隔离原因",
          "Quarantine reason")
_register("gui.dialog.quarantine_reason_prompt", "记录隔离原因：",
          "Reason for quarantine:")
_register("gui.dialog.quarantine_initial", "待排查冲突",
          "pending conflict review")
_register("gui.dialog.close_busy_title", "AeroGuard", "AeroGuard")
_register("gui.err.not_dir", "Community 路径不存在或不是目录：{path}",
          "Community path does not exist or is not a folder: {path}")
_register("gui.err.bad_mode", "不支持的扫描模式：{mode}",
          "Unsupported scan mode: {mode}")
_register("gui.status.history_count", "已读取 {n} 个扫描历史快照。",
          "Loaded {n} scan history snapshot(s).")
_register("gui.status.rollback_running", "正在回滚安装事务 {tid}…",
          "Rolling back install transaction {tid}...")
_register("gui.dialog.choose_zip", "选择插件 ZIP", "Select an add-on ZIP")
_register("gui.dialog.choose_dir", "选择插件目录或包集合目录",
          "Select an add-on folder or collection folder")
_register("gui.dialog.close_busy_text",
          "后台任务仍在运行，现在退出可能中断正在进行的操作。确定要退出吗？",
          "A background task is still running; quitting now may interrupt "
          "it. Quit anyway?")

_register("gui.row.type_resource", "资源", "Resource")
_register("gui.row.type_airport", "机场", "Airport")
_register("gui.row.type_cycle", "依赖环", "Dependency cycle")

# --------------------------------------------------------------------------
# analyzer 规则消息
# --------------------------------------------------------------------------
_register("issue.manifest.title", "manifest.json 缺少 title",
          "manifest.json is missing a title")
_register("issue.manifest.content_type", "manifest.json 缺少 content_type",
          "manifest.json is missing content_type")
_register("issue.manifest.version", "manifest.json 缺少 package_version",
          "manifest.json is missing package_version")
_register("issue.layout.missing", "缺少 layout.json", "layout.json is missing")
_register("issue.layout.invalid", "layout.json 无法解析：{error}",
          "layout.json could not be parsed: {error}")
_register("issue.layout.content_not_list",
          "layout.json 的 content 不是列表",
          "layout.json content is not a list")
_register("issue.layout.duplicate", "layout.json 中发现 {n} 个重复路径声明",
          "layout.json contains {n} duplicate path declaration(s)")
_register("issue.layout.invalid_entry", "layout.json 中发现 {n} 个无效条目",
          "layout.json contains {n} invalid entry/entries")
_register("issue.tree.incomplete",
          "有 {n} 个路径无法读取，文件检查不完整",
          "{n} path(s) could not be read; the file check is incomplete")
_register("issue.file.missing", "layout.json 声明的 {n} 个文件不存在",
          "{n} file(s) declared in layout.json do not exist")
_register("issue.file.size_mismatch",
          "发现 {n} 个文件大小与 layout.json 不一致",
          "{n} file(s) differ in size from layout.json")
_register("issue.file.unlisted", "发现 {n} 个文件未列入 layout.json",
          "{n} file(s) are not listed in layout.json")

# --------------------------------------------------------------------------
# classifier 分类理由
# --------------------------------------------------------------------------
_register("classify.docs.build_tool",
          "看起来属于说明文件、构建工具或打包辅助文件",
          "Looks like documentation, a build tool, or packaging helper")
_register("classify.docs.extension", "扩展名表明它可能是说明文档",
          "The extension suggests it is documentation")
_register("classify.docs.directory", "位于说明文档目录中",
          "Located in a documentation directory")
_register("classify.wasm.composite", "文件名表明它与 WASM 模块相关",
          "The filename suggests it belongs to a WASM module")
_register("classify.ext.runtime", "{extension} 文件可能参与模拟器或插件运行",
          "{extension} files may be used at runtime by the simulator or add-on")
_register("classify.dir.runtime", "文件位于插件的运行时结构目录中",
          "Located in a runtime structure directory of the add-on")
_register("classify.config.runtime",
          "文件位于配置目录中，可能参与插件运行",
          "Located in a configuration directory; may be used at runtime")
_register("classify.unknown", "目前没有足够信息判断该文件是否影响运行",
          "Not enough information to tell whether this affects runtime")

# --------------------------------------------------------------------------
# noise 降噪理由
# --------------------------------------------------------------------------
_register("noise.crlf_reason",
          "代表样本的大小差均精确符合 CRLF 转 LF 的换行规范化特征",
          "Representative samples all match CRLF-to-LF line-ending "
          "normalization exactly")

# --------------------------------------------------------------------------
# relationships 理由
# --------------------------------------------------------------------------
_register("rel.intentional",
          "检测到声明依赖或显式全局覆盖关系",
          "Declared dependency or explicit global override detected")
_register("rel.vfs.diff_size",
          "运行时 VFS 路径重叠且声明大小不同",
          "Runtime VFS paths overlap with different declared sizes")
_register("rel.vfs.same_size",
          "运行时 VFS 路径重叠且声明大小相同，仍需哈希或实机确认",
          "Runtime VFS paths overlap with identical declared sizes; "
          "hash or in-sim confirmation still needed")
_register("rel.other.overlap",
          "路径重叠，但当前静态信息不足以确定实际运行影响",
          "Paths overlap, but static information cannot determine the "
          "actual runtime impact")
_register("rel.airport.patch",
          "同一机场包含 Patch 顺序包，可能是有意覆盖",
          "Same airport has a patch-order package; likely intentional override")
_register("rel.airport.dup",
          "多个 Package 以至少两个独立静态信号指向同一机场",
          "Multiple packages point to the same airport via at least two "
          "independent static signals")
_register("rel.dep.outside_scope",
          "当前扫描根目录中未找到；可能位于 Official 或其他包源",
          "Not found under the current scan root; may live in Official or "
          "another source")
_register("rel.dep.invalid_list", "manifest dependencies 不是列表",
          "manifest dependencies is not a list")
_register("rel.dep.invalid_entry", "依赖条目不是 JSON 对象",
          "dependency entry is not a JSON object")
_register("rel.dep.invalid_name", "依赖名称缺失或类型无效",
          "dependency name is missing or invalid")
_register("rel.cycle.exists", "当前扫描根目录内存在循环依赖",
          "A circular dependency exists within the current scan root")


# --------------------------------------------------------------------------
# CLI 前缀 / 文本报告 / 启动器
# --------------------------------------------------------------------------
_register("cli.manage_failed", "管理操作失败：{error}",
          "Management failed: {error}")
_register("cli.history_failed", "历史操作失败：{error}",
          "History failed: {error}")
_register("cli.compare_summary",
          "基线比较 {name}: 共 {changes} 项变化（{detail}）；兼容性提示 {warnings} 条",
          "Baseline comparison {name}: {changes} change(s) ({detail}); "
          "{warnings} compatibility warning(s)")
_register("cli.compare_no_diff", "无差异", "no changes")
_register("cli.count_items", "{n} 项", "{n} item(s)")

_register("report.community_path", "Community 路径：{path}",
          "Community path: {path}")
_register("report.scan_mode", "扫描模式：{mode}", "Scan mode: {mode}")
_register("report.mode_full", "完整扫描", "full scan")
_register("report.mode_quick", "快速扫描", "quick scan")
_register("report.addons", "插件总数：{n}", "Add-ons: {n}")
_register("report.scan_errors", "扫描异常：{n}", "Scan errors: {n}")
_register("report.issues", "检测问题：{n}", "Findings: {n}")
_register("report.downgraded", "自动降噪：{n} 条问题 / {affected} 个项目",
          "Noise-reduced: {n} finding(s) / {affected} item(s)")
_register("report.resource_conflicts", "资源冲突候选：{n}",
          "Resource-conflict candidates: {n}")
_register("report.airport_conflicts", "机场重复候选：{n}",
          "Airport-duplicate candidates: {n}")
_register("report.declared_dependencies", "声明依赖：{n}",
          "Declared dependencies: {n}")
_register("report.by_rule", "\n按规则：", "\nBy rule:")
_register("report.rule_line", "  {rule}: {packages} 个插件{affected}",
          "  {rule}: {packages} add-on(s){affected}")
_register("report.rule_affected", " / {n} 个项目", " / {n} item(s)")
_register("report.top_issues", "\n=== 异常数量 TOP 10 ===",
          "\n=== Top 10 by finding count ===")
_register("report.by_package", "\n=== 按插件汇总 ===",
          "\n=== Summary by add-on ===")
_register("report.issue_line", "  [{severity}] {rule} - {message}{suffix}",
          "  [{severity}] {rule} - {message}{suffix}")
_register("report.issue_suffix", "（影响 {n} 项）", " ({n} item(s))")
_register("report.downgrade_note",
          "    已降级：{reason}（抽样 {n} 项）",
          "    Downgraded: {reason} (sampled {n})")
_register("report.missing_detail", "\n=== 缺失文件详情 ===",
          "\n=== Missing-file details ===")
_register("report.missing_for", "\n插件：{package}（{n} 项缺失）",
          "\nAdd-on: {package} ({n} missing)")
_register("report.missing_item", "  缺失：{path}", "  missing: {path}")
_register("report.missing_more", "  … 另有 {n} 项未显示，可用 --json 查看完整明细",
          "  ... {n} more not shown; use --json for full details")
_register("report.review_top", "\n=== 重点复核 TOP 10 ===",
          "\n=== Priority review TOP 10 ===")
_register("report.review_line",
          "{package} | ERROR {error} | WARNING {warning} | INFO {info} | 影响 {affected} 项",
          "{package} | ERROR {error} | WARNING {warning} | INFO {info} | "
          "{affected} item(s)")
_register("report.missing_review", "\n=== 缺失文件重点复核 ===",
          "\n=== Missing files by impact ===")
_register("report.missing_review_line", "{package} | {impact} | 影响 {n} 项",
          "{package} | {impact} | {n} item(s)")
_register("report.rel_conflicts", "\n=== Package 资源冲突 TOP 10 ===",
          "\n=== Package resource conflicts TOP 10 ===")
_register("report.rel_conflict_line", "[{severity}] {path} | {packages}",
          "[{severity}] {path} | {packages}")
_register("report.judgement", "  判断：{reason}", "  Reason: {reason}")
_register("report.default_priority", "  默认优先：{package}（{basis}）",
          "  Default priority: {package} ({basis})")
_register("report.airports", "\n=== 机场重复 / 覆盖候选 ===",
          "\n=== Airport duplicates / override candidates ===")
_register("report.airports_none", "未发现高置信度的 Community 内机场重复候选。",
          "No high-confidence airport-duplicate candidates found.")
_register("report.deps", "\n=== 插件依赖分析 ===",
          "\n=== Add-on dependency analysis ===")
_register("report.deps_resolved", "当前根目录内已解析：{n}",
          "Resolved in the scan root: {n}")
_register("report.deps_outside", "扫描范围外未解析：{n}",
          "Unresolved (outside scan scope): {n}")
_register("report.deps_invalid", "无效依赖条目：{n}", "Invalid dependency entries: {n}")
_register("report.deps_cycles", "依赖环：{n}", "Dependency cycles: {n}")
_register("report.scan_error_detail", "\n=== 扫描错误 ===", "\n=== Scan errors ===")
_register("report.scan_error_for", "\n插件：{package}", "\nAdd-on: {package}")
_register("report.scan_error_path", "  路径：{path}", "  path: {path}")
_register("report.scan_error_text", "  错误：{error}", "  error: {error}")
_register("report.performance", "\n=== 性能统计 ===", "\n=== Performance ===")
_register("report.perf_line", "{label}：{value} 秒", "{label}: {value} s")
_register("report.perf_total", "总耗时：{value} 秒", "Total: {value} s")
_register("report.perf_noise_label", "降噪规则", "Noise filter")
_register("report.perf_relationships_label", "关系分析",
          "Relationship analysis")
_register("report.perf_internal", "  Analyzer 内部：", "  Analyzer internals:")
_register("report.perf_layout", "    Layout 解析：{value} 秒",
          "    Layout parsing: {value} s")
_register("report.perf_declared", "    声明文件检查：{value} 秒",
          "    Declared-file checks: {value} s")
_register("report.perf_tree", "    文件树遍历：{value} 秒",
          "    File-tree walk: {value} s")
_register("report.perf_tree_parallel",
          "    文件树遍历（线程累计 / 墙钟）：{total} 秒 / {wall} 秒",
          "    File-tree walk (thread total / wall): {total} s / {wall} s")
_register("report.perf_hotspots", "  文件树遍历热点 TOP 5：",
          "  File-tree hot spots TOP 5:")
_register("report.perf_hotspot_line", "    {package}：{seconds:.2f} 秒 / {files} 个文件",
          "    {package}: {seconds:.2f} s / {files} file(s)")
_register("report.json_saved", "\nJSON 报告已保存：{path}",
          "\nJSON report saved: {path}")
_register("report.markdown_saved", "\nMarkdown 报告已保存：{path}",
          "\nMarkdown report saved: {path}")
_register("report.html_saved", "\nHTML 报告已保存：{path}",
          "\nHTML report saved: {path}")
_register("report.path_missing", "路径不存在，请检查输入的路径是否正确。",
          "Path does not exist; please check the entered path.")
_register("report.path_not_dir", "输入的路径不是一个目录。",
          "The entered path is not a folder.")
_register("report.prompt_path", "请输入 MSFS Community 文件夹路径：",
          "Enter the MSFS Community folder path: ")
_register("report.prompt_mode", "扫描模式[1=快速扫描/2=完整扫描]：",
          "Scan mode [1=quick / 2=full]: ")
_register("report.eof_hint",
          "没有可用的交互输入（标准输入已关闭）；请使用非交互参数：\n"
          "  python main.py <Community 路径> --mode quick|full [--json]",
          "No interactive input available (stdin is closed); use "
          "non-interactive arguments instead:\n"
          "  python main.py <Community path> --mode quick|full [--json]")

_register("launcher.usage", """AeroGuard —— MSFS 插件诊断与管理（单文件版）
用法：
  AeroGuard.exe                        启动桌面界面（无参数，双击）
  AeroGuard.exe gui                    同上
  AeroGuard.exe scan <Community> [--mode quick|full] [--json] [--no-relationships]
  AeroGuard.exe manage <Community> <子命令> ...
  AeroGuard.exe history <Community> <子命令> ...

提示：也可以直接运行 python main.py / manage.py / history_cli.py。""",
          """AeroGuard - MSFS add-on diagnostics & management (single file)

Usage:
  AeroGuard.exe                        open the desktop UI (no arguments / double-click)
  AeroGuard.exe gui                    same as above
  AeroGuard.exe scan <Community> [--mode quick|full] [--json] [--no-relationships]
  AeroGuard.exe manage <Community> <command> ...
  AeroGuard.exe history <Community> <command> ...

Tip: you can also run python main.py / manage.py / history_cli.py directly.""")


_register("help.main.description",
          "AeroGuard —— MSFS 插件一致性诊断工具（开发版 CLI）。",
          "AeroGuard - MSFS package consistency diagnostics (dev CLI).")
_register("help.main.community",
          "MSFS Community 文件夹路径（缺省时交互输入）",
          "Path to the MSFS Community folder (prompted if omitted)")
_register("help.main.mode",
          "扫描模式：quick=快速扫描，full=完整扫描（缺省时交互选择）",
          "Scan mode: quick or full (prompted if omitted)")
_register("help.main.json",
          "同时把完整报告写入 JSON 文件；不写 PATH 时自动保存到 reports/ 目录",
          "Also write the full report to a JSON file; without PATH it is "
          "saved under reports/")
_register("help.main.no_relationships",
          "跳过跨 Package 冲突/依赖分析（快速扫描可明显提速）",
          "Skip cross-package conflict/dependency analysis (faster quick scans)")
_register("help.main.state_dir",
          "知识状态目录；缺省使用 Community 同级的 .aeroguard",
          "Knowledge state directory; defaults to .aeroguard next to the "
          "Community")
_register("help.main.markdown",
          "同时导出 Markdown 报告（含逐条处理建议）；不写 PATH 时保存到 reports/",
          "Also export a Markdown report with per-rule guidance; without "
          "PATH it is saved under reports/")
_register("help.main.html",
          "同时导出 HTML 报告（含逐条处理建议）；不写 PATH 时保存到 reports/",
          "Also export an HTML report with per-rule guidance; without PATH "
          "it is saved under reports/")
_register("help.main.epilog",
          "示例：\n"
          "  python main.py\n"
          "  python main.py D:\\MSFS2024_DATA\\Community --mode full\n"
          "  python main.py <路径> --mode quick --json\n",
          "Examples:\n"
          "  python main.py\n"
          "  python main.py D:\\MSFS2024_DATA\\Community --mode full\n"
          "  python main.py <path> --mode quick --json\n")

_register("help.manage.description",
          "AeroGuard 插件管理（只操作指定 Community 与管理状态目录）。",
          "AeroGuard add-on management (operates only on the given Community "
          "and state directory).")
_register("help.manage.community", "Community 或 Community2024 路径",
          "Path to Community or Community2024")
_register("help.manage.state_dir",
          "管理状态目录；默认使用 Community 同级的 .aeroguard",
          "Management state directory; defaults to .aeroguard next to the "
          "Community")
_register("help.manage.inventory", "列出启用、禁用与隔离包",
          "List enabled, disabled, and quarantined packages")
_register("help.manage.versions", "列出当前与已归档版本",
          "List current and archived versions")
_register("help.manage.disable", "禁用一个包", "Disable a package")
_register("help.manage.enable", "启用一个包", "Enable a package")
_register("help.manage.restore", "从隔离区恢复一个包",
          "Restore a package from quarantine")
_register("help.manage.quarantine", "把包移入安全隔离区",
          "Move a package into the safe quarantine area")
_register("help.manage.profile_save", "保存当前启用状态",
          "Save the current enabled/disabled states")
_register("help.manage.profile_apply", "应用已保存的 Profile",
          "Apply a saved Profile")
_register("help.manage.check", "只读检查目录或 ZIP 安装源",
          "Read-only inspection of a folder or ZIP install source")
_register("help.manage.install", "检查后安装并保留旧版本",
          "Inspect, install, and keep the previous version")
_register("help.manage.rollback", "回滚一个已提交的安装事务",
          "Roll back a committed install transaction")
_register("help.manage.verify", "只读校验单个已安装插件包",
          "Read-only consistency check of a single installed add-on")
_register("help.manage.note_list", "列出本地已知结论记录（已知异常数据库雏形）",
          "List local knowledge records (seed of a known-issue database)")
_register("help.manage.note_add", "记录一条针对插件/规则的本地已知结论",
          "Record a local knowledge note for an add-on / rule")
_register("help.manage.note_text", "结论文本", "Note text")
_register("help.manage.note_rule",
          "可选的规则 ID（如 LAYOUT_FILE_SIZE_MISMATCH）",
          "Optional rule ID (e.g. LAYOUT_FILE_SIZE_MISMATCH)")
_register("help.manage.note_remove", "删除一条本地已知结论",
          "Delete a local knowledge record")
_register("help.manage.override_list", "列出本地规则覆盖（忽略 / 降级）",
          "List local rule overrides (ignore / downgrade)")
_register("help.manage.override_add", "为某插件的某条规则添加忽略或降级",
          "Add an ignore/downgrade override for a rule of an add-on")
_register("help.manage.override_rule", "规则 ID，如 LAYOUT_FILE_MISSING",
          "Rule ID, e.g. LAYOUT_FILE_MISSING")
_register("help.manage.override_remove", "删除一条规则覆盖",
          "Delete a rule override")

_register("help.history.description",
          "记录紧凑扫描历史并与命名环境基线比较。",
          "Record compact scan history and compare against named baselines.")
_register("help.history.record", "扫描并保存紧凑快照",
          "Scan and save a compact snapshot")
_register("help.history.list", "列出历史快照", "List history snapshots")
_register("help.history.baseline_set", "把历史快照设为命名基线",
          "Set a history snapshot as a named baseline")
_register("help.history.compare", "重新扫描并与命名基线比较",
          "Re-scan and compare against a named baseline")

_register("help.gui.description", "启动 AeroGuard 原生桌面界面。",
          "Launch the native AeroGuard desktop UI.")
_register("help.gui.lang",
          "界面语言（缺省按系统语言；也可用环境变量 AEROGUARD_LANG）",
          "UI language (defaults to the OS language; AEROGUARD_LANG also "
          "works)")


def resolve_language(override=None):
    """按优先级解析语言代码，返回 'zh' 或 'en'。"""
    if override:
        code = str(override).strip().lower()
    else:
        code = os.environ.get("AEROGUARD_LANG", "").strip().lower()
    if code.startswith("zh"):
        return "zh"
    if code.startswith("en"):
        return "en"
    if code:
        return "en" if "en" in code else "zh"
    # 操作系统界面语言
    try:
        if os.name == "nt":
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = lang_id & 0x3FF
            if primary == 0x04:  # LANG_CHINESE
                return "zh"
    except Exception:
        pass
    try:
        import locale

        language_code = locale.getdefaultlocale()[0] or ""
    except Exception:
        language_code = ""
    return "zh" if language_code.lower().startswith("zh") else "en"


_language = None


def set_language(override):
    """显式设置语言：'zh' / 'en'（也接受 'zh-CN'、'en-US' 等）。"""
    global _language
    _language = resolve_language(override)


def current_language():
    global _language
    if _language is None:
        _language = resolve_language()
    return _language


def tr(key, **kwargs):
    """按当前语言取文案；支持 {占位符} 格式化。"""
    language = current_language()
    table = _zh if language == "zh" else _en
    text = table.get(key)
    if text is None:
        text = _zh.get(key) or _en.get(key) or key
    if kwargs:
        return text.format(**kwargs)
    return text


# --------------------------------------------------------------------------
# 运行期消息的边界本地化
#
# 管理 / 历史 / 结论 / 覆盖等模块的异常与警告文案以中文模板产生；
# 为避免在领域模块里散落 i18n 调用，这里集中维护"中文模板 → 英文模板"
# 的映射，并在显示边界（GUI 弹窗、CLI 前缀、JSON 详情）调用
# localize_text / localize_document 完成转换。仅英文语言生效。
# --------------------------------------------------------------------------
_MESSAGE_TEMPLATES = (
    # --- 通用标签型 ---
    (r"(?P<label>.+)必须是字符串", "{label} must be a string"),
    (r"(?P<label>.+)不能为空", "{label} must not be empty"),
    (r"(?P<label>.+)不能超过 128 个字符",
     "{label} must not exceed 128 characters"),
    (r"(?P<label>.+)包含 Windows 路径非法字符",
     "{label} contains characters that are invalid in Windows paths"),
    (r"(?P<label>.+)包含控制字符", "{label} contains control characters"),
    (r"(?P<label>.+)不能以空格或句点结尾",
     "{label} must not end with a space or period"),
    (r"(?P<label>.+)不是安全文件名", "{label} is not a safe file name"),
    (r"(?P<label>.+)无法读取：(?P<error>.+)", "Failed to read {label}: {error}"),
    (r"(?P<label>.+)顶层必须是 JSON 对象",
     "{label} must be a JSON object"),
    (r"(?P<label>.+)不是有效的 JSON：(?P<error>.+)",
     "{label} is not valid JSON: {error}"),
    # --- 路径 / 状态目录 ---
    (r"Community 路径不存在或不是目录：(?P<path>.+)",
     "Community path does not exist or is not a folder: {path}"),
    (r"无法检查路径：(?P<path>.+)：(?P<error>.+)",
     "Cannot inspect path {path}: {error}"),
    (r"安装源包含链接或重解析点：(?P<path>.+)",
     "Install source contains a link or reparse point: {path}"),
    (r"拒绝清理非暂存目录：(?P<path>.+)",
     "Refusing to clean a non-staging directory: {path}"),
    (r"管理状态目录必须位于 Community 目录之外",
     "The management state directory must be outside the Community folder"),
    (r"状态目录必须位于 Community 之外",
     "The state directory must be outside the Community"),
    (r"历史状态目录必须位于 Community 之外",
     "The history state directory must be outside the Community"),
    # --- ZIP 安全校验 ---
    (r"ZIP 条目过多：(?P<n>\d+)，上限 (?P<limit>\d+)",
     "Too many ZIP entries: {n} (limit {limit})"),
    (r"ZIP 包含不安全路径：(?P<name>.+)",
     "ZIP contains an unsafe path: {name}"),
    (r"ZIP 包含 Windows 非法路径：(?P<name>.+)",
     "ZIP contains a Windows-invalid path: {name}"),
    (r"ZIP 包含加密条目：(?P<name>.+)",
     "ZIP contains an encrypted entry: {name}"),
    (r"ZIP 包含符号链接：(?P<name>.+)",
     "ZIP contains a symbolic link: {name}"),
    (r"ZIP 包含重复路径：(?P<name>.+)",
     "ZIP contains a duplicate path: {name}"),
    (r"ZIP 解压后总大小超过 100 GiB 安全上限",
     "ZIP uncompressed size exceeds the 100 GiB safety limit"),
    (r"ZIP 无法解析：(?P<error>.+)", "ZIP could not be parsed: {error}"),
    # --- 安装源 ---
    (r"安装源必须是包目录、包集合目录或 ZIP 文件",
     "Install source must be a package folder, a collection folder, "
     "or a ZIP file"),
    (r"安装源中未找到同时包含 manifest\.json 与 layout\.json 的包目录",
     "No package folder containing both manifest.json and layout.json "
     "was found in the install source"),
    (r"ZIP 中未找到同时包含 manifest\.json 与 layout\.json 的包目录",
     "No package folder containing both manifest.json and layout.json "
     "was found in the ZIP"),
    (r"安装源包含重复包目录名：(?P<name>.+)",
     "Install source contains a duplicate package folder name: {name}"),
    (r"(?P<name>.+)/layout\.json 的 content 不是列表",
     "{name}/layout.json content is not a list"),
    # --- 包清单 / 管理操作 ---
    (r"发现多个大小写等价的包目录：(?P<name>.+)",
     "Multiple case-equivalent package folders found: {name}"),
    (r"目标已存在，拒绝覆盖：(?P<path>.+)",
     "Destination already exists; refusing to overwrite: {path}"),
    (r"未找到包：(?P<name>.+)", "Package not found: {name}"),
    (r"目标位置已有同名包：(?P<path>.+)",
     "Destination already has a package with the same name: {path}"),
    (r"未找到可隔离的包：(?P<name>.+)",
     "No package available to quarantine: {name}"),
    (r"隔离区已有同名包：(?P<name>.+)",
     "The quarantine area already has a package with the same name: {name}"),
    (r"隔离记录已存在：(?P<path>.+)",
     "Quarantine record already exists: {path}"),
    (r"隔离区未找到包：(?P<name>.+)",
     "Package not found in the quarantine area: {name}"),
    (r"隔离记录中的 previous_status 无效",
     "The quarantine record has an invalid previous_status"),
    (r"恢复位置已有同名包：(?P<name>.+)",
     "The restore destination already has a package with the same name: "
     "{name}"),
    (r"存在跨位置同名包，无法保存确定性 Profile",
     "A package name exists in multiple locations; cannot save a "
     "deterministic Profile"),
    (r"Profile 已存在：(?P<path>.+)；使用 --replace 显式更新",
     "Profile already exists: {path}; use --replace to update explicitly"),
    (r"Profile packages 必须是 JSON 对象",
     "Profile packages must be a JSON object"),
    (r"Profile 中 (?P<name>.+) 的状态无效",
     "Profile has an invalid state for {name}"),
    (r"包同时存在于启用和禁用位置：(?P<name>.+)",
     "Package exists in both enabled and disabled locations: {name}"),
    (r"Profile 目标已存在：(?P<path>.+)",
     "Profile destination already exists: {path}"),
    (r"安装前检查未通过，未修改 Community",
     "Pre-install check failed; the Community was not modified"),
    (r"禁用区已有同名包：(?P<name>.+)",
     "The disabled area already has a package with the same name: {name}"),
    (r"Community 中已有同名非目录项：(?P<path>.+)",
     "The Community already contains a non-folder item with the same "
     "name: {path}"),
    # --- 回滚 ---
    (r"指定事务不是安装事务",
     "The given transaction is not an install transaction"),
    (r"安装事务当前状态不可回滚：(?P<status>.+)",
     "The install transaction cannot be rolled back in its current "
     "state: {status}"),
    (r"安装事务属于另一个 Community 路径",
     "The install transaction belongs to a different Community path"),
    (r"安装事务没有可回滚的包",
     "The install transaction has no packages to roll back"),
    (r"当前 Community 中未找到已安装包：(?P<name>.+)",
     "Installed package not found in the current Community: {name}"),
    (r"包 (?P<name>.+) 的 manifest/layout 在安装后已变化，拒绝覆盖",
     "manifest/layout of {name} changed after installation; refusing to "
     "overwrite"),
    (r"安装事务中的备份路径无效：(?P<path>.+)",
     "Invalid backup path in the install transaction: {path}"),
    (r"原版本备份不存在：(?P<path>.+)",
     "The previous-version backup does not exist: {path}"),
    (r"回滚保留目录已存在：(?P<path>.+)",
     "The rollback retention directory already exists: {path}"),
    # --- 依赖 / Profile 警告 ---
    (r"启用包声明依赖即将离开 Community 的包",
     "An enabled package declares a dependency on a package that is "
     "about to leave the Community"),
    (r"Profile 中的包当前未安装",
     "The package in this Profile is not currently installed"),
    # --- 单插件校验 ---
    (r"插件名不能为空", "Package name must not be empty"),
    (r"未找到插件：(?P<name>.+)", "Add-on not found: {name}"),
    (r"缺少 manifest\.json：(?P<name>.+)",
     "manifest.json is missing: {name}"),
    (r"插件 manifest\.json 无法解析：(?P<error>.+)",
     "Failed to parse the add-on manifest.json: {error}"),
    (r"插件 manifest\.json 顶层必须是 JSON 对象",
     "The add-on manifest.json must be a JSON object"),
    # --- 历史 / 基线 ---
    (r"报告必须是 JSON 对象", "The report must be a JSON object"),
    (r"基线和当前快照必须是 JSON 对象",
     "The baseline and the current snapshot must be JSON objects"),
    (r"扫描模式不同，文件一致性问题变化不可直接比较",
     "Scan modes differ; file-consistency changes cannot be compared "
     "directly"),
    (r"Community 路径不同，结果可能属于不同环境",
     "Community paths differ; results may belong to different "
     "environments"),
    (r"基线已存在：(?P<path>.+)；使用 --replace 显式更新",
     "Baseline already exists: {path}; use --replace to update explicitly"),
    (r"没有可用扫描快照，请先执行 record",
     "No scan snapshot available; run record first"),
    # --- 结论记录 ---
    (r"包名无效：(?P<name>.+)", "Invalid package name: {name}"),
    (r"结论记录文件中的 notes 必须是列表",
     "notes in the knowledge-record file must be a list"),
    (r"结论文本不能为空", "Note text must not be empty"),
    (r"结论文本过长（(?P<n>\d+) > (?P<limit>\d+)）",
     "Note text is too long ({n} > {limit})"),
    (r"rule_id 无效或过长", "rule_id is invalid or too long"),
    (r"note id 无效", "Invalid note id"),
    (r"未找到结论记录：(?P<id>.+)", "Knowledge record not found: {id}"),
    # --- 规则覆盖 ---
    (r"rule_id 缺失或过长", "rule_id is missing or too long"),
    (r"覆盖记录文件中的 overrides 必须是列表",
     "overrides in the override-record file must be a list"),
    (r"action 必须是其中之一：(?P<actions>.+)",
     "action must be one of: {actions}"),
    (r"reason 无效或过长", "reason is invalid or too long"),
    (r"同一 \(包, 规则\) 已有覆盖：(?P<package>.+) / (?P<rule>.+)",
     "An override already exists for (package, rule): {package} / {rule}"),
    (r"override id 无效", "Invalid override id"),
    (r"未找到覆盖记录：(?P<id>.+)", "Override record not found: {id}"),
)


def localize_text(text):
    """把运行期中文消息模板转换为当前语言；未命中时原样返回。"""
    if current_language() != "en" or not isinstance(text, str):
        return text
    for pattern, template in _MESSAGE_TEMPLATES:
        match = re.fullmatch(pattern, text)
        if match is not None:
            return template.format(**match.groupdict())
    return text


def localize_document(value):
    """递归本地化文档中的字符串（用于详情窗口 / JSON 警告列表）。"""
    if current_language() != "en":
        return value
    if isinstance(value, str):
        return localize_text(value)
    if isinstance(value, list):
        return [localize_document(item) for item in value]
    if isinstance(value, dict):
        return {
            key: localize_document(item)
            for key, item in value.items()
        }
    return value
