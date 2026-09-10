"""把 AeroGuard 报告导出为 Markdown / HTML，并附逐条处理建议。

输入是 report.build_report 生成的报告文档；输出适合贴论坛、发给插件作者
或本地留档。除数据本身外，还按规则给出"含义 + 建议处理步骤"，并统一
强调只读前提与安全操作（先备份、不要直接删除、确认运行期生成后再标注）。
"""

import html
from datetime import datetime, timezone

from i18n import current_language, tr


#: 每条规则的处理指导（zh / en）
RULE_GUIDANCE = {
    "MANIFEST_MISSING_TITLE": {
        "zh": ("缺少 title", "manifest.json 没有 title 字段。",
               ["补全 manifest.json 的 title（不影响运行，但列表/工具显示会异常）。"]),
        "en": ("Missing title", "manifest.json has no title field.",
               ["Add a title to manifest.json (harmless at runtime, but "
                "listings/tools may display oddly)."]),
    },
    "MANIFEST_MISSING_CONTENT_TYPE": {
        "zh": ("缺少 content_type", "manifest.json 没有 content_type。",
               ["补全 content_type，MSFS 依赖它判断包类型。"]),
        "en": ("Missing content_type", "manifest.json has no content_type.",
               ["Add content_type; MSFS uses it to classify the package."]),
    },
    "MANIFEST_MISSING_VERSION": {
        "zh": ("缺少 package_version", "manifest.json 没有版本字段。",
               ["补全 package_version，便于版本管理与更新比对。"]),
        "en": ("Missing package_version",
               "manifest.json has no version field.",
               ["Add package_version for version management and updates."]),
    },
    "LAYOUT_MISSING": {
        "zh": ("缺少 layout.json", "包目录中没有 layout.json。",
               ["用 MSFSLayoutGenerator 生成 layout.json，或从原始发布包重新安装。",
                "缺少 layout.json 时 MSFS 通常无法挂载该包。"]),
        "en": ("layout.json is missing",
               "The package folder has no layout.json.",
               ["Generate layout.json with MSFSLayoutGenerator, or reinstall "
                "from the original release.",
                "MSFS usually cannot mount a package without layout.json."]),
    },
    "LAYOUT_INVALID": {
        "zh": ("layout.json 无法解析", "layout.json 存在但不是合法 JSON。",
               ["从原始发布包恢复，或用 MSFSLayoutGenerator 重新生成。",
                "不建议手工修补语法错误。"]),
        "en": ("layout.json cannot be parsed",
               "layout.json exists but is not valid JSON.",
               ["Restore it from the original release or regenerate it with "
                "MSFSLayoutGenerator.", "Manual syntax fixes are not advised."]),
    },
    "LAYOUT_INVALID_ENTRY": {
        "zh": ("无效 Layout 条目", "条目缺少 path，或 size 不是非负整数。",
               ["用 MSFSLayoutGenerator 重新生成 layout.json，或修正对应条目。"]),
        "en": ("Invalid Layout entries",
               "An entry lacks path, or size is not a non-negative integer.",
               ["Regenerate layout.json with MSFSLayoutGenerator, or fix the "
                "offending entry."]),
    },
    "LAYOUT_DUPLICATE_PATH": {
        "zh": ("重复路径声明", "同一路径在 layout.json 中出现多次。",
               ["重新生成 layout.json 以去重。",
                "重复条目可能让加载顺序变得不确定。"]),
        "en": ("Duplicate path declarations",
               "The same path appears multiple times in layout.json.",
               ["Regenerate layout.json to remove duplicates.",
                "Duplicate entries can make load order ambiguous."]),
    },
    "FILE_TREE_SCAN_INCOMPLETE": {
        "zh": ("扫描不完整", "部分文件/目录无法读取（权限、占用或损坏链接）。",
               ["确认没有程序占用该目录，必要时以更高权限重新扫描。",
                "此类包的文件检查结果可能不完整，缺失文件不会被误报。"]),
        "en": ("Scan incomplete",
               "Some files/folders could not be read (permissions, locks, or "
               "broken links).",
               ["Make sure nothing is locking the folder; re-scan with higher "
                "privileges if needed.",
                "File checks for this add-on may be incomplete; missing files "
                "are not falsely reported."]),
    },
    "LAYOUT_FILE_MISSING": {
        "zh": ("声明文件缺失", "layout.json 声明的文件在实际目录中不存在。",
               ["常见原因：安装不完整、更新覆盖不完整，或文件在运行期生成。",
                "先备份，再从原始发布包重新安装该插件。",
                "若确认是运行期生成（如自更新数据库），可用 "
                "`manage note-add` / `override-add --action ignore` 标记，"
                "避免后续重复报告。"]),
        "en": ("Declared files missing",
               "Files declared in layout.json do not exist on disk.",
               ["Common causes: incomplete install, partial update, or files "
                "generated at runtime.",
                "Back up first, then reinstall the add-on from its original "
                "release.",
                "If the files are generated at runtime (e.g. self-updating "
                "data), mark them with `manage note-add` / "
                "`override-add --action ignore` to stop repeat reports."]),
    },
    "LAYOUT_FILE_SIZE_MISMATCH": {
        "zh": ("文件大小不一致", "实际文件大小与 layout.json 声明不同。",
               ["常见于运行期自更新、CRLF→LF 换行规范化或打包后被修改。",
                "若模拟器内一切正常，可用 `manage note-add` 记录原因；",
                "若出现加载异常，则从原始发布包重新安装。"]),
        "en": ("File size mismatches",
               "Actual file sizes differ from layout.json.",
               ["Common with runtime self-updates, CRLF/LF normalization, or "
                "post-packaging edits.",
                "If the simulator behaves normally, record it with "
                "`manage note-add`.",
                "If you see loading problems, reinstall from the original "
                "release."]),
    },
    "LAYOUT_UNLISTED_FILE": {
        "zh": ("未登记文件", "目录中存在未写入 layout.json 的文件。",
               ["多为打包工具残留、日志或运行期产物。",
                "若属于插件内容，用 MSFSLayoutGenerator 重新生成 layout.json；",
                "若确认无用，再考虑清理（先备份）。"]),
        "en": ("Unlisted files",
               "Files exist on disk but are not listed in layout.json.",
               ["Often packaging leftovers, logs, or runtime artifacts.",
                "If they are real content, regenerate layout.json with "
                "MSFSLayoutGenerator.",
                "Otherwise consider cleanup (back up first)."]),
    },
}

#: 关系分析章节的处理指导
RELATIONSHIP_GUIDANCE = {
    "resource_conflicts": {
        "zh": ("资源路径重叠", "多个包声明了相同的 VFS 相对路径。",
               ["确认是否为有意覆盖（依赖声明或全局覆盖声明）。",
                "若属冲突：在管理页禁用一个包后复测，再决定保留哪一个。"]),
        "en": ("Resource path overlaps",
               "Multiple packages declare the same VFS-relative path.",
               ["Confirm whether the override is intentional (declared "
                "dependency or global override).",
                "If it is a real conflict: disable one package, re-test, then "
                "decide which to keep."]),
    },
    "airport_conflicts": {
        "zh": ("机场重复候选", "多个包以多个信号指向同一机场。",
               ["检查是否为同一机场的 Patch/配套包（可有意覆盖）。",
                "若非有意，禁用重复包并在模拟器中确认。"]),
        "en": ("Airport duplication candidates",
               "Multiple packages point to the same airport via several "
               "signals.",
               ["Check whether they are patch/companion packages (intentional "
                "override).",
                "If not intentional, disable the duplicate and verify in the "
                "simulator."]),
    },
    "dependencies": {
        "zh": ("依赖关系", "包声明的依赖解析情况。",
               ["范围外依赖无需处理，可能位于 Official 或其他包源。",
                "依赖环需要与插件作者确认，AeroGuard 无法自动解决。"]),
        "en": ("Dependencies", "How declared dependencies resolved.",
               ["Out-of-scope dependencies need no action; they may live in "
                "Official or another source.",
                "Dependency cycles require confirmation from the add-on "
                "author."]),
    },
}

SAFETY_NOTE = {
    "zh": "以下建议均以「只读扫描」为前提：先备份，再修改或重装；"
          "不要在未确认前直接删除插件文件。",
    "en": "All guidance assumes the scan was read-only: back up before "
          "changing or reinstalling, and do not delete add-on files before "
          "confirming the cause.",
}


def _lang():
    return "zh" if current_language() == "zh" else "en"


def _guidance(rule_id):
    entry = RULE_GUIDANCE.get(rule_id)
    if entry is None:
        return None
    title, meaning, actions = entry[_lang()]
    return {"title": title, "meaning": meaning, "actions": actions}


def _md_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _package_issues(document):
    grouped = document.get("issues_by_package") or {}
    return sorted(grouped.items(), key=lambda item: item[0].casefold())


def _used_rules(document):
    rules = []
    for _package, issues in _package_issues(document):
        for issue in issues:
            rule_id = issue.get("rule_id")
            if rule_id and rule_id not in rules and rule_id in RULE_GUIDANCE:
                rules.append(rule_id)
    return rules


def _summary_block(document):
    summary = document.get("summary", {})
    return [
        ("addons", summary.get("addons", 0)),
        ("issues", summary.get("issues", 0)),
        ("scan_errors", summary.get("scan_errors", 0)),
        ("resource_conflicts", summary.get("resource_conflicts", 0)),
        ("airport_conflicts", summary.get("airport_conflicts", 0)),
        ("downgraded", summary.get("downgraded_issues", 0)),
    ]


def export_markdown(document):
    """把报告文档导出为 Markdown 文本。"""
    lang = _lang()
    lines = []
    lines.append("# AeroGuard report")
    lines.append("")
    lines.append(f"- `{tr('report.community_path', path=document.get('community_path', ''))}`")
    lines.append(f"- `{tr('report.scan_mode', mode=document.get('scan_mode', ''))}`")
    lines.append(f"- generated_at: {document.get('generated_at', '')}")
    lines.append(f"- schema_version: {document.get('schema_version', '')}")
    lines.append("")

    lines.append("## Summary" if lang == "en" else "## 概览")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    for key, value in _summary_block(document):
        lines.append(f"| {key} | {value} |")
    lines.append("")

    lines.append("## Findings by rule" if lang == "en" else "## 按规则统计")
    lines.append("")
    lines.append("| rule | packages | affected |")
    lines.append("| --- | --- | --- |")
    for item in document.get("rule_summary", []):
        lines.append(
            f"| {item['rule_id']} | {item['packages']} | {item['affected']} |"
        )
    lines.append("")

    lines.append("## Findings by add-on" if lang == "en" else "## 按插件明细")
    lines.append("")
    for package, issues in _package_issues(document):
        lines.append(f"### {package}")
        lines.append("")
        for issue in issues:
            severity = str(issue.get("severity", "")).upper()
            suffix = ""
            if issue.get("override"):
                suffix += " [override]"
            if issue.get("original_severity"):
                suffix += " [noise-reduced]"
            lines.append(
                f"- **[{severity}]** `{issue.get('rule_id', '')}` — "
                f"{issue.get('message', '')} "
                f"({issue.get('affected_count', 1)} item(s)){suffix}"
            )
            for note in issue.get("notes") or []:
                lines.append(f"  - note: {note.get('text', '')}")
        lines.append("")

    relationships = document.get("relationships")
    if relationships:
        rel_summary = relationships.get("summary", {})
        lines.append("## Conflicts & dependencies"
                     if lang == "en" else "## 冲突与依赖")
        lines.append("")
        lines.append(
            f"- resource_conflicts: {rel_summary.get('resource_conflicts', 0)}"
        )
        lines.append(
            f"- airport_conflicts: {rel_summary.get('airport_conflicts', 0)}"
        )
        lines.append(
            f"- declared_dependencies: "
            f"{rel_summary.get('declared_dependencies', 0)}"
        )
        lines.append("")
        for conflict in (relationships.get("resource_conflicts") or [])[:20]:
            packages = ", ".join(
                str(item.get("package", ""))
                for item in conflict.get("packages", [])
            )
            lines.append(
                f"- [{str(conflict.get('severity', '')).upper()}] "
                f"`{_md_escape(conflict.get('path', ''))}` — {packages}"
            )
        lines.append("")

    rules = _used_rules(document)
    lines.append("## How to handle" if lang == "en" else "## 处理建议")
    lines.append("")
    lines.append(f"> {SAFETY_NOTE[lang]}")
    lines.append("")
    for rule_id in rules:
        guidance = _guidance(rule_id)
        lines.append(f"### {rule_id} — {guidance['title']}")
        lines.append("")
        lines.append(guidance["meaning"])
        lines.append("")
        for action in guidance["actions"]:
            lines.append(f"- {action}")
        lines.append("")

    if relationships:
        for key in ("resource_conflicts", "airport_conflicts", "dependencies"):
            title, meaning, actions = RELATIONSHIP_GUIDANCE[key][lang]
            lines.append(f"### {key} — {title}")
            lines.append("")
            lines.append(meaning)
            lines.append("")
            for action in actions:
                lines.append(f"- {action}")
            lines.append("")

    scan_errors = document.get("scan_errors") or []
    if scan_errors:
        lines.append("## Scan errors" if lang == "en" else "## 扫描错误")
        lines.append("")
        for error in scan_errors:
            lines.append(
                f"- {error.get('package', '')}: {error.get('error', '')}"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by AeroGuard — local, read-only diagnostics. "
        "An anomaly does not necessarily mean the add-on is broken."
    )
    lines.append("")
    return "\n".join(lines)


_HTML_CSS = """
body { font-family: Segoe UI, system-ui, sans-serif; margin: 32px auto;
       max-width: 960px; line-height: 1.55; color: #1f2937; }
h1 { border-bottom: 2px solid #0ea5e9; padding-bottom: 6px; }
h2 { margin-top: 28px; color: #0f172a; }
h3 { margin-top: 20px; color: #334155; }
table { border-collapse: collapse; margin: 12px 0; width: 100%; }
th, td { border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; }
th { background: #f1f5f9; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
.sev-ERROR { color: #c62828; font-weight: 600; }
.sev-WARNING { color: #b26a00; font-weight: 600; }
.sev-INFO { color: #1a56db; }
blockquote { border-left: 4px solid #0ea5e9; margin: 12px 0;
             padding: 6px 14px; background: #f8fafc; }
footer { margin-top: 32px; color: #64748b; font-size: 13px; }
"""


def export_html(document):
    """把报告文档导出为独立 HTML（内联样式，可直接分享）。"""
    lang = _lang()
    esc = html.escape
    parts = [
        "<!DOCTYPE html>",
        '<html lang="{}">'.format("zh" if lang == "zh" else "en"),
        "<head><meta charset='utf-8'>",
        "<title>AeroGuard report</title>",
        f"<style>{_HTML_CSS}</style>",
        "</head><body>",
        "<h1>AeroGuard report</h1>",
        "<ul>",
        f"<li>{esc(tr('report.community_path', path=document.get('community_path', '')))}</li>",
        f"<li>{esc(tr('report.scan_mode', mode=document.get('scan_mode', '')))}</li>",
        f"<li>generated_at: {esc(str(document.get('generated_at', '')))}</li>",
        f"<li>schema_version: {esc(str(document.get('schema_version', '')))}</li>",
        "</ul>",
    ]

    parts.append("<h2>{}</h2>".format("Summary" if lang == "en" else "概览"))
    parts.append("<table><tr><th>metric</th><th>value</th></tr>")
    for key, value in _summary_block(document):
        parts.append(f"<tr><td>{esc(key)}</td><td>{esc(str(value))}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>{}</h2>".format(
        "Findings by rule" if lang == "en" else "按规则统计"
    ))
    parts.append("<table><tr><th>rule</th><th>packages</th>"
                 "<th>affected</th></tr>")
    for item in document.get("rule_summary", []):
        parts.append(
            f"<tr><td><code>{esc(item['rule_id'])}</code></td>"
            f"<td>{item['packages']}</td><td>{item['affected']}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>{}</h2>".format(
        "Findings by add-on" if lang == "en" else "按插件明细"
    ))
    for package, issues in _package_issues(document):
        parts.append(f"<h3>{esc(package)}</h3><ul>")
        for issue in issues:
            severity = str(issue.get("severity", "")).upper()
            suffix = ""
            if issue.get("override"):
                suffix += " [override]"
            if issue.get("original_severity"):
                suffix += " [noise-reduced]"
            parts.append(
                f"<li><span class='sev-{esc(severity)}'>[{esc(severity)}]</span> "
                f"<code>{esc(str(issue.get('rule_id', '')))}</code> — "
                f"{esc(str(issue.get('message', '')))} "
                f"({esc(str(issue.get('affected_count', 1)))} item(s))"
                f"{esc(suffix)}"
            )
            notes = issue.get("notes") or []
            if notes:
                parts.append("<ul>")
                for note in notes:
                    parts.append(f"<li>note: {esc(str(note.get('text', '')))}</li>")
                parts.append("</ul>")
            parts.append("</li>")
        parts.append("</ul>")

    relationships = document.get("relationships")
    if relationships:
        rel_summary = relationships.get("summary", {})
        parts.append("<h2>{}</h2>".format(
            "Conflicts & dependencies" if lang == "en" else "冲突与依赖"
        ))
        parts.append("<ul>")
        for key in ("resource_conflicts", "airport_conflicts",
                    "declared_dependencies"):
            parts.append(
                f"<li>{esc(key)}: {rel_summary.get(key, 0)}</li>"
            )
        parts.append("</ul>")
        conflicts = relationships.get("resource_conflicts") or []
        if conflicts:
            parts.append("<ul>")
            for conflict in conflicts[:20]:
                packages = ", ".join(
                    str(item.get("package", ""))
                    for item in conflict.get("packages", [])
                )
                parts.append(
                    f"<li>[{esc(str(conflict.get('severity', '')).upper())}] "
                    f"<code>{esc(str(conflict.get('path', '')))}</code> — "
                    f"{esc(packages)}</li>"
                )
            parts.append("</ul>")

    parts.append("<h2>{}</h2>".format(
        "How to handle" if lang == "en" else "处理建议"
    ))
    parts.append(f"<blockquote>{esc(SAFETY_NOTE[lang])}</blockquote>")
    for rule_id in _used_rules(document):
        guidance = _guidance(rule_id)
        parts.append(
            f"<h3>{esc(rule_id)} — {esc(guidance['title'])}</h3>"
        )
        parts.append(f"<p>{esc(guidance['meaning'])}</p><ul>")
        for action in guidance["actions"]:
            parts.append(f"<li>{esc(action)}</li>")
        parts.append("</ul>")
    if relationships:
        for key in ("resource_conflicts", "airport_conflicts", "dependencies"):
            title, meaning, actions = RELATIONSHIP_GUIDANCE[key][lang]
            parts.append(f"<h3>{esc(key)} — {esc(title)}</h3>")
            parts.append(f"<p>{esc(meaning)}</p><ul>")
            for action in actions:
                parts.append(f"<li>{esc(action)}</li>")
            parts.append("</ul>")

    scan_errors = document.get("scan_errors") or []
    if scan_errors:
        parts.append("<h2>{}</h2><ul>".format(
            "Scan errors" if lang == "en" else "扫描错误"
        ))
        for error in scan_errors:
            parts.append(
                f"<li>{esc(str(error.get('package', '')))}: "
                f"{esc(str(error.get('error', '')))}</li>"
            )
        parts.append("</ul>")

    parts.append(
        "<footer>Generated by AeroGuard — local, read-only diagnostics. "
        f"Exported at {datetime.now(timezone.utc).isoformat(timespec='seconds')}."
        "</footer>"
    )
    parts.append("</body></html>")
    return "\n".join(parts)
