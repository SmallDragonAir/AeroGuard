"""跨 Package 的 VFS 资源、机场与依赖关系分析。"""

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath


RUNTIME_VFS_ROOTS = {
    "cgl",
    "config",
    "data",
    "effects",
    "html_ui",
    "materiallibs",
    "modelbehaviordefs",
    "scenery",
    "simobjects",
    "simpropcontainers",
    "visualeffectlibs",
}

PACKAGE_METADATA_PATHS = {
    "layout.json",
    "manifest.json",
}

OS_JUNK_PATHS = {
    ".ds_store",
    "desktop.ini",
    "thumbs.db",
}

AIRPORT_CODE_STOP_WORDS = {
    "AERO", "AIRPORT", "AREA", "BASE", "BOUT", "CHINA", "CITY",
    "COMP", "COPY", "DARK", "DATA", "DISH", "DOOR", "DROP",
    "FIRE", "FLAGS", "GATE", "GLOBAL", "GLTF", "HAIR", "INTL",
    "JSON", "KTX2", "LIGHT", "LINE", "LONG", "MARK", "MISC",
    "MODE", "MODEL", "MODELS", "NIGHT", "OBJECT", "OBJECTS",
    "PARK", "RAMP", "REAL", "ROAD", "ROOF", "SCENERY", "SHED",
    "SIGN", "SKIN", "TAXI", "TERM", "TEST", "TEXT", "TILE",
    "TREE", "WALL", "WOOD", "WORLD",
}

AIRPORT_CODE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Z0-9])([A-Z0-9]{3,8})(?![A-Z0-9])"
)
AIRPORT_CODE_AFTER_PATTERN = re.compile(
    r"(?:^|[-_ /])AIRPORT[-_ ]+([A-Z0-9]{3,8})(?:[-_ /.]|$)"
)
AIRPORT_CODE_BEFORE_PATTERN = re.compile(
    r"(?:^|[-_ /])([A-Z0-9]{3,8})[-_ ]+AIRPORT(?:[-_ /.]|$)"
)


@dataclass
class RelationshipAnalysis:
    """可直接写入 JSON 报告的跨 Package 分析结果。"""

    resource_conflicts: list = field(default_factory=list)
    airport_packages: list = field(default_factory=list)
    airport_conflicts: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    dependency_cycles: list = field(default_factory=list)

    def summary(self):
        dependency_status = defaultdict(int)
        for dependency in self.dependencies:
            dependency_status[dependency["status"]] += 1

        return {
            "resource_conflicts": len(self.resource_conflicts),
            "resource_warnings": sum(
                item["severity"] == "warning"
                for item in self.resource_conflicts
            ),
            "intentional_overrides": sum(
                bool(item["intentional_overrides"])
                for item in self.resource_conflicts
            ),
            "identified_airport_packages": len(self.airport_packages),
            "airport_conflicts": len(self.airport_conflicts),
            "declared_dependencies": len(self.dependencies),
            "dependencies_resolved_in_scan_root": dependency_status[
                "resolved_in_scan_root"
            ],
            "dependencies_outside_scan_scope": dependency_status[
                "outside_scan_scope"
            ],
            "invalid_dependencies": dependency_status["invalid"],
            "dependency_cycles": len(self.dependency_cycles),
        }

    def as_dict(self):
        document = asdict(self)
        document["summary"] = self.summary()
        return document


def _normalize_path(path):
    return str(path).replace("\\", "/").strip("/").casefold()


def _load_layout_entries(addon):
    """读取有效 layout 条目；结构错误由 Analyzer 负责报告。"""
    layout_path = Path(addon["path"]) / "layout.json"
    try:
        with open(layout_path, "r", encoding="utf-8-sig") as file:
            layout = json.load(file)
    except (OSError, ValueError, TypeError):
        return []

    if not isinstance(layout, dict):
        return []
    content = layout.get("content")
    if not isinstance(content, list):
        return []

    entries = []
    seen = set()
    for item in content:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        normalized = _normalize_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        entries.append({
            "path": path.replace("\\", "/"),
            "normalized_path": normalized,
            "size": item.get("size") if isinstance(item.get("size"), int)
            else None,
        })
    return entries


def _dependency_names(manifest):
    names = set()
    dependencies = manifest.get("dependencies", [])
    if not isinstance(dependencies, list):
        return names
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        name = dependency.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
    return names


def _intentional_overrides(owners, normalized_path):
    intentional = []
    seen = set()

    for owner in owners:
        for target in owners:
            if owner is target:
                continue
            pair = (owner["package"], target["package"])

            basis = None
            if target["package"].casefold() in owner["dependency_names"]:
                basis = "declared_dependency"
            elif normalized_path in owner["global_overrides"]:
                basis = "declared_global_override"

            if basis is not None and (pair, basis) not in seen:
                seen.add((pair, basis))
                intentional.append({
                    "package": owner["package"],
                    "target": target["package"],
                    "basis": basis,
                })

    return intentional


def _likely_winner(owners):
    hints = {owner["package_order_hint"] for owner in owners}
    if len(hints) == 1 and None not in hints:
        winner = max(owners, key=lambda item: item["package"].casefold())
        return {
            "package": winner["package"],
            "basis": "same_order_hint_alphabetical_default",
            "confidence": "default_order_only",
        }

    return None


def _resource_scope(normalized_path):
    if "/" not in normalized_path:
        return "package_root"
    top = normalized_path.split("/", 1)[0]
    if top in RUNTIME_VFS_ROOTS:
        return "runtime_vfs"
    return "other_vfs"


def _analyze_resource_conflicts(packages):
    path_owners = defaultdict(list)
    for package in packages:
        for entry in package["entries"]:
            normalized = entry["normalized_path"]
            if normalized in PACKAGE_METADATA_PATHS or normalized in OS_JUNK_PATHS:
                continue
            path_owners[normalized].append({
                "package": package["package"],
                "declared_path": entry["path"],
                "size": entry["size"],
                "package_order_hint": package["package_order_hint"],
                "dependency_names": package["dependency_names"],
                "global_overrides": package["global_overrides"],
            })

    conflicts = []
    for normalized, owners in path_owners.items():
        if len(owners) < 2:
            continue

        sizes = {owner["size"] for owner in owners if owner["size"] is not None}
        same_declared_size = (
            len(sizes) == 1
            and all(owner["size"] is not None for owner in owners)
        )
        scope = _resource_scope(normalized)
        intentional = _intentional_overrides(owners, normalized)

        if intentional:
            severity = "info"
            reason = "检测到声明依赖或显式全局覆盖关系"
        elif scope == "runtime_vfs" and not same_declared_size:
            severity = "warning"
            reason = "运行时 VFS 路径重叠且声明大小不同"
        elif scope == "runtime_vfs":
            severity = "info"
            reason = "运行时 VFS 路径重叠且声明大小相同，仍需哈希或实机确认"
        else:
            severity = "info"
            reason = "路径重叠，但当前静态信息不足以确定实际运行影响"

        public_owners = [{
            "package": owner["package"],
            "declared_path": owner["declared_path"],
            "size": owner["size"],
            "package_order_hint": owner["package_order_hint"],
        } for owner in owners]

        conflicts.append({
            "path": owners[0]["declared_path"],
            "normalized_path": normalized,
            "severity": severity,
            "scope": scope,
            "reason": reason,
            "same_declared_size": same_declared_size,
            "packages": public_owners,
            "intentional_overrides": intentional,
            "likely_winner": _likely_winner(owners),
        })

    severity_order = {"warning": 2, "info": 1}
    return sorted(
        conflicts,
        key=lambda item: (
            severity_order[item["severity"]],
            len(item["packages"]),
            item["normalized_path"],
        ),
        reverse=True,
    )


def _valid_airport_code(code, allow_wide=False):
    return (
        code not in AIRPORT_CODE_STOP_WORDS
        and any(character.isalpha() for character in code)
        and (3 <= len(code) <= 8 if allow_wide else 3 <= len(code) <= 4)
    )


def _add_airport_code_signal(signals, code, source, allow_wide=False):
    code = code.upper()
    if _valid_airport_code(code, allow_wide):
        signals[code].add(source)


def _airport_codes(package):
    manifest = package["manifest"]
    if str(manifest.get("content_type", "")).casefold() != "scenery":
        return {}

    signals = defaultdict(set)
    folder_name = package["package"].upper()
    title = str(manifest.get("title", "")).upper()

    if _valid_airport_code(folder_name, allow_wide=True):
        _add_airport_code_signal(signals, folder_name, "folder", allow_wide=True)
    for code in AIRPORT_CODE_AFTER_PATTERN.findall(folder_name):
        _add_airport_code_signal(signals, code, "folder", allow_wide=True)

    if "AIRPORT" in title:
        for code in AIRPORT_CODE_TOKEN_PATTERN.findall(title):
            _add_airport_code_signal(signals, code, "title")

    for entry in package["entries"]:
        path = entry["path"].upper()
        for pattern in (
            AIRPORT_CODE_AFTER_PATTERN,
            AIRPORT_CODE_BEFORE_PATTERN,
        ):
            for code in pattern.findall(path):
                _add_airport_code_signal(
                    signals, code, "layout", allow_wide=True
                )

        if path.endswith(".BGL"):
            stem = PurePosixPath(path).stem
            _add_airport_code_signal(
                signals, stem, "layout", allow_wide=True
            )

    return {
        code: sorted(sources)
        for code, sources in signals.items()
        if len(sources) >= 2 and "layout" in sources
    }


def _analyze_airports(packages):
    airport_packages = []
    by_code = defaultdict(list)

    for package in packages:
        codes = _airport_codes(package)
        for code, signals in codes.items():
            item = {
                "airport_code": code,
                "package": package["package"],
                "title": package["manifest"].get("title"),
                "signals": signals,
                "package_order_hint": package["package_order_hint"],
            }
            airport_packages.append(item)
            by_code[code].append(item)

    conflicts = []
    for code, owners in by_code.items():
        if len(owners) < 2:
            continue

        patch_owners = [
            owner for owner in owners
            if (owner["package_order_hint"] or "").endswith("_PATCH")
        ]
        intentional = bool(patch_owners)
        conflicts.append({
            "airport_code": code,
            "severity": "info" if intentional else "warning",
            "confidence": "heuristic_high",
            "reason": (
                "同一机场包含 Patch 顺序包，可能是有意覆盖"
                if intentional else
                "多个 Package 以至少两个独立静态信号指向同一机场"
            ),
            "packages": owners,
            "intentional_override": intentional,
            "likely_winner": (
                patch_owners[0]["package"] if len(patch_owners) == 1 else None
            ),
        })

    airport_packages.sort(
        key=lambda item: (item["airport_code"], item["package"])
    )
    conflicts.sort(
        key=lambda item: (item["severity"] == "warning", len(item["packages"])),
        reverse=True,
    )
    return airport_packages, conflicts


def _analyze_dependencies(packages):
    installed = {
        package["package"].casefold(): package
        for package in packages
    }
    dependencies = []
    adjacency = defaultdict(set)

    for package in packages:
        raw_dependencies = package["manifest"].get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            dependencies.append({
                "package": package["package"],
                "name": None,
                "declared_version": None,
                "status": "invalid",
                "reason": "manifest dependencies 不是列表",
            })
            continue

        for dependency in raw_dependencies:
            if not isinstance(dependency, dict):
                dependencies.append({
                    "package": package["package"],
                    "name": None,
                    "declared_version": None,
                    "status": "invalid",
                    "reason": "依赖条目不是 JSON 对象",
                })
                continue

            name = dependency.get("name")
            version = dependency.get("package_version")
            if not isinstance(name, str) or not name.strip():
                dependencies.append({
                    "package": package["package"],
                    "name": None,
                    "declared_version": version,
                    "status": "invalid",
                    "reason": "依赖名称缺失或类型无效",
                })
                continue

            name = name.strip()
            target = installed.get(name.casefold())
            if target is None:
                dependencies.append({
                    "package": package["package"],
                    "name": name,
                    "declared_version": version,
                    "status": "outside_scan_scope",
                    "reason": "当前扫描根目录中未找到；可能位于 Official 或其他包源",
                })
                continue

            dependencies.append({
                "package": package["package"],
                "name": name,
                "declared_version": version,
                "status": "resolved_in_scan_root",
                "installed_package": target["package"],
                "installed_version": target["manifest"].get("package_version"),
            })
            adjacency[package["package"]].add(target["package"])

    cycles = _dependency_cycles(adjacency)
    return dependencies, cycles


def _dependency_cycles(adjacency):
    """返回去重后的当前扫描根目录内依赖环。"""
    visiting = set()
    visited = set()
    stack = []
    cycles = set()

    def canonical_cycle(nodes):
        rotations = [
            tuple(nodes[index:] + nodes[:index])
            for index in range(len(nodes))
        ]
        return min(rotations, key=lambda item: tuple(x.casefold() for x in item))

    def visit(node):
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)

        for target in adjacency.get(node, ()):
            if target in visiting:
                start = stack.index(target)
                cycles.add(canonical_cycle(stack[start:]))
            elif target not in visited:
                visit(target)

        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        visit(node)

    return [list(cycle) for cycle in sorted(cycles)]


def analyze_relationships(addons):
    """分析当前扫描根目录中的跨 Package 关系。"""
    packages = []
    for addon in addons:
        manifest = addon.get("manifest")
        if not isinstance(manifest, dict):
            manifest = {}
        global_overrides = manifest.get("globally_overriden_base_sim_files", [])
        if not isinstance(global_overrides, list):
            global_overrides = []

        packages.append({
            "package": addon["folder_name"],
            "manifest": manifest,
            "entries": _load_layout_entries(addon),
            "package_order_hint": (
                str(manifest["package_order_hint"]).upper()
                if manifest.get("package_order_hint") else None
            ),
            "dependency_names": _dependency_names(manifest),
            "global_overrides": {
                _normalize_path(path)
                for path in global_overrides
                if isinstance(path, str)
            },
        })

    resource_conflicts = _analyze_resource_conflicts(packages)
    airport_packages, airport_conflicts = _analyze_airports(packages)
    dependencies, dependency_cycles = _analyze_dependencies(packages)

    return RelationshipAnalysis(
        resource_conflicts=resource_conflicts,
        airport_packages=airport_packages,
        airport_conflicts=airport_conflicts,
        dependencies=dependencies,
        dependency_cycles=dependency_cycles,
    )
