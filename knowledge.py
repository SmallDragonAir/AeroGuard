"""扫描结果的知识上下文：匹配本地已知结论（notes）并应用规则覆盖。

只做两件事：
- 把与 issue 匹配的 notes 附到 issue["notes"]（包匹配，可选规则匹配合并）；
- 按 overrides 应用 ignore（移除）或 downgrade（severity 降为 info 并附
  override 信息）。

保持纯确定性，不联网；notes/overrides 的读写仍由对应 Store 负责。
"""

from collections import defaultdict


def _notes_by_package(notes):
    grouped = defaultdict(list)
    for note in notes:
        grouped[str(note.get("package", "")).casefold()].append(note)
    return grouped


def _overrides_by_package(overrides):
    grouped = defaultdict(list)
    for record in overrides:
        grouped[str(record.get("package", "")).casefold()].append(record)
    return grouped


def apply_known_context(issues, addons, *, note_store=None, override_store=None):
    """
    返回处理后的 issue 列表（可能移除被 ignore 的条目）。

    - note_store / override_store 均可选；为 None 时跳过对应步骤。
    - 依赖 stores 的 list() 返回 {"notes": [...]} / {"overrides": [...]}。
    """
    notes = []
    if note_store is not None:
        notes = note_store.list().get("notes", [])

    overrides = []
    if override_store is not None:
        overrides = override_store.list().get("overrides", [])

    notes_by_package = _notes_by_package(notes)
    overrides_by_package = _overrides_by_package(overrides)

    kept = []
    for issue in issues:
        package_key = str(issue.get("package", "")).casefold()
        rule_id = str(issue.get("rule_id", ""))

        # === 附上匹配的 notes（包匹配，可选规则匹配） ===
        matched_notes = [
            {
                "id": note.get("id"),
                "text": note.get("text"),
                "rule_id": note.get("rule_id"),
            }
            for note in notes_by_package.get(package_key, [])
            if not note.get("rule_id") or note.get("rule_id") == rule_id
        ]
        if matched_notes:
            issue["notes"] = matched_notes

        # === 应用规则覆盖（ignore / downgrade） ===
        matched_override = None
        for record in overrides_by_package.get(package_key, []):
            if str(record.get("rule_id", "")).upper() == rule_id.upper():
                matched_override = record
                break

        if matched_override is not None:
            action = str(matched_override.get("action", "")).lower()
            if action == "ignore":
                continue
            if action == "downgrade":
                issue["severity"] = "info"
                issue["override"] = {
                    "action": "downgrade",
                    "reason": matched_override.get("reason"),
                    "override_id": matched_override.get("id"),
                }

        kept.append(issue)

    return kept
