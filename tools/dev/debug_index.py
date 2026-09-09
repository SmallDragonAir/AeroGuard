import sys
import json
from pathlib import Path

# 允许从任意工作目录运行：python tools/dev/debug_index.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from analyzer import build_file_index


PACKAGE_ROOT = Path(
    r"D:\MSFS2024_DATA\Community\fsl-a32x"
)

layout_path = PACKAGE_ROOT / "layout.json"

with open(layout_path, "r", encoding="utf-8-sig") as f:
    layout_data = json.load(f)


print("正在建立文件索引……")
file_index = build_file_index(PACKAGE_ROOT)

print("索引文件数：", len(file_index))


missing = []

for file_info in layout_data.get("content", []):
    relative_path = file_info.get("path")

    if not isinstance(relative_path, str):
        continue

    normalized_path = (
        relative_path
        .replace("\\", "/")
        .casefold()
    )

    if normalized_path not in file_index:
        direct_path = PACKAGE_ROOT / relative_path

        missing.append({
            "path": relative_path,
            "exists": direct_path.exists(),
            "is_file": direct_path.is_file()
        })


print("索引判定缺失：", len(missing))

print("\n前 10 个：")

for item in missing[:10]:
    print(
        item["path"],
        "| exists =", item["exists"],
        "| is_file =", item["is_file"]
    )