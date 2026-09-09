"""AeroGuard 的本地插件管理、安装检查与事务回滚。"""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from analyzer import analyze_community_with_stats
from classifier import classify_issues
from noise import apply_noise_rules


EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".com", ".dll", ".exe", ".msi", ".ps1"}
MAX_ZIP_ENTRIES = 500_000
MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024 * 1024
PROFILE_SCHEMA_VERSION = 1
TRANSACTION_SCHEMA_VERSION = 1


class ManagementError(RuntimeError):
    """管理操作因安全校验或当前状态而无法执行。"""


@dataclass
class PreinstallInspection:
    """安装前检查的可序列化结果。"""

    source: str
    packages: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    executable_files: list = field(default_factory=list)

    @property
    def can_install(self):
        return not self.errors and not any(
            issue.get("severity") == "error" for issue in self.issues
        )

    @property
    def requires_executable_override(self):
        return bool(self.executable_files)

    def summary(self):
        return {
            "packages": len(self.packages),
            "issues": len(self.issues),
            "errors": len(self.errors),
            "executable_files": len(self.executable_files),
            "can_install": self.can_install,
            "requires_executable_override": self.requires_executable_override,
            "ready_for_default_install": (
                self.can_install and not self.requires_executable_override
            ),
        }

    def as_dict(self):
        document = asdict(self)
        document["summary"] = self.summary()
        return document


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_transaction_id():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _validate_leaf_name(name, label):
    if not isinstance(name, str):
        raise ManagementError(f"{label}必须是字符串")
    value = name.strip()
    if not value or value in {".", ".."}:
        raise ManagementError(f"{label}不能为空")
    if len(value) > 128:
        raise ManagementError(f"{label}不能超过 128 个字符")
    if any(character in value for character in '<>:"/\\|?*'):
        raise ManagementError(f"{label}包含 Windows 路径非法字符")
    if any(ord(character) < 32 for character in value):
        raise ManagementError(f"{label}包含控制字符")
    if value.endswith((" ", ".")):
        raise ManagementError(f"{label}不能以空格或句点结尾")
    return value


def _read_json_object(path, label):
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            document = json.load(file)
    except (OSError, ValueError, TypeError) as error:
        raise ManagementError(f"{label}无法读取：{error}") from error
    if not isinstance(document, dict):
        raise ManagementError(f"{label}顶层必须是 JSON 对象")
    return document


def _write_json_atomic(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _is_reparse_point(path):
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ManagementError(f"无法检查路径：{path}：{error}") from error
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _reject_reparse_tree(root):
    root = Path(root)
    if _is_reparse_point(root):
        raise ManagementError(f"安装源包含链接或重解析点：{root}")
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories + files:
            candidate = current_path / name
            if _is_reparse_point(candidate):
                raise ManagementError(
                    f"安装源包含链接或重解析点：{candidate}"
                )


def _metadata_fingerprint(package_path):
    digest = hashlib.sha256()
    for filename in ("manifest.json", "layout.json"):
        path = Path(package_path) / filename
        digest.update(filename.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")
    return digest.hexdigest()


def _safe_rmtree(path, allowed_parent):
    path = Path(path).resolve()
    allowed_parent = Path(allowed_parent).resolve()
    if path == allowed_parent or not path.is_relative_to(allowed_parent):
        raise ManagementError(f"拒绝清理非暂存目录：{path}")
    if path.exists():
        shutil.rmtree(path)


def _locate_package_roots(source_root):
    source_root = Path(source_root)

    def immediate_packages(parent):
        return sorted(
            (
                item for item in parent.iterdir()
                if item.is_dir()
                and (item / "manifest.json").is_file()
                and (item / "layout.json").is_file()
            ),
            key=lambda item: item.name.casefold(),
        )

    if (
        (source_root / "manifest.json").is_file()
        and (source_root / "layout.json").is_file()
    ):
        return [source_root]

    packages = immediate_packages(source_root)
    if packages:
        return packages

    directories = [item for item in source_root.iterdir() if item.is_dir()]
    if len(directories) == 1:
        return immediate_packages(directories[0])
    return []


def _validated_zip_members(archive):
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ManagementError(
            f"ZIP 条目过多：{len(infos)}，上限 {MAX_ZIP_ENTRIES}"
        )

    total_size = 0
    members = []
    seen_paths = set()
    for info in infos:
        raw_name = info.filename.replace("\\", "/")
        path = PurePosixPath(raw_name)
        if (
            not raw_name
            or raw_name.startswith("/")
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(":" in part for part in path.parts)
        ):
            raise ManagementError(f"ZIP 包含不安全路径：{info.filename}")
        for part in path.parts:
            if (
                part.endswith((" ", "."))
                or any(character in part for character in '<>"|?*')
                or any(ord(character) < 32 for character in part)
            ):
                raise ManagementError(f"ZIP 包含 Windows 非法路径：{info.filename}")
        if info.flag_bits & 0x1:
            raise ManagementError(f"ZIP 包含加密条目：{info.filename}")
        unix_mode = info.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise ManagementError(f"ZIP 包含符号链接：{info.filename}")
        normalized = "/".join(path.parts).casefold()
        if normalized in seen_paths:
            raise ManagementError(f"ZIP 包含重复路径：{info.filename}")
        seen_paths.add(normalized)
        total_size += info.file_size
        if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ManagementError("ZIP 解压后总大小超过 100 GiB 安全上限")
        members.append((info, path))
    return members


def _safe_extract_zip(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(source) as archive:
            members = _validated_zip_members(archive)
            for info, relative in members:
                target = destination.joinpath(*relative.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as input_file, open(target, "wb") as output:
                    shutil.copyfileobj(input_file, output)
    except zipfile.BadZipFile as error:
        raise ManagementError(f"ZIP 无法解析：{error}") from error


def _prepare_source(source, destination):
    """把目录或 ZIP 中的包复制到 destination，返回包目录列表。"""
    source = Path(source).expanduser()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)

    if source.is_dir():
        _reject_reparse_tree(source)
        package_roots = _locate_package_roots(source)
        if not package_roots:
            raise ManagementError(
                "安装源中未找到同时包含 manifest.json 与 layout.json 的包目录"
            )
        prepared = []
        for package_root in package_roots:
            name = _validate_leaf_name(package_root.name, "包目录名")
            target = destination / name
            shutil.copytree(package_root, target, copy_function=shutil.copy2)
            prepared.append(target)
    elif source.is_file() and source.suffix.casefold() == ".zip":
        extracted = destination / "_extracted"
        _safe_extract_zip(source, extracted)
        package_roots = _locate_package_roots(extracted)
        if not package_roots:
            raise ManagementError(
                "ZIP 中未找到同时包含 manifest.json 与 layout.json 的包目录"
            )
        prepared = []
        package_area = destination / "_packages"
        package_area.mkdir()
        for package_root in package_roots:
            name = _validate_leaf_name(package_root.name, "包目录名")
            target = package_area / name
            shutil.move(str(package_root), str(target))
            prepared.append(target)
    else:
        raise ManagementError("安装源必须是包目录、包集合目录或 ZIP 文件")

    seen = set()
    for package in prepared:
        folded = package.name.casefold()
        if folded in seen:
            raise ManagementError(f"安装源包含重复包目录名：{package.name}")
        seen.add(folded)
    return prepared


def _inspect_prepared(source, package_roots):
    inspection = PreinstallInspection(source=str(source))
    addons = []

    for package_root in package_roots:
        try:
            manifest = _read_json_object(
                package_root / "manifest.json",
                f"{package_root.name}/manifest.json",
            )
            layout = _read_json_object(
                package_root / "layout.json",
                f"{package_root.name}/layout.json",
            )
            if not isinstance(layout.get("content"), list):
                raise ManagementError(
                    f"{package_root.name}/layout.json 的 content 不是列表"
                )
        except ManagementError as error:
            inspection.errors.append({
                "package": package_root.name,
                "error": str(error),
            })
            continue

        record = {
            "folder_name": package_root.name,
            "name": manifest.get("title"),
            "type": manifest.get("content_type"),
            "creator": manifest.get("creator"),
            "version": manifest.get("package_version"),
            "path": str(package_root),
            "manifest": manifest,
        }
        addons.append(record)
        inspection.packages.append({
            key: record[key]
            for key in ("folder_name", "name", "type", "creator", "version")
        })

        for current, _, files in os.walk(package_root):
            current_path = Path(current)
            for filename in files:
                candidate = current_path / filename
                if candidate.suffix.casefold() in EXECUTABLE_SUFFIXES:
                    inspection.executable_files.append({
                        "package": package_root.name,
                        "path": candidate.relative_to(package_root).as_posix(),
                    })

    if addons:
        issues, _ = analyze_community_with_stats(addons, full_scan=True)
        issues = apply_noise_rules(issues, addons)
        inspection.issues = classify_issues(issues)

    return inspection


class AddonManager:
    """只管理指定 Community 根目录，不触碰 Official 或模拟器配置。"""

    def __init__(self, community_path, state_root=None):
        community = Path(community_path).expanduser().resolve()
        if not community.is_dir():
            raise ManagementError(f"Community 路径不存在或不是目录：{community}")
        state = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else (community.parent / ".aeroguard").resolve()
        )
        if state == community or state.is_relative_to(community):
            raise ManagementError("管理状态目录必须位于 Community 目录之外")

        self.community = community
        self.state_root = state
        self.disabled_root = state / "disabled"
        self.quarantine_root = state / "quarantine"
        self.profile_root = state / "profiles"
        self.staging_root = state / "staging"
        self.backup_root = state / "backups"
        self.rolled_back_root = state / "rolled-back"
        self.transaction_root = state / "transactions"

    @staticmethod
    def _find_directory(root, package_name):
        folded = package_name.casefold()
        if not root.is_dir():
            return None
        matches = [
            item for item in root.iterdir()
            if item.is_dir() and item.name.casefold() == folded
        ]
        if len(matches) > 1:
            raise ManagementError(f"发现多个大小写等价的包目录：{package_name}")
        return matches[0] if matches else None

    @staticmethod
    def _package_record(path, status):
        manifest_path = path / "manifest.json"
        try:
            manifest = _read_json_object(manifest_path, str(manifest_path))
            error = None
        except ManagementError as exception:
            manifest = {}
            error = str(exception)
        record = {
            "package": path.name,
            "status": status,
            "title": manifest.get("title"),
            "content_type": manifest.get("content_type"),
            "version": manifest.get("package_version"),
            "path": str(path),
        }
        if error is not None:
            record["error"] = error
        return record

    @staticmethod
    def _declared_dependencies(package_path):
        try:
            manifest = _read_json_object(
                package_path / "manifest.json", str(package_path / "manifest.json")
            )
        except ManagementError:
            return set()
        dependencies = manifest.get("dependencies", [])
        if not isinstance(dependencies, list):
            return set()
        return {
            item["name"].strip().casefold()
            for item in dependencies
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item["name"].strip()
        }

    def _dependent_warnings(self, removed_packages, remaining_paths=None):
        removed = {name.casefold() for name in removed_packages}
        if remaining_paths is None:
            remaining_paths = [
                item for item in self.community.iterdir()
                if item.is_dir() and item.name.casefold() not in removed
            ]
        warnings = []
        for package_path in remaining_paths:
            matched = sorted(
                self._declared_dependencies(package_path) & removed
            )
            for dependency in matched:
                warnings.append({
                    "package": package_path.name,
                    "dependency": dependency,
                    "warning": "启用包声明依赖即将离开 Community 的包",
                })
        return warnings

    def _list_location(self, root, status):
        if not root.is_dir():
            return []
        return [
            self._package_record(item, status)
            for item in sorted(root.iterdir(), key=lambda value: value.name.casefold())
            if item.is_dir()
        ]

    def inventory(self):
        active = self._list_location(self.community, "enabled")
        disabled = self._list_location(self.disabled_root, "disabled")
        quarantined = self._list_location(self.quarantine_root, "quarantined")
        locations = {}
        for record in active + disabled + quarantined:
            locations.setdefault(record["package"].casefold(), []).append(
                record["status"]
            )
        conflicts = [
            {"package": name, "locations": statuses}
            for name, statuses in sorted(locations.items())
            if len(statuses) > 1
        ]
        return {
            "community_path": str(self.community),
            "state_root": str(self.state_root),
            "summary": {
                "enabled": len(active),
                "disabled": len(disabled),
                "quarantined": len(quarantined),
                "invalid_entries": sum(
                    "error" in record
                    for record in active + disabled + quarantined
                ),
                "location_conflicts": len(conflicts),
            },
            "enabled": active,
            "disabled": disabled,
            "quarantined": quarantined,
            "location_conflicts": conflicts,
        }

    def _move_atomic(self, source, destination):
        if destination.exists():
            raise ManagementError(f"目标已存在，拒绝覆盖：{destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.replace(destination)
        except OSError as error:
            raise ManagementError(
                "包目录移动失败；状态目录应与 Community 位于同一磁盘："
                f"{error}"
            ) from error

    def _transaction_path(self, transaction_id):
        safe_id = _validate_leaf_name(transaction_id, "事务 ID")
        return self.transaction_root / f"{safe_id}.json"

    def _save_transaction(self, document):
        _write_json_atomic(self._transaction_path(document["id"]), document)

    def _simple_move(self, package_name, source_root, destination_root, kind):
        package_name = _validate_leaf_name(package_name, "包名")
        source = self._find_directory(source_root, package_name)
        if source is None:
            raise ManagementError(f"未找到包：{package_name}")
        collision = self._find_directory(destination_root, package_name)
        if collision is not None:
            raise ManagementError(f"目标位置已有同名包：{collision}")
        destination = destination_root / source.name
        dependency_warnings = (
            self._dependent_warnings({source.name}) if kind == "disable" else []
        )
        transaction = {
            "schema_version": TRANSACTION_SCHEMA_VERSION,
            "id": _new_transaction_id(),
            "kind": kind,
            "status": "committed",
            "created_at": _now_utc(),
            "community_path": str(self.community),
            "operations": [{
                "package": source.name,
                "source": str(source),
                "destination": str(destination),
            }],
            "dependency_warnings": dependency_warnings,
            "restart_required": True,
        }
        self._move_atomic(source, destination)
        try:
            self._save_transaction(transaction)
        except Exception:
            destination.replace(source)
            raise
        return transaction

    def disable(self, package_name):
        return self._simple_move(
            package_name, self.community, self.disabled_root, "disable"
        )

    def enable(self, package_name):
        return self._simple_move(
            package_name, self.disabled_root, self.community, "enable"
        )

    def quarantine(self, package_name, reason="manual quarantine"):
        package_name = _validate_leaf_name(package_name, "包名")
        source = self._find_directory(self.community, package_name)
        previous_status = "enabled"
        if source is None:
            source = self._find_directory(self.disabled_root, package_name)
            previous_status = "disabled"
        if source is None:
            raise ManagementError(f"未找到可隔离的包：{package_name}")
        if self._find_directory(self.quarantine_root, package_name) is not None:
            raise ManagementError(f"隔离区已有同名包：{package_name}")

        destination = self.quarantine_root / source.name
        metadata_path = self.quarantine_root / f"{source.name}.json"
        if metadata_path.exists():
            raise ManagementError(f"隔离记录已存在：{metadata_path}")
        metadata = {
            "schema_version": 1,
            "package": source.name,
            "quarantined_at": _now_utc(),
            "previous_status": previous_status,
            "reason": str(reason),
        }
        transaction = {
            "schema_version": TRANSACTION_SCHEMA_VERSION,
            "id": _new_transaction_id(),
            "kind": "quarantine",
            "status": "committed",
            "created_at": _now_utc(),
            "community_path": str(self.community),
            "operations": [{
                "package": source.name,
                "source": str(source),
                "destination": str(destination),
            }],
            "dependency_warnings": (
                self._dependent_warnings({source.name})
                if previous_status == "enabled" else []
            ),
            "restart_required": True,
        }
        self._move_atomic(source, destination)
        try:
            _write_json_atomic(metadata_path, metadata)
            self._save_transaction(transaction)
        except Exception:
            if metadata_path.exists():
                metadata_path.unlink()
            destination.replace(source)
            raise
        return transaction

    def restore_quarantine(self, package_name):
        package_name = _validate_leaf_name(package_name, "包名")
        source = self._find_directory(self.quarantine_root, package_name)
        if source is None:
            raise ManagementError(f"隔离区未找到包：{package_name}")
        metadata_path = self.quarantine_root / f"{source.name}.json"
        metadata = _read_json_object(metadata_path, "隔离记录")
        previous_status = metadata.get("previous_status")
        if previous_status not in {"enabled", "disabled"}:
            raise ManagementError("隔离记录中的 previous_status 无效")
        destination_root = (
            self.community if previous_status == "enabled" else self.disabled_root
        )
        if self._find_directory(destination_root, source.name) is not None:
            raise ManagementError(f"恢复位置已有同名包：{source.name}")
        destination = destination_root / source.name
        transaction = {
            "schema_version": TRANSACTION_SCHEMA_VERSION,
            "id": _new_transaction_id(),
            "kind": "restore_quarantine",
            "status": "committed",
            "created_at": _now_utc(),
            "community_path": str(self.community),
            "operations": [{
                "package": source.name,
                "source": str(source),
                "destination": str(destination),
            }],
            "restart_required": True,
        }
        self._move_atomic(source, destination)
        try:
            metadata_path.unlink()
            self._save_transaction(transaction)
        except Exception:
            destination.replace(source)
            if not metadata_path.exists():
                _write_json_atomic(metadata_path, metadata)
            raise
        return transaction

    def _profile_path(self, profile_name):
        safe_name = _validate_leaf_name(profile_name, "Profile 名称")
        return self.profile_root / f"{safe_name}.json"

    def save_profile(self, profile_name, replace=False):
        inventory = self.inventory()
        if inventory["location_conflicts"]:
            raise ManagementError("存在跨位置同名包，无法保存确定性 Profile")
        packages = {}
        skipped_entries = []
        for status in ("enabled", "disabled"):
            for record in inventory[status]:
                if "error" in record:
                    skipped_entries.append({
                        "package": record["package"],
                        "status": status,
                        "error": record["error"],
                    })
                    continue
                packages[record["package"]] = {
                    "enabled": status == "enabled",
                    "version": record["version"],
                }
        document = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "name": _validate_leaf_name(profile_name, "Profile 名称"),
            "created_at": _now_utc(),
            "community_path": str(self.community),
            "packages": packages,
            "skipped_entries": skipped_entries,
        }
        path = self._profile_path(profile_name)
        if path.exists() and not replace:
            raise ManagementError(
                f"Profile 已存在：{path}；使用 --replace 显式更新"
            )
        _write_json_atomic(path, document)
        return {"profile_path": str(path), **document}

    def apply_profile(self, profile_name, dry_run=False):
        profile = _read_json_object(self._profile_path(profile_name), "Profile")
        package_states = profile.get("packages")
        if not isinstance(package_states, dict):
            raise ManagementError("Profile packages 必须是 JSON 对象")

        moves = []
        warnings = []
        for package_name, state in package_states.items():
            package_name = _validate_leaf_name(package_name, "Profile 包名")
            if not isinstance(state, dict) or not isinstance(
                state.get("enabled"), bool
            ):
                raise ManagementError(f"Profile 中 {package_name} 的状态无效")
            active = self._find_directory(self.community, package_name)
            disabled = self._find_directory(self.disabled_root, package_name)
            if active is not None and disabled is not None:
                raise ManagementError(f"包同时存在于启用和禁用位置：{package_name}")
            if active is None and disabled is None:
                warnings.append({
                    "package": package_name,
                    "warning": "Profile 中的包当前未安装",
                })
                continue
            desired_enabled = state["enabled"]
            if desired_enabled and disabled is not None:
                moves.append((disabled, self.community / disabled.name))
            elif not desired_enabled and active is not None:
                moves.append((active, self.disabled_root / active.name))

        for _, destination in moves:
            if destination.exists():
                raise ManagementError(f"Profile 目标已存在：{destination}")

        plan = {
            "profile": profile.get("name", profile_name),
            "dry_run": bool(dry_run),
            "moves": [
                {
                    "package": source.name,
                    "source": str(source),
                    "destination": str(destination),
                }
                for source, destination in moves
            ],
            "warnings": warnings,
            "restart_required": bool(moves),
        }
        disabled_names = {
            source.name
            for source, destination in moves
            if destination.parent == self.disabled_root
        }
        enabled_sources = {
            source.name.casefold(): source
            for source, destination in moves
            if destination.parent == self.community
        }
        remaining_paths = [
            item for item in self.community.iterdir()
            if item.is_dir() and item.name.casefold() not in {
                name.casefold() for name in disabled_names
            }
        ]
        remaining_paths.extend(enabled_sources.values())
        dependency_warnings = self._dependent_warnings(
            disabled_names, remaining_paths
        )
        plan["dependency_warnings"] = dependency_warnings
        if dry_run or not moves:
            return plan

        transaction = {
            "schema_version": TRANSACTION_SCHEMA_VERSION,
            "id": _new_transaction_id(),
            "kind": "apply_profile",
            "status": "committed",
            "created_at": _now_utc(),
            "community_path": str(self.community),
            "profile": profile.get("name", profile_name),
            "operations": plan["moves"],
            "warnings": warnings,
            "dependency_warnings": dependency_warnings,
            "restart_required": True,
        }
        completed = []
        try:
            for source, destination in moves:
                self._move_atomic(source, destination)
                completed.append((source, destination))
            self._save_transaction(transaction)
        except Exception:
            for source, destination in reversed(completed):
                if destination.exists() and not source.exists():
                    destination.replace(source)
            raise
        return transaction

    def inspect_install_source(self, source):
        source = Path(source).expanduser()
        try:
            with tempfile.TemporaryDirectory(prefix="aeroguard-check-") as temporary:
                prepared = _prepare_source(source, Path(temporary) / "packages")
                return _inspect_prepared(source, prepared)
        except ManagementError as error:
            return PreinstallInspection(
                source=str(source),
                errors=[{"package": None, "error": str(error)}],
            )

    def install(self, source, allow_executables=False):
        source = Path(source).expanduser()
        transaction_id = _new_transaction_id()
        stage = self.staging_root / transaction_id
        stage.parent.mkdir(parents=True, exist_ok=True)
        try:
            prepared = _prepare_source(source, stage)
            inspection = _inspect_prepared(source, prepared)
            if not inspection.can_install:
                raise ManagementError("安装前检查未通过，未修改 Community")
            if inspection.executable_files and not allow_executables:
                raise ManagementError(
                    "安装源包含可执行文件；复核检查结果后使用 "
                    "--allow-executables 显式接受"
                )

            planned = []
            for package_root in prepared:
                name = package_root.name
                if self._find_directory(self.disabled_root, name) is not None:
                    raise ManagementError(f"禁用区已有同名包：{name}")
                if self._find_directory(self.quarantine_root, name) is not None:
                    raise ManagementError(f"隔离区已有同名包：{name}")
                existing = self._find_directory(self.community, name)
                destination = self.community / name
                if existing is None and destination.exists():
                    raise ManagementError(f"Community 中已有同名非目录项：{destination}")
                backup = (
                    self.backup_root / transaction_id / existing.name
                    if existing is not None else None
                )
                planned.append({
                    "package": name,
                    "staged": package_root,
                    "destination": destination,
                    "existing": existing,
                    "backup": backup,
                })

            transaction = {
                "schema_version": TRANSACTION_SCHEMA_VERSION,
                "id": transaction_id,
                "kind": "install",
                "status": "pending",
                "created_at": _now_utc(),
                "community_path": str(self.community),
                "source": str(source),
                "inspection_summary": inspection.summary(),
                "packages": [],
                "restart_required": True,
            }
            for item in planned:
                previous_manifest = {}
                if item["existing"] is not None:
                    try:
                        previous_manifest = _read_json_object(
                            item["existing"] / "manifest.json",
                            "原版本 manifest",
                        )
                    except ManagementError:
                        pass
                new_manifest = _read_json_object(
                    item["staged"] / "manifest.json", "新版本 manifest"
                )
                transaction["packages"].append({
                    "package": item["package"],
                    "destination": str(item["destination"]),
                    "backup": str(item["backup"]) if item["backup"] else None,
                    "previous_version": previous_manifest.get("package_version"),
                    "installed_version": new_manifest.get("package_version"),
                    "installed_metadata_fingerprint": _metadata_fingerprint(
                        item["staged"]
                    ),
                })
            self._save_transaction(transaction)

            backed_up = []
            installed = []
            try:
                for item in planned:
                    if item["existing"] is not None:
                        self._move_atomic(item["existing"], item["backup"])
                        backed_up.append(item)
                for item in planned:
                    self._move_atomic(item["staged"], item["destination"])
                    installed.append(item)
                transaction["status"] = "committed"
                transaction["committed_at"] = _now_utc()
                self._save_transaction(transaction)
            except Exception:
                for item in reversed(installed):
                    if item["destination"].exists() and not item["staged"].exists():
                        item["destination"].replace(item["staged"])
                for item in reversed(backed_up):
                    if item["backup"].exists() and not item["existing"].exists():
                        item["backup"].replace(item["existing"])
                transaction["status"] = "failed_rolled_back"
                transaction["failed_at"] = _now_utc()
                self._save_transaction(transaction)
                raise

            return {
                "transaction": transaction,
                "inspection": inspection.as_dict(),
            }
        except Exception:
            if stage.exists():
                _safe_rmtree(stage, self.staging_root)
            raise
        finally:
            if stage.exists():
                _safe_rmtree(stage, self.staging_root)

    def rollback_install(self, transaction_id):
        transaction_path = self._transaction_path(transaction_id)
        transaction = _read_json_object(transaction_path, "安装事务")
        if transaction.get("kind") != "install":
            raise ManagementError("指定事务不是安装事务")
        if transaction.get("status") != "committed":
            raise ManagementError(
                f"安装事务当前状态不可回滚：{transaction.get('status')}"
            )
        if Path(transaction.get("community_path", "")).resolve() != self.community:
            raise ManagementError("安装事务属于另一个 Community 路径")

        packages = transaction.get("packages")
        if not isinstance(packages, list) or not packages:
            raise ManagementError("安装事务没有可回滚的包")

        plan = []
        rollback_root = self.rolled_back_root / transaction["id"]
        for package in packages:
            name = _validate_leaf_name(package.get("package"), "事务包名")
            active = self._find_directory(self.community, name)
            if active is None:
                raise ManagementError(f"当前 Community 中未找到已安装包：{name}")
            expected = package.get("installed_metadata_fingerprint")
            if _metadata_fingerprint(active) != expected:
                raise ManagementError(
                    f"包 {name} 的 manifest/layout 在安装后已变化，拒绝覆盖"
                )
            backup = Path(package["backup"]).resolve() if package.get("backup") else None
            expected_backup_root = (self.backup_root / transaction["id"]).resolve()
            if backup is not None and (
                backup.parent != expected_backup_root
                or backup.name.casefold() != name.casefold()
            ):
                raise ManagementError(f"安装事务中的备份路径无效：{backup}")
            if backup is not None and not backup.is_dir():
                raise ManagementError(f"原版本备份不存在：{backup}")
            rollback_destination = rollback_root / active.name
            if rollback_destination.exists():
                raise ManagementError(f"回滚保留目录已存在：{rollback_destination}")
            plan.append((active, backup, rollback_destination))

        moved_current = []
        restored_backup = []
        try:
            for active, _, rollback_destination in plan:
                self._move_atomic(active, rollback_destination)
                moved_current.append((active, rollback_destination))
            for active, backup, _ in plan:
                if backup is not None:
                    self._move_atomic(backup, active)
                    restored_backup.append((active, backup))
            transaction["status"] = "rolled_back"
            transaction["rolled_back_at"] = _now_utc()
            transaction["rolled_back_packages"] = [
                str(item[2]) for item in plan
            ]
            self._save_transaction(transaction)
        except Exception:
            for active, backup in reversed(restored_backup):
                if active.exists() and not backup.exists():
                    active.replace(backup)
            for active, rollback_destination in reversed(moved_current):
                if rollback_destination.exists() and not active.exists():
                    rollback_destination.replace(active)
            raise
        return transaction

    def versions(self):
        inventory = self.inventory()
        current = (
            inventory["enabled"]
            + inventory["disabled"]
            + inventory["quarantined"]
        )
        archived = []
        for root, status in (
            (self.backup_root, "backup"),
            (self.rolled_back_root, "rolled_back"),
        ):
            if not root.is_dir():
                continue
            for transaction_dir in sorted(root.iterdir()):
                if not transaction_dir.is_dir():
                    continue
                for package_dir in sorted(transaction_dir.iterdir()):
                    if package_dir.is_dir() and (
                        package_dir / "manifest.json"
                    ).exists():
                        record = self._package_record(package_dir, status)
                        record["transaction_id"] = transaction_dir.name
                        archived.append(record)
        return {
            "summary": {
                "current_versions": len(current),
                "archived_versions": len(archived),
            },
            "current": current,
            "archived": archived,
        }
