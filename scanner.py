import json
from pathlib import Path

def scan_community(path):
    community_path = Path(path)

    addons = []
    scan_error = []

    for addon in community_path.iterdir():

        if not addon.is_dir():
            continue

        manifest = addon / "manifest.json"

        if not manifest.exists():
            continue
    
        try:
            with open(manifest, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

        except Exception as e:
            error_info = {
            "package": addon.name,
            "path": str(addon),
            "error": str(e)
        }
            scan_error.append(error_info)
            continue

        addon_info = {
            "folder_name": addon.name,
            "name": data.get("title"),
            "type": data.get("content_type"),
            "creator": data.get("creator"),
            "version": data.get("package_version"),
            "path": str(addon)
        }
        addons.append(addon_info)

    return addons,scan_error