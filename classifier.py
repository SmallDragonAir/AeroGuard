from pathlib import PurePosixPath


LIKELY_NON_RUNTIME_FILES = {
    "msfslayoutgenerator.exe",
    "readme.md",
    "readme.txt",
    "how_to_install.txt",
    ".keep",
    "gen.bat",
}


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
    normalized_path = file_path.replace("\\", "/")
    path = PurePosixPath(normalized_path)

    file_name = path.name.casefold()
    extension = path.suffix.casefold()

    if file_name in LIKELY_NON_RUNTIME_FILES:
        return {
            "impact": "likely_non_runtime",
            "reason": "看起来属于说明文件、构建工具或打包辅助文件"
        }

    if extension in POTENTIALLY_RUNTIME_EXTENSIONS:
        return {
            "impact": "potentially_runtime",
            "reason": f"{extension} 文件可能参与模拟器或插件运行"
        }

    return {
        "impact": "unknown",
        "reason": "目前没有足够信息判断该文件是否影响运行"
    }


def classify_issues(issues):
    for issue in issues:

        if issue["rule_id"] != "LAYOUT_FILE_MISSING":
            issue["impact"] = "unknown"
            continue

        classified_files = []

        for file_path in issue.get("details", []):
            result = classify_file_path(file_path)

            classified_files.append({
                "path": file_path,
                "impact": result["impact"],
                "reason": result["reason"]
            })

        issue["classified_files"] = classified_files
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