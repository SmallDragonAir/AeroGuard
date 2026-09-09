import os
import time
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


# 终端 / 文本展示时每条 issue 明细最多显示多少项。
# issue["details"] 始终保存完整列表，供分类器与 JSON 报告使用。
DETAILS_PREVIEW_LIMIT = 10


# 操作系统或文件管理器自动生成的杂物文件。
# 它们不属于插件内容，报告为“未登记文件”只会增加噪音。
OS_JUNK_BASENAMES = {
    "thumbs.db",
    "desktop.ini",
    ".ds_store",
}


@dataclass
class AnalyzerStats:
    """Analyzer 内部各阶段耗时统计（秒），供性能分析使用。"""

    layout_parse_time: float = 0.0
    declared_check_time: float = 0.0
    tree_walk_time: float = 0.0
    addon_count: int = 0
    package_timings: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def make_issue(rule_id, severity, package, message, details=(),
               affected_count=None):
    """
    构造一条结构统一的 issue。

    - details: 受影响的完整项目列表（供分类器、JSON 报告使用）
    - preview: 展示用的截断视图（默认最多 10 项）
    - affected_count: 文件级问题默认取 details 长度；没有明细的包级问题
      默认计为 1，表示影响一个插件包
    """
    details = list(details)
    if len(details) <= DETAILS_PREVIEW_LIMIT:
        preview = details
    else:
        preview = details[:DETAILS_PREVIEW_LIMIT]

    if affected_count is None:
        affected_count = len(details) if details else 1

    return {
        "rule_id": rule_id,
        "severity": severity,
        "package": package,
        "message": message,
        "affected_count": affected_count,
        "details": details,
        "preview": preview,
    }


def _is_os_junk(normalized_path):
    """normalized_path 为 casefold 后的正斜杠相对路径。"""
    basename = normalized_path.rsplit("/", 1)[-1]
    return basename in OS_JUNK_BASENAMES


def build_file_index(package_root, scan_errors=None):
    """
    扫描 Package 的逻辑文件树，并建立内存索引。

    支持普通目录和目录符号链接。

    为避免符号链接形成循环，只阻止当前递归链中
    再次进入已经访问过的真实目录。

    注意：
    不能使用一个全局 visited 集合，因为多个不同的
    符号链接可能合法地指向同一个真实目录，而它们在
    Package 中对应不同的逻辑路径。
    """

    package_root = Path(package_root)

    file_index = {}
    if scan_errors is None:
        scan_errors = []

    def record_scan_error(path, error):
        """记录无法读取的逻辑路径，供 Analyzer 避免把未知状态报成缺失。"""
        try:
            relative_path = Path(path).relative_to(package_root).as_posix()
        except ValueError:
            relative_path = str(path)

        scan_errors.append({
            "path": relative_path or ".",
            "error": f"{type(error).__name__}: {error}",
        })


    ancestor_real_paths = set()

    def scan_directory(current_path, real_path):
        # 当前递归链中再次碰到同一个真实目录，
        # 说明可能出现 symlink 循环。
        if real_path in ancestor_real_paths:
            return

        ancestor_real_paths.add(real_path)

        try:
            with os.scandir(current_path) as entries:

                for entry in entries:

                    try:
                        # follow_symlinks=True：
                        # 目录软链接也作为目录继续扫描。
                        if entry.is_dir(follow_symlinks=True):
                            is_link = entry.is_symlink()
                            if hasattr(entry, "is_junction"):
                                is_link = is_link or entry.is_junction()

                            # 普通子目录的真实路径可由父目录直接推导；
                            # 只有 symlink / junction 才调用 realpath。
                            # 真实 Community 中深层普通目录很多，这避免了
                            # 为每一层目录重复访问文件系统解析路径。
                            if is_link:
                                child_real_path = os.path.normcase(
                                    os.path.realpath(entry.path)
                                )
                            else:
                                child_real_path = os.path.normcase(
                                    os.path.join(real_path, entry.name)
                                )

                            scan_directory(
                                entry.path,
                                child_real_path
                            )

                            continue


                        if not entry.is_file(
                            follow_symlinks=True
                        ):
                            continue


                        actual_path = Path(entry.path)

                        # 这里保留 Package 内看到的“逻辑路径”，
                        # 而不是 resolve() 后的真实目标路径。
                        relative_path = (
                            actual_path
                            .relative_to(package_root)
                            .as_posix()
                        )

                        normalized_path = (
                            relative_path.casefold()
                        )

                        file_index[normalized_path] = {
                            "path": relative_path,
                            "size": entry.stat(
                                follow_symlinks=True
                            ).st_size
                        }

                    except OSError as e:
                        # 某个文件突然不可访问时，
                        # 不应导致整个 Community 扫描崩溃。
                        record_scan_error(entry.path, e)
                        continue

        except OSError as e:
            # 无权限、失效链接等目录级异常需要保留，后续不能把
            # 该目录中的未知文件误判为“确定缺失”。
            record_scan_error(current_path, e)
            return

        finally:
            ancestor_real_paths.remove(real_path)

    try:
        root_real_path = os.path.normcase(os.path.realpath(package_root))
    except OSError as e:
        record_scan_error(package_root, e)
    else:
        scan_directory(package_root, root_real_path)

    return file_index


def _path_covered_by_scan_error(normalized_path, scan_errors):
    """判断某个声明路径是否位于未能读取的文件或目录下。"""
    for error in scan_errors:
        error_path = (
            str(error.get("path", ""))
            .replace("\\", "/")
            .strip("/")
            .casefold()
        )
        if error_path in {"", "."}:
            return True
        if (
            normalized_path == error_path
            or normalized_path.startswith(f"{error_path}/")
        ):
            return True
    return False



def analyze_community_with_stats(addons, full_scan=False):
    """
    分析 scanner 返回的插件列表，并生成一致性问题列表。

    返回 (issues, AnalyzerStats)：
    - issues: 检测问题列表，details 中始终包含完整明细，
      preview 提供展示用的截断视图（最多 10 项）
    - AnalyzerStats: 内部各阶段耗时，仅用于性能分析，不改变检测结果

    full_scan=False:
        只检查 manifest / layout 的结构问题。

    full_scan=True:
        在快速扫描基础上，进一步检查实际文件是否缺失、
        文件大小是否与 layout.json 一致，以及是否存在未登记文件。
    """

    layout_parse_time = 0.0
    declared_check_time = 0.0
    tree_walk_time = 0.0
    package_timings = []

    issues = []

    for addon in addons:

        # === Manifest 基础字段检查 ===

        if not addon["name"]:
            issues.append(make_issue(
                "MANIFEST_MISSING_TITLE",
                "warning",
                addon["folder_name"],
                "manifest.json 缺少 title"
            ))

        if not addon["type"]:
            issues.append(make_issue(
                "MANIFEST_MISSING_CONTENT_TYPE",
                "warning",
                addon["folder_name"],
                "manifest.json 缺少 content_type"
            ))

        if not addon["version"]:
            issues.append(make_issue(
                "MANIFEST_MISSING_VERSION",
                "warning",
                addon["folder_name"],
                "manifest.json 缺少 package_version"
            ))

        # === Layout 读取 ===

        layout = Path(addon["path"]) / "layout.json"

        if not layout.exists():
            issues.append(make_issue(
                "LAYOUT_MISSING",
                "info",
                addon["folder_name"],
                "缺少 layout.json"
            ))
            continue

        parse_start = time.perf_counter()

        try:
            with open(layout, "r", encoding="utf-8-sig") as f:
                layout_data = json.load(f)

            if not isinstance(layout_data, dict):
                raise ValueError("layout.json 顶层必须是 JSON 对象")

        except Exception as e:
            # 即使解析失败，也把本次尝试计入 Layout 解析耗时。
            layout_parse_time += time.perf_counter() - parse_start

            issues.append(make_issue(
                "LAYOUT_INVALID",
                "error",
                addon["folder_name"],
                f"layout.json 无法解析：{e}"
            ))
            continue

        layout_parse_time += time.perf_counter() - parse_start

        # === Layout 数据结构检查 ===

        listed_paths = set()
        duplicate_paths = []
        invalid_entries = []
        valid_entries = []

        content = layout_data.get("content", [])

        if not isinstance(content, list):
            issues.append(make_issue(
                "LAYOUT_INVALID_ENTRY",
                "error",
                addon["folder_name"],
                "layout.json 的 content 不是列表"
            ))
            continue

        for index, file_info in enumerate(content):

            # 每个 layout 条目必须是 JSON 对象。
            if not isinstance(file_info, dict):
                invalid_entries.append({
                    "index": index,
                    "reason": "条目不是 JSON 对象"
                })
                continue

            relative_path = file_info.get("path")

            # path 必须是非空字符串，否则不能安全用于文件检查。
            if not isinstance(relative_path, str) or not relative_path.strip():
                invalid_entries.append({
                    "index": index,
                    "reason": "path 缺失或类型无效"
                })
                continue

            expected_size = file_info.get("size")

            # size 如果存在，必须是非负整数。
            # bool 在 Python 中属于 int 的子类，因此需要单独排除。
            if expected_size is not None:
                if (
                    not isinstance(expected_size, int)
                    or isinstance(expected_size, bool)
                    or expected_size < 0
                ):
                    invalid_entries.append({
                        "index": index,
                        "path": relative_path,
                        "reason": "size 不是有效的非负整数"
                    })
                    continue

            # 到这里说明该条目可以安全用于后续完整扫描。
            valid_entries.append(file_info)

            normalized_path = (
                relative_path
                .replace("\\", "/")
                .casefold()
            )

            if normalized_path in listed_paths:
                duplicate_paths.append(relative_path)
            else:
                listed_paths.add(normalized_path)

        if duplicate_paths:
            issues.append(make_issue(
                "LAYOUT_DUPLICATE_PATH",
                "warning",
                addon["folder_name"],
                f"layout.json 中发现 {len(duplicate_paths)} 个重复路径声明",
                duplicate_paths
            ))

        if invalid_entries:
            issues.append(make_issue(
                "LAYOUT_INVALID_ENTRY",
                "warning",
                addon["folder_name"],
                f"layout.json 中发现 {len(invalid_entries)} 个无效条目",
                invalid_entries
            ))

        # 快速扫描到这里结束，不读取整个插件文件树。
        if not full_scan:
            continue

        # === 完整扫描：核对 layout 声明文件 ===

        missing_files = []
        size_mismatches = []
        unlisted_files = []


        package_root = Path(addon["path"])


        # === 完整扫描：建立实际文件索引 ===

        tree_start = time.perf_counter()

        file_index_errors = []
        file_index = build_file_index(package_root, file_index_errors)

        package_tree_time = time.perf_counter() - tree_start
        tree_walk_time += package_tree_time
        package_timings.append({
            "package": addon["folder_name"],
            "tree_walk_time": package_tree_time,
            "file_count": len(file_index),
            "scan_error_count": len(file_index_errors),
        })


        # === 完整扫描：核对 layout 声明 ===

        declared_start = time.perf_counter()

        for file_info in valid_entries:

            relative_path = file_info["path"]

            normalized_path = (
                relative_path
                .replace("\\", "/")
                .casefold()
            )

            actual_file = file_index.get(normalized_path)

            # 索引里不存在，说明 layout 声明了文件，
            # 但实际 Package 中没有找到。
            if actual_file is None:
                if not _path_covered_by_scan_error(
                    normalized_path, file_index_errors
                ):
                    missing_files.append(relative_path)
                continue

            expected_size = file_info.get("size")
            actual_size = actual_file["size"]

            if (
                expected_size is not None
                and actual_size != expected_size
            ):
                size_mismatches.append({
                    "path": relative_path,
                    "expected": expected_size,
                    "actual": actual_size
                })

        declared_check_time += (
            time.perf_counter() - declared_start
        )

        # === 完整扫描：寻找未登记文件 ===
        # 这里不再访问磁盘，只遍历已经建立好的 file_index。
        for normalized_path, actual_file in file_index.items():

            # Package 元数据文件不要求登记在 layout.json 的 content 中。
            if normalized_path in {
                "manifest.json",
                "layout.json"
            }:
                continue

            if normalized_path not in listed_paths:
                # 操作系统 / 资源管理器自动生成的杂物文件不是插件内容，
                # 不把它们当作“未登记文件”报告，以减少误报噪音。
                if _is_os_junk(normalized_path):
                    continue

                unlisted_files.append(actual_file["path"])

        # === 生成完整扫描问题 ===

        if file_index_errors:
            issues.append(make_issue(
                "FILE_TREE_SCAN_INCOMPLETE",
                "warning",
                addon["folder_name"],
                f"有 {len(file_index_errors)} 个路径无法读取，文件检查不完整",
                file_index_errors
            ))

        if missing_files:
            issues.append(make_issue(
                "LAYOUT_FILE_MISSING",
                "error",
                addon["folder_name"],
                f"layout.json 声明的 {len(missing_files)} 个文件不存在",
                missing_files
            ))

        if size_mismatches:
            issues.append(make_issue(
                "LAYOUT_FILE_SIZE_MISMATCH",
                "warning",
                addon["folder_name"],
                f"发现 {len(size_mismatches)} 个文件大小与 layout.json 不一致",
                size_mismatches
            ))

        if unlisted_files:
            issues.append(make_issue(
                "LAYOUT_UNLISTED_FILE",
                "info",
                addon["folder_name"],
                f"发现 {len(unlisted_files)} 个文件未列入 layout.json",
                unlisted_files
            ))

    stats = AnalyzerStats(
        layout_parse_time=layout_parse_time,
        declared_check_time=declared_check_time,
        tree_walk_time=tree_walk_time,
        addon_count=len(addons),
        package_timings=sorted(
            package_timings,
            key=lambda item: item["tree_walk_time"],
            reverse=True,
        ),
    )

    return issues, stats


def analyze_community(addons, full_scan=False):
    """
    兼容入口：只返回问题列表，不返回性能统计。

    新代码建议使用 analyze_community_with_stats()。
    三项耗时之和不一定等于 Analyzer 总耗时，因为还有结构检查、
    Path 对象创建、结果聚合等未单独计时的工作。
    """
    issues, _stats = analyze_community_with_stats(
        addons, full_scan=full_scan
    )
    return issues
