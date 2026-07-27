import os
import time
import json
from pathlib import Path



def build_file_index(package_root):
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


    def scan_directory(current_path, ancestor_real_paths):
        # resolve() 用于判断当前目录真实指向哪里，
        # 只用于防止 symlink 循环。
        try:
            real_path = os.path.normcase(
                os.path.realpath(current_path)
            )
        except OSError:
            return

        # 当前递归链中再次碰到同一个真实目录，
        # 说明可能出现 symlink 循环。
        if real_path in ancestor_real_paths:
            return

        current_ancestors = (
            ancestor_real_paths | {real_path}
        )

        try:
            with os.scandir(current_path) as entries:

                for entry in entries:

                    try:
                        # follow_symlinks=True：
                        # 目录软链接也作为目录继续扫描。
                        if entry.is_dir(follow_symlinks=True):

                            scan_directory(
                                entry.path,
                                current_ancestors
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

                    except OSError:
                        # 某个文件突然不可访问时，
                        # 不应导致整个 Community 扫描崩溃。
                        continue

        except OSError:
            # 无权限、失效链接等目录级异常暂时跳过。
            return


    scan_directory(package_root, set())

    return file_index



def analyze_community(addons, full_scan=False):
    """
    分析 scanner 返回的插件列表，并生成一致性问题列表。

    full_scan=False:
        只检查 manifest / layout 的结构问题。

    full_scan=True:
        在快速扫描基础上，进一步检查实际文件是否缺失、
        文件大小是否与 layout.json 一致，以及是否存在未登记文件。

    性能统计仅用于当前开发阶段定位瓶颈，不改变检测结果。
    """

    layout_parse_time = 0.0
    declared_check_time = 0.0
    tree_walk_time = 0.0

    issues = []

    for addon in addons:

        # === Manifest 基础字段检查 ===

        if not addon["name"]:
            issues.append({
                "rule_id": "MANIFEST_MISSING_TITLE",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": "manifest.json 缺少 title"
            })

        if not addon["type"]:
            issues.append({
                "rule_id": "MANIFEST_MISSING_CONTENT_TYPE",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": "manifest.json 缺少 content_type"
            })

        if not addon["version"]:
            issues.append({
                "rule_id": "MANIFEST_MISSING_VERSION",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": "manifest.json 缺少 package_version"
            })

        # === Layout 读取 ===

        layout = Path(addon["path"]) / "layout.json"

        if not layout.exists():
            issues.append({
                "rule_id": "LAYOUT_MISSING",
                "severity": "info",
                "package": addon["folder_name"],
                "message": "缺少 layout.json"
            })
            continue

        parse_start = time.perf_counter()

        try:
            with open(layout, "r", encoding="utf-8-sig") as f:
                layout_data = json.load(f)

        except Exception as e:
            # 即使解析失败，也把本次尝试计入 Layout 解析耗时。
            layout_parse_time += time.perf_counter() - parse_start

            issues.append({
                "rule_id": "LAYOUT_INVALID",
                "severity": "error",
                "package": addon["folder_name"],
                "message": f"layout.json 无法解析：{e}"
            })
            continue

        layout_parse_time += time.perf_counter() - parse_start

        # === Layout 数据结构检查 ===

        listed_paths = set()
        duplicate_paths = []
        invalid_entries = []
        valid_entries = []

        content = layout_data.get("content", [])

        if not isinstance(content, list):
            issues.append({
                "rule_id": "LAYOUT_INVALID_ENTRY",
                "severity": "error",
                "package": addon["folder_name"],
                "message": "layout.json 的 content 不是列表"
            })
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
            issues.append({
                "rule_id": "LAYOUT_DUPLICATE_PATH",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": f"layout.json 中发现 {len(duplicate_paths)} 个重复路径声明",
                "affected_count": len(duplicate_paths),
                "details": duplicate_paths[:10]
            })

        if invalid_entries:
            issues.append({
                "rule_id": "LAYOUT_INVALID_ENTRY",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": f"layout.json 中发现 {len(invalid_entries)} 个无效条目",
                "affected_count": len(invalid_entries),
                "details": invalid_entries[:10]
            })

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

        file_index = build_file_index(package_root)

        tree_walk_time += time.perf_counter() - tree_start


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
                unlisted_files.append(actual_file["path"])

        # === 生成完整扫描问题 ===

        if missing_files:
            issues.append({
                "rule_id": "LAYOUT_FILE_MISSING",
                "severity": "error",
                "package": addon["folder_name"],
                "message": f"layout.json 声明的 {len(missing_files)} 个文件不存在",
                "affected_count": len(missing_files),
                "details": missing_files[:10]
            })

        if size_mismatches:
            issues.append({
                "rule_id": "LAYOUT_FILE_SIZE_MISMATCH",
                "severity": "warning",
                "package": addon["folder_name"],
                "message": f"发现 {len(size_mismatches)} 个文件大小与 layout.json 不一致",
                "affected_count": len(size_mismatches),
                "details": size_mismatches[:10]
            })

        if unlisted_files:
            issues.append({
                "rule_id": "LAYOUT_UNLISTED_FILE",
                "severity": "info",
                "package": addon["folder_name"],
                "message": f"发现 {len(unlisted_files)} 个文件未列入 layout.json",
                "affected_count": len(unlisted_files),
                "details": unlisted_files[:10]
            })

    # 当前用于开发阶段性能分析。
    # 三项之和不一定等于 Analyzer 总耗时，因为还有结构检查、
    # Path 对象创建、结果聚合等未单独计时的工作。
    print("\n=== Analyzer 内部性能 ===")
    print("Layout 解析：", round(layout_parse_time, 2), "秒")
    print("声明文件检查：", round(declared_check_time, 2), "秒")
    print("文件树遍历：", round(tree_walk_time, 2), "秒")

    return issues
