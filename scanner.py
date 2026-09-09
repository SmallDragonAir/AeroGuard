import json
from pathlib import Path


def scan_community(path):
    """
    发现 Community 文件夹中的插件包并读取基础元数据。

    返回 (addons, scan_errors)：
    - addons: 每个元素是包含 manifest 基础字段的字典，
      其中 manifest 保留解析后的原始 JSON，供后续
      依赖分析等功能读取完整字段。
    - scan_errors: manifest.json 存在但无法解析的条目。

    只做只读扫描，不会修改任何插件文件。
    """
    community_path = Path(path)

    addons = []
    scan_errors = []

    for addon in community_path.iterdir():

        if not addon.is_dir():
            continue

        manifest = addon / "manifest.json"

        if not manifest.exists():
            continue

        try:
            with open(manifest, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("manifest.json 顶层必须是 JSON 对象")

        except Exception as e:
            scan_errors.append({
                "package": addon.name,
                "path": str(addon),
                "error": str(e),
            })
            continue

        addons.append({
            "folder_name": addon.name,
            "name": data.get("title"),
            "type": data.get("content_type"),
            "creator": data.get("creator"),
            "version": data.get("package_version"),
            "path": str(addon),
            "manifest": data,
        })

    return addons, scan_errors
