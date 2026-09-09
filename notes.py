"""本地已知结论（notes）存储 —— 已知异常数据库的纯本地雏形。

把用户对"某个插件 + 某条规则"的人工结论（例如"该差异由自更新器
导致，可忽略"）记录在管理状态目录中。只做本地记录与查询，
不联网、不参与扫描判断；后续在线知识库可按同一数据结构演进。

存储文件：<state_root>/notes/notes.json
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


NOTES_SCHEMA_VERSION = 1
MAX_NOTE_TEXT_LENGTH = 2000
MAX_RULE_ID_LENGTH = 64


class NoteStoreError(RuntimeError):
    """笔记数据无法安全读取或写入。"""


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_note_id():
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
        raise NoteStoreError(f"无法读取{label}：{error}") from error
    except ValueError as error:
        raise NoteStoreError(f"{label}不是有效的 JSON：{error}") from error
    if not isinstance(document, dict):
        raise NoteStoreError(f"{label}必须是 JSON 对象")
    return document


def _valid_package_name(name):
    """包名只允许作为目录叶名称出现，禁止路径分隔符。"""
    name = name.strip()
    if (
        not name
        or name in {".", ".."}
        or any(character in name for character in "/\\")
        or any(ord(character) < 32 for character in name)
    ):
        raise NoteStoreError(f"包名无效：{name!r}")
    return name


class NoteStore:
    """按包（可选按规则）记录与查询人工结论。"""

    def __init__(self, community_path, state_root=None):
        community = Path(community_path).expanduser().resolve()
        if not community.is_dir():
            raise NoteStoreError(
                f"Community 路径不存在或不是目录：{community}"
            )
        state = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else (community.parent / ".aeroguard").resolve()
        )
        if state == community or state.is_relative_to(community):
            raise NoteStoreError("状态目录必须位于 Community 之外")
        self.community = community
        self.state_root = state
        self.notes_path = state / "notes" / "notes.json"

    def _load(self):
        if not self.notes_path.exists():
            return []
        document = _read_json_object(self.notes_path, "结论记录")
        notes = document.get("notes")
        if not isinstance(notes, list):
            raise NoteStoreError("结论记录文件中的 notes 必须是列表")
        return notes

    def _save(self, notes):
        document = {
            "schema_version": NOTES_SCHEMA_VERSION,
            "community_path": str(self.community),
            "notes": notes,
        }
        _write_json_atomic(self.notes_path, document)

    def add(self, package, text, rule_id=None):
        """添加一条结论，返回新记录。"""
        package = _valid_package_name(package)
        if not isinstance(text, str) or not text.strip():
            raise NoteStoreError("结论文本不能为空")
        if len(text) > MAX_NOTE_TEXT_LENGTH:
            raise NoteStoreError(
                f"结论文本过长（{len(text)} > {MAX_NOTE_TEXT_LENGTH}）"
            )
        if rule_id is not None:
            if (
                not isinstance(rule_id, str)
                or not rule_id.strip()
                or len(rule_id) > MAX_RULE_ID_LENGTH
            ):
                raise NoteStoreError("rule_id 无效或过长")
            rule_id = rule_id.strip()

        notes = self._load()
        note = {
            "id": _new_note_id(),
            "package": package,
            "rule_id": rule_id,
            "text": text.strip(),
            "source": "manual",
            "created_at": _now_utc(),
        }
        notes.append(note)
        self._save(notes)
        return note

    def remove(self, note_id):
        """删除一条结论，返回被删除的记录。"""
        if not isinstance(note_id, str) or not note_id.strip():
            raise NoteStoreError("note id 无效")
        notes = self._load()
        remaining = []
        removed = None
        for note in notes:
            if note.get("id") == note_id:
                removed = note
            else:
                remaining.append(note)
        if removed is None:
            raise NoteStoreError(f"未找到结论记录：{note_id}")
        self._save(remaining)
        return removed

    def list(self, package=None):
        """列出全部或某个包（大小写不敏感）的结论。"""
        notes = self._load()
        if package is not None:
            wanted = _valid_package_name(package).casefold()
            notes = [
                note for note in notes
                if str(note.get("package", "")).casefold() == wanted
            ]
        return {
            "community_path": str(self.community),
            "count": len(notes),
            "notes": sorted(
                notes,
                key=lambda note: (
                    str(note.get("package", "")).casefold(),
                    str(note.get("created_at", "")),
                    note.get("id", ""),
                ),
            ),
        }
