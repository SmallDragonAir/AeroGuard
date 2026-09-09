from pathlib import PurePosixPath

from i18n import tr


# 明确属于文档、安装辅助或构建工具的文件。
# 缺失这些文件通常不会直接影响插件在 MSFS 中运行。
LIKELY_NON_RUNTIME_FILES = {
    "msfslayoutgenerator.exe",
    "readme.md",
    "readme.txt",
    "how_to_install.txt",
    "changelog.md",
    "changelog.txt",
    "license.md",
    "license.txt",
    ".keep",
    "gen.bat",
}

# 说明文档类扩展名。
# 命中它们通常意味着文件只用于阅读，不参与模拟器运行。
DOCUMENTATION_EXTENSIONS = {
    ".md",
    ".markdown",
    ".rtf",
}

# 常见说明文档目录名。
# 位于这些目录下的文件更可能只是文档。
NON_RUNTIME_DIR_PARTS = {
    "documentation",
    "docs",
}

# 常见的运行时资源扩展名。
# 命中这里只代表“可能参与运行”，不代表插件一定损坏。
POTENTIALLY_RUNTIME_EXTENSIONS = {
    ".wasm",
    ".bgl",
    ".hvar",
    ".cfg",
    ".xml",
    ".js",
    ".mjs",
    ".html",
    ".css",
    ".spb",
    ".fx",
    # 模型与贴图资源
    ".gltf",
    ".glb",
    ".mdl",
    ".dds",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tga",
    # 音频资源
    ".wav",
    ".flac",
    ".ogg",
}

# MSFS / 插件的标准运行时结构目录。
# 位于这些目录下的文件更可能参与运行。
RUNTIME_DIR_PARTS = {
    "simobjects",
    "effects",
    "html_ui",
    "modelbehaviordefs",
    "vcockpit",
}


def classify_file_path(file_path):
    """
    根据文件路径和名称，估计它对插件运行的潜在影响。

    impact:
    - potentially_runtime: 可能参与插件或模拟器运行
    - likely_non_runtime: 很可能只是文档、构建或安装辅助文件
    - unknown: 当前规则无法可靠判断

    注意：
    这里只进行启发式分类，不代表插件一定存在运行故障。
    """

    normalized_path = file_path.replace("\\", "/")
    path = PurePosixPath(normalized_path)

    file_name = path.name.casefold()
    clean_file_name = file_name.lstrip(".")
    extension = path.suffix.casefold()

    path_parts = {
        part.casefold()
        for part in path.parts
    }

    # 已知说明文档、打包工具和安装辅助文件。
    # 必须优先判断，防止 Config/README.txt 被误判为运行配置。
    if clean_file_name in LIKELY_NON_RUNTIME_FILES:
        return {
            "impact": "likely_non_runtime",
            "reason": tr("classify.docs.build_tool")
        }

    # 说明文档类扩展名或文档目录。
    if extension in DOCUMENTATION_EXTENSIONS:
        return {
            "impact": "likely_non_runtime",
            "reason": tr("classify.docs.extension")
        }

    if path_parts & NON_RUNTIME_DIR_PARTS:
        return {
            "impact": "likely_non_runtime",
            "reason": tr("classify.docs.directory")
        }

    # 部分 WASM 相关资源使用复合扩展名，
    # 例如 MSFS_ToLiss_Plugin.wasm.id0。
    # Path.suffix 只能得到 .id0，因此额外检查文件名。
    if ".wasm." in file_name:
        return {
            "impact": "potentially_runtime",
            "reason": tr("classify.wasm.composite")
        }

    # 常见 MSFS / 插件运行资源。
    if extension in POTENTIALLY_RUNTIME_EXTENSIONS:
        return {
            "impact": "potentially_runtime",
            "reason": tr("classify.ext.runtime", extension=extension)
        }

    # 标准运行时结构目录（SimObjects / effects / html_ui 等）。
    if path_parts & RUNTIME_DIR_PARTS:
        return {
            "impact": "potentially_runtime",
            "reason": tr("classify.dir.runtime")
        }

    # 不能简单认为 .txt 都是说明文档。
    # 部分插件会在 Config 目录中使用文本文件作为运行配置。
    if (
        "config" in path_parts
        or "configs" in path_parts
        or "configuration" in path_parts
    ):
        return {
            "impact": "potentially_runtime",
            "reason": tr("classify.config.runtime")
        }

    # 没有充分依据时保持 unknown，宁可不判，也不要乱判。
    return {
        "impact": "unknown",
        "reason": tr("classify.unknown")
    }


# 需要对文件逐条分类的规则。
# 这些规则的 details 中保存的是“文件路径或带 path 字段的条目”。
FILE_LEVEL_RULES = {
    "LAYOUT_FILE_MISSING",
    "LAYOUT_FILE_SIZE_MISMATCH",
    "LAYOUT_UNLISTED_FILE",
}


def _entry_path(entry):
    """details 中的条目可能是纯字符串，也可能是带 path 键的字典。"""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        path = entry.get("path")
        if isinstance(path, str):
            return path
    return None


def classify_issues(issues):
    """
    对 Analyzer 产生的 issue 列表进行潜在运行影响分类。

    对 details 中带文件路径的规则（缺失文件、大小不一致、
    未登记文件），逐条基于完整明细分类后聚合；
    其余规则暂时保持 unknown。
    """

    for issue in issues:

        if issue["rule_id"] not in FILE_LEVEL_RULES:
            issue["impact"] = "unknown"
            continue

        classified_files = []

        for entry in issue.get("details", []):
            file_path = _entry_path(entry)

            if file_path is None:
                continue

            result = classify_file_path(file_path)

            classified_files.append({
                "path": file_path,
                "impact": result["impact"],
                "reason": result["reason"]
            })

        issue["classified_files"] = classified_files

        # 一个 Package 中只要存在潜在运行文件，
        # 整个 issue 就优先视为 potentially_runtime。
        impacts = {
            item["impact"]
            for item in classified_files
        }

        if not impacts:
            issue["impact"] = "unknown"

        elif "potentially_runtime" in impacts:
            issue["impact"] = "potentially_runtime"

        elif "unknown" in impacts:
            issue["impact"] = "unknown"

        else:
            issue["impact"] = "likely_non_runtime"

    return issues
