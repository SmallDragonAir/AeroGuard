"""紧凑扫描历史、环境基线与确定性差异比较。"""

import hashlib
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SNAPSHOT_SCHEMA_VERSION = 1
BASELINE_SCHEMA_VERSION = 1
SEVERITY_ORDER = {"info": 1, "warning": 2, "error": 3}


class HistoryError(RuntimeError):
    """历史或基线数据无法安全读取或写入。"""


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_snapshot_id():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _safe_name(value, label):
    if not isinstance(value, str):
        raise HistoryError(f"{label}必须是字符串")
    value = value.strip()
    if not value or value in {".", ".."}:
        raise HistoryError(f"{label}不能为空")
    if len(value) > 128 or any(char in value for char in '<>:"/\\|?*'):
        raise HistoryError(f"{label}不是安全文件名")
    if any(ord(char) < 32 for char in value) or value.endswith((" ", ".")):
        raise HistoryError(f"{label}不是安全文件名")
    return value


def _read_json_object(path, label):
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            document = json.load(file)
    except (OSError, ValueError, TypeError) as error:
        raise HistoryError(f"{label}无法读取：{error}") from error
    if not isinstance(document, dict):
        raise HistoryError(f"{label}顶层必须是 JSON 对象")
    return document


def _write_json_atomic(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _stable_digest(value):
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _compact_issues(report):
    grouped = defaultdict(list)
    for package, issues in report.get("issues_by_package", {}).items():
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if isinstance(issue, dict):
                grouped[(str(package), str(issue.get("rule_id", "")))].append(
                    issue
                )

    compact = []
    for (package, rule_id), issues in grouped.items():
        highest = max(
            issues,
            key=lambda item: SEVERITY_ORDER.get(item.get("severity"), 0),
        )
        evidence = [
            {
                "details": issue.get("details", []),
                "affected_count": issue.get("affected_count", 1),
                "severity": issue.get("severity"),
                "impact": issue.get("impact"),
                "downgrade_rule": issue.get("downgrade_rule"),
            }
            for issue in issues
        ]
        compact.append({
            "package": package,
            "rule_id": rule_id,
            "severity": highest.get("severity"),
            "affected_count": sum(
                issue.get("affected_count", 1) for issue in issues
            ),
            "impacts": sorted({
                str(issue.get("impact") or "unknown") for issue in issues
            }),
            "evidence_digest": _stable_digest(evidence),
        })
    return sorted(
        compact,
        key=lambda item: (item["package"].casefold(), item["rule_id"]),
    )


def _compact_relationships(report):
    relationships = report.get("relationships") or {}
    resource_conflicts = []
    for conflict in relationships.get("resource_conflicts", []):
        if not isinstance(conflict, dict):
            continue
        resource_conflicts.append({
            "path": conflict.get("normalized_path") or conflict.get("path"),
            "severity": conflict.get("severity"),
            "scope": conflict.get("scope"),
            "packages": sorted(
                str(item.get("package") or "")
                for item in conflict.get("packages", [])
                if isinstance(item, dict)
            ),
            "intentional": bool(conflict.get("intentional_overrides")),
        })

    airport_conflicts = []
    for conflict in relationships.get("airport_conflicts", []):
        if not isinstance(conflict, dict):
            continue
        airport_conflicts.append({
            "airport_code": conflict.get("airport_code"),
            "severity": conflict.get("severity"),
            "packages": sorted(
                str(item.get("package") or "")
                for item in conflict.get("packages", [])
                if isinstance(item, dict)
            ),
            "intentional": bool(conflict.get("intentional_override")),
        })

    dependencies = []
    for dependency in relationships.get("dependencies", []):
        if not isinstance(dependency, dict):
            continue
        dependencies.append({
            "package": dependency.get("package"),
            "name": dependency.get("name"),
            "status": dependency.get("status"),
            "declared_version": dependency.get("declared_version"),
            "installed_version": dependency.get("installed_version"),
        })

    return {
        "resource_conflicts": sorted(
            resource_conflicts, key=lambda item: str(item["path"]).casefold()
        ),
        "airport_conflicts": sorted(
            airport_conflicts,
            key=lambda item: str(item["airport_code"]).casefold(),
        ),
        "dependencies": sorted(
            dependencies,
            key=lambda item: (
                str(item["package"]).casefold(),
                str(item["name"]).casefold(),
            ),
        ),
        "dependency_cycles": sorted(
            relationships.get("dependency_cycles", [])
        ),
    }


def build_snapshot(report, *, snapshot_id=None, label=None):
    """从完整 JSON 报告构造适合长期保存的紧凑快照。"""
    if not isinstance(report, dict):
        raise HistoryError("报告必须是 JSON 对象")
    snapshot_id = _safe_name(
        snapshot_id or _new_snapshot_id(), "快照 ID"
    )
    packages = []
    for addon in report.get("addons", []):
        if not isinstance(addon, dict):
            continue
        packages.append({
            "package": addon.get("folder_name"),
            "title": addon.get("name"),
            "content_type": addon.get("type"),
            "version": addon.get("version"),
        })
    packages.sort(key=lambda item: str(item["package"]).casefold())
    compact_relationships = _compact_relationships(report)
    issues = _compact_issues(report)
    scan_errors = [
        {
            "package": item.get("package"),
            "path": item.get("path"),
            "error": item.get("error"),
        }
        for item in report.get("scan_errors", [])
        if isinstance(item, dict)
    ]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "recorded_at": _now_utc(),
        "source_generated_at": report.get("generated_at"),
        "source_schema_version": report.get("schema_version"),
        "community_path": report.get("community_path"),
        "scan_mode": report.get("scan_mode"),
        "label": str(label) if label else None,
        "summary": {
            "addons": len(packages),
            "issues": len(issues),
            "scan_errors": len(scan_errors),
            "resource_conflicts": len(
                compact_relationships["resource_conflicts"]
            ),
            "airport_conflicts": len(
                compact_relationships["airport_conflicts"]
            ),
            "elapsed_s": report.get("timing", {}).get("total_s"),
        },
        "packages": packages,
        "issues": issues,
        "scan_errors": scan_errors,
        **compact_relationships,
    }


def _compare_section(before, after, key_fields):
    def item_key(item):
        return tuple(str(item.get(field, "")).casefold() for field in key_fields)

    before_index = {item_key(item): item for item in before}
    after_index = {item_key(item): item for item in after}
    before_keys = set(before_index)
    after_keys = set(after_index)
    added = [after_index[key] for key in sorted(after_keys - before_keys)]
    removed = [before_index[key] for key in sorted(before_keys - after_keys)]
    changed = [
        {
            "key": dict(zip(key_fields, key)),
            "before": before_index[key],
            "after": after_index[key],
        }
        for key in sorted(before_keys & after_keys)
        if before_index[key] != after_index[key]
    ]
    return {"added": added, "removed": removed, "changed": changed}


def compare_snapshots(baseline, current):
    """比较两个快照，返回可序列化的环境差异。"""
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise HistoryError("基线和当前快照必须是 JSON 对象")
    sections = {
        "packages": _compare_section(
            baseline.get("packages", []), current.get("packages", []),
            ("package",),
        ),
        "issues": _compare_section(
            baseline.get("issues", []), current.get("issues", []),
            ("package", "rule_id"),
        ),
        "resource_conflicts": _compare_section(
            baseline.get("resource_conflicts", []),
            current.get("resource_conflicts", []),
            ("path",),
        ),
        "airport_conflicts": _compare_section(
            baseline.get("airport_conflicts", []),
            current.get("airport_conflicts", []),
            ("airport_code",),
        ),
        "dependencies": _compare_section(
            baseline.get("dependencies", []), current.get("dependencies", []),
            ("package", "name"),
        ),
        "scan_errors": _compare_section(
            baseline.get("scan_errors", []), current.get("scan_errors", []),
            ("package", "path"),
        ),
    }
    counts = {
        section: {
            change: len(items)
            for change, items in changes.items()
        }
        for section, changes in sections.items()
    }
    cycles_changed = (
        baseline.get("dependency_cycles", [])
        != current.get("dependency_cycles", [])
    )
    total_changes = sum(
        count for section in counts.values() for count in section.values()
    ) + int(cycles_changed)
    compatibility_warnings = []
    if baseline.get("scan_mode") != current.get("scan_mode"):
        compatibility_warnings.append({
            "field": "scan_mode",
            "baseline": baseline.get("scan_mode"),
            "current": current.get("scan_mode"),
            "warning": "扫描模式不同，文件一致性问题变化不可直接比较",
        })
    if baseline.get("community_path") != current.get("community_path"):
        compatibility_warnings.append({
            "field": "community_path",
            "baseline": baseline.get("community_path"),
            "current": current.get("community_path"),
            "warning": "Community 路径不同，结果可能属于不同环境",
        })
    return {
        "baseline_snapshot_id": baseline.get("snapshot_id"),
        "current_snapshot_id": current.get("snapshot_id"),
        "compared_at": _now_utc(),
        "summary": {
            "total_changes": total_changes,
            "sections": counts,
            "compatibility_warnings": len(compatibility_warnings),
        },
        "compatibility_warnings": compatibility_warnings,
        **sections,
        "dependency_cycles": {
            "before": baseline.get("dependency_cycles", []),
            "after": current.get("dependency_cycles", []),
            "changed": cycles_changed,
        },
    }


class HistoryStore:
    """在 Community 外保存扫描快照与命名基线。"""

    def __init__(self, community_path, state_root=None):
        community = Path(community_path).expanduser().resolve()
        if not community.is_dir():
            raise HistoryError(f"Community 路径不存在或不是目录：{community}")
        state = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else (community.parent / ".aeroguard").resolve()
        )
        if state == community or state.is_relative_to(community):
            raise HistoryError("历史状态目录必须位于 Community 之外")
        self.community = community
        self.state_root = state
        self.snapshot_root = state / "history" / "snapshots"
        self.baseline_root = state / "history" / "baselines"

    def _snapshot_path(self, snapshot_id):
        return self.snapshot_root / f"{_safe_name(snapshot_id, '快照 ID')}.json"

    def _baseline_path(self, name):
        return self.baseline_root / f"{_safe_name(name, '基线名称')}.json"

    def record(self, report, label=None):
        snapshot = build_snapshot(report, label=label)
        path = self._snapshot_path(snapshot["snapshot_id"])
        _write_json_atomic(path, snapshot)
        return {"snapshot_path": str(path), **snapshot}

    def load_snapshot(self, snapshot_id):
        return _read_json_object(self._snapshot_path(snapshot_id), "扫描快照")

    def list_snapshots(self, limit=None):
        if not self.snapshot_root.is_dir():
            return []
        snapshots = []
        for path in self.snapshot_root.glob("*.json"):
            try:
                snapshot = _read_json_object(path, str(path))
                snapshots.append({
                    "snapshot_id": snapshot.get("snapshot_id", path.stem),
                    "recorded_at": snapshot.get("recorded_at"),
                    "scan_mode": snapshot.get("scan_mode"),
                    "label": snapshot.get("label"),
                    "summary": snapshot.get("summary", {}),
                    "path": str(path),
                })
            except HistoryError as error:
                snapshots.append({
                    "snapshot_id": path.stem,
                    "path": str(path),
                    "error": str(error),
                })
        snapshots.sort(
            key=lambda item: (
                str(item.get("recorded_at") or ""), item["snapshot_id"]
            ),
            reverse=True,
        )
        return snapshots[:limit] if limit is not None else snapshots

    def set_baseline(self, name, snapshot_id=None, replace=False):
        name = _safe_name(name, "基线名称")
        baseline_path = self._baseline_path(name)
        if baseline_path.exists() and not replace:
            raise HistoryError(
                f"基线已存在：{baseline_path}；使用 --replace 显式更新"
            )
        if snapshot_id is None:
            snapshots = self.list_snapshots(limit=1)
            if not snapshots or "error" in snapshots[0]:
                raise HistoryError("没有可用扫描快照，请先执行 record")
            snapshot_id = snapshots[0]["snapshot_id"]
        snapshot = self.load_snapshot(snapshot_id)
        document = {
            "baseline_schema_version": BASELINE_SCHEMA_VERSION,
            "baseline_name": name,
            "baseline_set_at": _now_utc(),
            **snapshot,
        }
        _write_json_atomic(baseline_path, document)
        return {"baseline_path": str(baseline_path), **document}

    def load_baseline(self, name):
        return _read_json_object(self._baseline_path(name), "环境基线")

    def compare(self, name, report):
        baseline = self.load_baseline(name)
        current = build_snapshot(report)
        comparison = compare_snapshots(baseline, current)
        comparison["baseline_name"] = baseline.get("baseline_name", name)
        return comparison
