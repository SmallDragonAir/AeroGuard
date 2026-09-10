"""本地规则覆盖（overrides）存储 —— 按 (插件, 规则) 忽略或降级扫描结果。

与 notes 一样完全本地：记录用户对"某插件的某条规则"的处理决定，
扫描时由 knowledge.apply_known_context 应用。数据存放于
<state_root>/overrides/overrides.json。
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


OVERRIDES_SCHEMA_VERSION = 1
ALLOWED_ACTIONS = ("ignore", "downgrade")
MAX_RULE_ID_LENGTH = 64
MAX_REASON_LENGTH = 2000


class OverrideStoreError(RuntimeError):
    """覆盖数据无法安全读取或写入。"""


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_override_id():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _write_json_atomic(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
    temporary.replace(path)


def _read_json_object(path, label):
    try:
        with open(path, "r", encoding="utf-8") as file:
            document = json.load(file)
    except OSError as error:
        raise OverrideStoreError(f"无法读取{label}：{error}") from error
    except ValueError as error:
        raise OverrideStoreError(f"{label}不是有效的 JSON：{error}") from error
    if not isinstance(document, dict):
        raise OverrideStoreError(f"{label}必须是 JSON 对象")
    return document


def _valid_package_name(name):
    name = name.strip()
    if (
        not name
        or name in {".", ".."}
        or any(character in name for character in "/\\")
        or any(ord(character) < 32 for character in name)
    ):
        raise OverrideStoreError(f"包名无效：{name!r}")
    return name


def _valid_rule_id(rule_id):
    rule_id = rule_id.strip()
    if not rule_id or len(rule_id) > MAX_RULE_ID_LENGTH:
        raise OverrideStoreError("rule_id 缺失或过长")
    return rule_id


class OverrideStore:
    """按 (包, 规则) 保存忽略 / 降级决定，支持查询与删除。"""

    def __init__(self, community_path, state_root=None):
        community = Path(community_path).expanduser().resolve()
        if not community.is_dir():
            raise OverrideStoreError(
                f"Community 路径不存在或不是目录：{community}"
            )
        state = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else (community.parent / ".aeroguard").resolve()
        )
        if state == community or state.is_relative_to(community):
            raise OverrideStoreError("状态目录必须位于 Community 之外")
        self.community = community
        self.state_root = state
        self.overrides_path = state / "overrides" / "overrides.json"

    def _load(self):
        if not self.overrides_path.exists():
            return []
        document = _read_json_object(self.overrides_path, "覆盖记录")
        overrides = document.get("overrides")
        if not isinstance(overrides, list):
            raise OverrideStoreError("覆盖记录文件中的 overrides 必须是列表")
        return overrides

    def _save(self, overrides):
        document = {
            "schema_version": OVERRIDES_SCHEMA_VERSION,
            "community_path": str(self.community),
            "overrides": overrides,
        }
        _write_json_atomic(self.overrides_path, document)

    def add(self, package, rule, action, reason=None):
        """添加一条覆盖；同一 (包, 规则) 已存在则拒绝（需先删除）。"""
        package = _valid_package_name(package)
        rule = _valid_rule_id(rule).upper()
        action = str(action).strip().lower()
        if action not in ALLOWED_ACTIONS:
            raise OverrideStoreError(
                f"action 必须是其中之一：{', '.join(ALLOWED_ACTIONS)}"
            )
        if reason is not None and (
            not isinstance(reason, str) or len(reason) > MAX_REASON_LENGTH
        ):
            raise OverrideStoreError("reason 无效或过长")

        overrides = self._load()
        for existing in overrides:
            if (
                str(existing.get("package", "")).casefold() == package.casefold()
                and str(existing.get("rule_id", "")).upper() == rule
            ):
                raise OverrideStoreError(
                    f"同一 (包, 规则) 已有覆盖：{package} / {rule}"
                )

        record = {
            "id": _new_override_id(),
            "package": package,
            "rule_id": rule,
            "action": action,
            "reason": (reason.strip() if reason else None),
            "created_at": _now_utc(),
        }
        overrides.append(record)
        self._save(overrides)
        return record

    def remove(self, override_id):
        if not isinstance(override_id, str) or not override_id.strip():
            raise OverrideStoreError("override id 无效")
        overrides = self._load()
        remaining = []
        removed = None
        for record in overrides:
            if record.get("id") == override_id:
                removed = record
            else:
                remaining.append(record)
        if removed is None:
            raise OverrideStoreError(f"未找到覆盖记录：{override_id}")
        self._save(remaining)
        return removed

    def list(self, package=None, rule=None):
        """列出全部或按包（大小写不敏感）/规则筛选的覆盖。"""
        overrides = self._load()
        if package is not None:
            wanted = _valid_package_name(package).casefold()
            overrides = [
                record for record in overrides
                if str(record.get("package", "")).casefold() == wanted
            ]
        if rule is not None:
            wanted_rule = _valid_rule_id(rule).upper()
            overrides = [
                record for record in overrides
                if str(record.get("rule_id", "")).upper() == wanted_rule
            ]
        return {
            "community_path": str(self.community),
            "count": len(overrides),
            "overrides": sorted(
                overrides,
                key=lambda record: (
                    str(record.get("package", "")).casefold(),
                    str(record.get("rule_id", "")),
                    record.get("id", ""),
                ),
            ),
        }
