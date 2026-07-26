from pathlib import PurePosixPath


# 明确属于文档、安装辅助或构建工具的文件。
# 缺失这些文件通常不会直接影响插件在 MSFS 中运行。
LIKELY_NON_RUNTIME_FILES = {
    "msfslayoutgenerator.exe",
    "readme.md",
    "readme.txt",
    "how_to_install.txt",
    ".keep",
    "gen.bat",
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
    ".html",
    ".css",
    ".spb",
}





def classify_file_path(file_path):
    """
    根据缺失文件的路径和名称，估计它对插件运行的潜在影响。

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
            "reason": "看起来属于说明文件、构建工具或打包辅助文件"
        }

    # 部分 WASM 相关资源使用复合扩展名，
    # 例如 MSFS_ToLiss_Plugin.wasm.id0。
    # Path.suffix 只能得到 .id0，因此额外检查文件名。
    if ".wasm." in file_name:
        return {
            "impact": "potentially_runtime",
            "reason": "文件名表明它与 WASM 模块相关"
        }

    # 常见 MSFS / 插件运行资源。
    if extension in POTENTIALLY_RUNTIME_EXTENSIONS:
        return {
            "impact": "potentially_runtime",
            "reason": f"{extension} 文件可能参与模拟器或插件运行"
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
            "reason": "文件位于配置目录中，可能参与插件运行"
        }

    # 没有充分依据时保持 unknown，宁可不判，也不要乱判。
    return {
        "impact": "unknown",
        "reason": "目前没有足够信息判断该文件是否影响运行"
    }



def classify_issues(issues):
    """
    对 Analyzer 产生的 issue 列表进行潜在运行影响分类。

    当前只对 LAYOUT_FILE_MISSING 进行具体分类。
    其他规则暂时保持 unknown。
    """

    for issue in issues:

        # 当前 classifier 只处理缺失文件规则。
        if issue["rule_id"] != "LAYOUT_FILE_MISSING":
            issue["impact"] = "unknown"
            continue

        classified_files = []

        # 对该 issue 中记录的每个缺失文件分别进行分类。
        for file_path in issue.get("details", []):
            result = classify_file_path(file_path)

            classified_files.append({
                "path": file_path,
                "impact": result["impact"],
                "reason": result["reason"]
            })

        issue["classified_files"] = classified_files

        # 一个 Package 中只要存在潜在运行文件，
        # 整个 issue 就优先视为 potentially_runtime。
        impacts = [
            item["impact"]
            for item in classified_files
        ]

        if "potentially_runtime" in impacts:
            issue["impact"] = "potentially_runtime"

        elif "unknown" in impacts:
            issue["impact"] = "unknown"

        else:
            issue["impact"] = "likely_non_runtime"

    return issues