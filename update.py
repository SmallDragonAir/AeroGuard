"""检查 AeroGuard 自身是否有新版本。

设计原则：
- 只在用户**显式**触发时联网（CLI --check-update / GUI「检查更新」按钮）；
  扫描与管理流程保持零网络行为。
- 只读取 GitHub Releases 的公开信息，不下载、不替换任何文件；
  更新方式由用户自行决定（平台页面 / 发布页）。

测试通过注入 fetch 函数避免真实联网。
"""

import json
import urllib.error
import urllib.request

from version import VERSION


GITHUB_API = (
    "https://api.github.com/repos/SmallDragonAir/AeroGuard/releases/latest"
)
RELEASES_PAGE = "https://github.com/SmallDragonAir/AeroGuard/releases"
DEFAULT_TIMEOUT = 6.0
MAX_RESPONSE_BYTES = 512 * 1024
NOTES_EXCERPT_LENGTH = 600


class UpdateError(RuntimeError):
    """检查更新失败（网络或响应格式问题）。"""


def parse_version(text):
    """把 'v1.2.3' / '1.2.3-beta' 解析为可比较的数字元组。"""
    if not isinstance(text, str):
        return ()
    cleaned = text.strip().lstrip("vV")
    numbers = []
    current = ""
    for character in cleaned:
        if character.isdigit():
            current += character
        else:
            if character == "." or current:
                if current:
                    numbers.append(int(current))
                current = ""
                if character not in ".-_+":
                    break
            else:
                break
    if current:
        numbers.append(int(current))
    while numbers and len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def compare_versions(left, right):
    """比较版本：left > right 返回 1，相等 0，小于 -1。"""
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    if not left_parts or not right_parts:
        return 0
    length = max(len(left_parts), len(right_parts))
    for index in range(length):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value > right_value:
            return 1
        if left_value < right_value:
            return -1
    return 0


def _default_fetch(url, timeout=DEFAULT_TIMEOUT):
    """读取 GitHub Releases API 的 JSON（只读、限量）。"""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"AeroGuard/{VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES)
    return json.loads(raw.decode("utf-8", errors="replace"))


def check_for_update(current=None, fetch=None, timeout=DEFAULT_TIMEOUT):
    """返回更新检查结果字典；失败抛 UpdateError。"""
    current_version = current or VERSION
    fetcher = fetch or _default_fetch

    try:
        payload = fetcher(GITHUB_API, timeout=timeout)
    except UpdateError:
        raise
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
        raise UpdateError(f"无法连接更新服务：{error}") from error
    except Exception as error:  # 注入的 fetch 可能抛任意异常
        raise UpdateError(f"检查更新失败：{error}") from error

    if not isinstance(payload, dict):
        raise UpdateError("更新服务返回的内容不是 JSON 对象")

    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        raise UpdateError("更新服务返回的版本标签无效")
    tag = tag.strip()

    release_name = payload.get("name")
    if not isinstance(release_name, str) or not release_name.strip():
        release_name = None
    else:
        release_name = release_name.strip()

    # 优先使用 tag，其次 release 名称；两者都无法解析出数字版本时，
    # 明确标记为"无法比较"，而不是误报"已是最新版本"。
    candidates = [tag]
    if release_name:
        candidates.append(release_name)
    usable = [
        candidate for candidate in candidates
        if parse_version(candidate)
    ]
    current_parsable = bool(parse_version(current_version))
    version_comparable = bool(usable) and current_parsable

    if version_comparable:
        latest_version = usable[0].lstrip("vV")
        update_available = compare_versions(
            latest_version, current_version
        ) > 0
    else:
        latest_version = tag.lstrip("vV")
        update_available = False

    release_url = payload.get("html_url")
    if not isinstance(release_url, str) or not release_url.strip():
        release_url = RELEASES_PAGE

    notes = payload.get("body")
    notes_excerpt = ""
    if isinstance(notes, str):
        notes_excerpt = notes.strip()[:NOTES_EXCERPT_LENGTH]

    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "tag": tag,
        "version_comparable": version_comparable,
        "update_available": update_available,
        "release_name": release_name,
        "published_at": payload.get("published_at")
        if isinstance(payload.get("published_at"), str) else None,
        "release_url": release_url.strip(),
        "notes_excerpt": notes_excerpt,
        "downloaded": False,
    }
