"""测试用的合成 Community fixture 构造工具。

所有插件都建立在临时目录中，不触碰真实 Community。
"""

import json
from pathlib import Path


DEFAULT_MANIFEST = {
    "title": "Test Addon",
    "content_type": "AIRCRAFT",
    "creator": "fixture",
    "package_version": "1.0.0",
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def make_addon(community, folder_name, manifest=None,
               layout_content=None, files=None):
    """
    在 community 下创建一个完整插件目录。

    - manifest: dict，覆盖 DEFAULT_MANIFEST 的字段；
      None 表示写默认 manifest；False 表示不写 manifest。
    - layout_content: layout.json 的 content 列表；
      None 表示不写 layout.json。
    - files: {相对路径: 文件内容(bytes 或 str)}。
    """
    addon_dir = Path(community) / folder_name
    addon_dir.mkdir(parents=True, exist_ok=True)

    if manifest is not False:
        manifest_data = dict(DEFAULT_MANIFEST)
        if manifest:
            manifest_data.update(manifest)
        write_json(addon_dir / "manifest.json", manifest_data)

    if layout_content is not None:
        write_json(addon_dir / "layout.json", {"content": layout_content})

    for rel_path, content in (files or {}).items():
        target = addon_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        target.write_bytes(content)

    return addon_dir


def make_file(root, rel_path, content=b"content"):
    """在已有插件目录下直接写一个文件，返回其大小。"""
    target = Path(root) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return len(content)
