"""单插件快速校验：只检查一个已安装插件包的一致性。

复用完整扫描的检测链路（analyzer → noise → classifier → knowledge），
不遍历整个 Community，适合安装后自检、排查单个插件时使用。
只读：不创建状态目录、不修改任何文件。
"""

import json
from pathlib import Path

from analyzer import analyze_community_with_stats
from classifier import classify_issues
from knowledge import apply_known_context
from noise import apply_noise_rules
from notes import NoteStore, NoteStoreError
from overrides import OverrideStore, OverrideStoreError


class VerifyError(RuntimeError):
    """无法校验指定插件（未找到或元数据不可读）。"""


def _find_package(community_path, package_name):
    """在 Community 中按大小写不敏感查找包目录。"""
    wanted = package_name.strip().casefold()
    if not wanted:
        raise VerifyError("插件名不能为空")
    for item in Path(community_path).iterdir():
        if item.is_dir() and item.name.casefold() == wanted:
            return item
    raise VerifyError(f"未找到插件：{package_name}")


def _load_addon(package_root):
    """构造与 scanner 输出结构一致的单个 addon 记录。"""
    manifest_path = package_root / "manifest.json"
    if not manifest_path.is_file():
        raise VerifyError(f"缺少 manifest.json：{package_root.name}")

    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as file:
            manifest = json.load(file)
    except (OSError, ValueError) as error:
        raise VerifyError(
            f"插件 manifest.json 无法解析：{error}"
        ) from error
    if not isinstance(manifest, dict):
        raise VerifyError("插件 manifest.json 顶层必须是 JSON 对象")

    return {
        "folder_name": package_root.name,
        "name": manifest.get("title"),
        "type": manifest.get("content_type"),
        "creator": manifest.get("creator"),
        "version": manifest.get("package_version"),
        "path": str(package_root),
        "manifest": manifest,
    }


def verify_package(community_path, package_name, state_dir=None):
    """校验单个插件，返回可直接 JSON 序列化的结果。"""
    community = Path(community_path).expanduser().resolve()
    if not community.is_dir():
        raise VerifyError(f"Community 路径不存在或不是目录：{community}")

    package_root = _find_package(community, package_name)
    addon = _load_addon(package_root)

    issues, stats = analyze_community_with_stats([addon], full_scan=True)
    issues = apply_noise_rules(issues, [addon])
    issues = classify_issues(issues)

    before_count = len(issues)

    note_store = None
    try:
        note_store = NoteStore(community, state_dir)
    except NoteStoreError:
        note_store = None
    override_store = None
    try:
        override_store = OverrideStore(community, state_dir)
    except OverrideStoreError:
        override_store = None

    issues = apply_known_context(
        issues, [addon],
        note_store=note_store, override_store=override_store,
    )

    severity_counts = {"error": 0, "warning": 0, "info": 0}
    impact_counts = {}
    notes_total = 0
    downgraded = 0
    for issue in issues:
        severity = str(issue.get("severity", "info"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        impact = str(issue.get("impact", "unknown"))
        impact_counts[impact] = impact_counts.get(impact, 0) + 1
        notes_total += len(issue.get("notes") or [])
        if "original_severity" in issue or "override" in issue:
            downgraded += 1

    traversal = None
    for item in stats.package_timings:
        if item.get("package") == addon["folder_name"]:
            traversal = {
                "tree_walk_time": round(item["tree_walk_time"], 3),
                "file_count": item["file_count"],
                "scan_error_count": item["scan_error_count"],
            }
            break

    return {
        "package": addon["folder_name"],
        "path": str(package_root),
        "location": "enabled",
        "title": addon["name"],
        "content_type": addon["type"],
        "creator": addon["creator"],
        "version": addon["version"],
        "summary": {
            "issues": len(issues),
            "error": severity_counts.get("error", 0),
            "warning": severity_counts.get("warning", 0),
            "info": severity_counts.get("info", 0),
            "by_impact": impact_counts,
            "downgraded": downgraded,
            "notes": notes_total,
            "ignored_by_override": max(before_count - len(issues), 0),
        },
        "traversal": traversal,
        "issues": issues,
        "restart_required": False,
    }
