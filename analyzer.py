import json
from pathlib import Path

def analyze_community(addons, full_scan=False):

    issues = []

    for addon in addons:

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

        layout = Path(addon["path"]) / "layout.json"

        if not layout.exists():
            issues.append({
                "rule_id": "LAYOUT_MISSING",
                "severity": "info",
                "package": addon["folder_name"],
                "message": "缺少 layout.json"
    })

            continue

        try:
            with open(layout, "r", encoding="utf-8-sig") as f:
                layout_data = json.load(f)

        except Exception as e:
            issues.append({
                "rule_id": "LAYOUT_INVALID",
                "severity": "error",
                "package": addon["folder_name"],
                "message": f"layout.json 无法解析：{e}"
            })

            continue

 

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

            # 条目本身必须是一个字典
            if not isinstance(file_info, dict):
                invalid_entries.append({
                    "index": index,
                    "reason": "条目不是 JSON 对象"
                })
                continue

            relative_path = file_info.get("path")

            # path 必须是非空字符串
            if not isinstance(relative_path, str) or not relative_path.strip():
                invalid_entries.append({
                    "index": index,
                    "reason": "path 缺失或类型无效"
                })
                continue

            expected_size = file_info.get("size")

            # size 如果存在，必须是非负整数
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

            # 到这里说明该条目能安全使用
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
        

        if not full_scan:
            continue
        
        missing_files = []
        size_mismatches = []
        unlisted_files = []

        for file_info in valid_entries:

            relative_path = file_info.get("path")

            if not relative_path:
                continue

            actual_path = Path(addon["path"]) / relative_path

            if not actual_path.exists():
                missing_files.append(relative_path)
                continue

            expected_size = file_info.get("size")
            actual_size = actual_path.stat().st_size

            if expected_size is not None and actual_size != expected_size:
                size_mismatches.append({
                    "path": relative_path,
                    "expected": expected_size,
                    "actual": actual_size
                })


        package_root = Path(addon["path"])

        for actual_file in package_root.rglob("*"):

            if not actual_file.is_file():
                continue

            relative_path = actual_file.relative_to(package_root).as_posix()
            normalized_path = relative_path.casefold()

            if normalized_path in {
                "manifest.json",
                "layout.json"
            }:
                continue

            if normalized_path not in listed_paths:
                unlisted_files.append(relative_path)


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

        
        
    
    return issues