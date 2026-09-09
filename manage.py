"""AeroGuard 插件管理命令行入口。"""

import argparse
import json
import sys

from management import AddonManager, ManagementError


def _print_json(document):
    print(json.dumps(document, ensure_ascii=False, indent=2))


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="aeroguard-manage",
        description="AeroGuard 插件管理（只操作指定 Community 与管理状态目录）。",
    )
    parser.add_argument("community_path", help="Community 或 Community2024 路径")
    parser.add_argument(
        "--state-dir",
        help="管理状态目录；默认使用 Community 同级的 .aeroguard",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("inventory", help="列出启用、禁用与隔离包")
    commands.add_parser("versions", help="列出当前与已归档版本")

    for command, help_text in (
        ("disable", "禁用一个包"),
        ("enable", "启用一个包"),
        ("restore", "从隔离区恢复一个包"),
    ):
        subparser = commands.add_parser(command, help=help_text)
        subparser.add_argument("package")

    quarantine = commands.add_parser("quarantine", help="把包移入安全隔离区")
    quarantine.add_argument("package")
    quarantine.add_argument("--reason", default="manual quarantine")

    profile_save = commands.add_parser("profile-save", help="保存当前启用状态")
    profile_save.add_argument("name")
    profile_save.add_argument("--replace", action="store_true")
    profile_apply = commands.add_parser("profile-apply", help="应用已保存的 Profile")
    profile_apply.add_argument("name")
    profile_apply.add_argument("--dry-run", action="store_true")

    check = commands.add_parser("check", help="只读检查目录或 ZIP 安装源")
    check.add_argument("source")
    install = commands.add_parser("install", help="检查后安装并保留旧版本")
    install.add_argument("source")
    install.add_argument("--allow-executables", action="store_true")
    rollback = commands.add_parser("rollback", help="回滚一个已提交的安装事务")
    rollback.add_argument("transaction_id")
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = _build_parser().parse_args(argv)
    try:
        manager = AddonManager(args.community_path, args.state_dir)
        if args.command == "inventory":
            result = manager.inventory()
        elif args.command == "versions":
            result = manager.versions()
        elif args.command == "disable":
            result = manager.disable(args.package)
        elif args.command == "enable":
            result = manager.enable(args.package)
        elif args.command == "quarantine":
            result = manager.quarantine(args.package, args.reason)
        elif args.command == "restore":
            result = manager.restore_quarantine(args.package)
        elif args.command == "profile-save":
            result = manager.save_profile(args.name, args.replace)
        elif args.command == "profile-apply":
            result = manager.apply_profile(args.name, args.dry_run)
        elif args.command == "check":
            inspection = manager.inspect_install_source(args.source)
            result = inspection.as_dict()
            _print_json(result)
            return 0 if result["summary"]["ready_for_default_install"] else 2
        elif args.command == "install":
            result = manager.install(args.source, args.allow_executables)
        elif args.command == "rollback":
            result = manager.rollback_install(args.transaction_id)
        else:
            raise AssertionError(f"未处理的命令：{args.command}")
        _print_json(result)
        return 0
    except ManagementError as error:
        print(f"管理操作失败：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
