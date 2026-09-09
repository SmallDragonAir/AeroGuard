"""基于可复核证据降低已知高置信度扫描噪音。"""

from pathlib import Path, PurePosixPath


SIZE_MISMATCH_RULE = "LAYOUT_FILE_SIZE_MISMATCH"
LINE_ENDING_RULE = "TEXT_LINE_ENDING_NORMALIZATION"
MIN_MISMATCHES_FOR_SAMPLING = 20
MAX_SAMPLES = 64
MAX_SAMPLE_BYTES = 1024 * 1024


def _group_key(detail):
    """按顶层目录与扩展名分组，让样本覆盖不同内容区域。"""
    path = PurePosixPath(str(detail.get("path", "")).replace("\\", "/"))
    top = path.parts[0].casefold() if path.parts else ""
    return top, path.suffix.casefold()


def _representative_sample(details):
    """确定性选择分层样本；分组过多时保守地放弃自动降级。"""
    if len(details) <= MAX_SAMPLES:
        return list(details)

    representatives = {}
    for detail in details:
        representatives.setdefault(_group_key(detail), detail)

    if len(representatives) > MAX_SAMPLES:
        return []

    selected = list(representatives.values())
    selected_ids = {id(detail) for detail in selected}
    remaining = MAX_SAMPLES - len(selected)

    if remaining > 0:
        last_index = len(details) - 1
        for slot in range(remaining):
            index = round(slot * last_index / max(remaining - 1, 1))
            detail = details[index]
            if id(detail) not in selected_ids:
                selected.append(detail)
                selected_ids.add(id(detail))

    # 分层代表与等距位置可能重合；继续补足样本，避免无谓降低证据量。
    if len(selected) < MAX_SAMPLES:
        for detail in details:
            if id(detail) in selected_ids:
                continue
            selected.append(detail)
            selected_ids.add(id(detail))
            if len(selected) == MAX_SAMPLES:
                break

    return selected[:MAX_SAMPLES]


def _safe_file_path(package_root, relative_path):
    normalized = str(relative_path).replace("\\", "/")
    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute() or ".." in pure_path.parts:
        return None
    if pure_path.parts and ":" in pure_path.parts[0]:
        return None

    return package_root.joinpath(*pure_path.parts)


def _matches_crlf_to_lf_normalization(package_root, detail):
    """检查大小差是否恰好等于文件中仍为 LF 的换行数量。"""
    expected = detail.get("expected")
    actual = detail.get("actual")
    relative_path = detail.get("path")

    if (
        not isinstance(expected, int)
        or not isinstance(actual, int)
        or not isinstance(relative_path, str)
        or expected <= actual
        or actual > MAX_SAMPLE_BYTES
    ):
        return False

    file_path = _safe_file_path(package_root, relative_path)
    if file_path is None:
        return False

    try:
        data = file_path.read_bytes()
    except OSError:
        return False

    if len(data) != actual or b"\0" in data:
        return False

    bare_lf_count = data.count(b"\n") - data.count(b"\r\n")
    return bare_lf_count > 0 and expected - actual == bare_lf_count


def apply_noise_rules(issues, addons):
    """
    对大批量大小差异做有限、分层的内容抽样。

    只有所有代表样本都精确符合 CRLF -> LF 的大小变化时，才把该
    issue 从 warning 降为 info。完整明细仍保留，并记录原等级与证据。
    """
    package_roots = {
        addon["folder_name"]: Path(addon["path"])
        for addon in addons
    }

    for issue in issues:
        if issue.get("rule_id") != SIZE_MISMATCH_RULE:
            continue

        details = issue.get("details", [])
        if len(details) < MIN_MISMATCHES_FOR_SAMPLING:
            continue

        package_root = package_roots.get(issue.get("package"))
        if package_root is None:
            continue

        sample = _representative_sample(details)
        if not sample:
            continue

        if not all(
            _matches_crlf_to_lf_normalization(package_root, detail)
            for detail in sample
        ):
            continue

        issue["original_severity"] = issue["severity"]
        issue["severity"] = "info"
        issue["downgrade_rule"] = LINE_ENDING_RULE
        issue["downgrade_reason"] = (
            "代表样本的大小差均精确符合 CRLF 转 LF 的换行规范化特征"
        )
        issue["downgrade_evidence"] = {
            "sampled_files": len(sample),
            "total_files": len(details),
        }

    return issues
