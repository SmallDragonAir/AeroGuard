"""AeroGuard 插件管理命令行入口。"""

import argparse
import json
import sys

from i18n import localize_text, tr
from management import AddonManager, ManagementError
from notes import NoteStore, NoteStoreError
from overrides import OverrideStore, OverrideStoreError


def _print_json(document):
    print(json.dumps(document, ensure_ascii=False, indent=2))


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="aeroguard-manage",
        description=tr("help.manage.description"),
    )
    parser.add_argument("community_path", help=tr("help.manage.community"))
    parser.add_argument(
        "--state-dir",
        help=tr("help.manage.state_dir"),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("inventory", help=tr("help.manage.inventory"))
    commands.add_parser("versions", help=tr("help.manage.versions"))

    for command, help_key in (
        ("disable", "help.manage.disable"),
        ("enable", "help.manage.enable"),
        ("restore", "help.manage.restore"),
    ):
        subparser = commands.add_parser(command, help=tr(help_key))
        subparser.add_argument("package")

    quarantine = commands.add_parser(
        "quarantine", help=tr("help.manage.quarantine")
    )
    quarantine.add_argument("package")
    quarantine.add_argument("--reason", default="manual quarantine")

    profile_save = commands.add_parser(
        "profile-save", help=tr("help.manage.profile_save")
    )
    profile_save.add_argument("name")
    profile_save.add_argument("--replace", action="store_true")
    profile_apply = commands.add_parser(
        "profile-apply", help=tr("help.manage.profile_apply")
    )
    profile_apply.add_argument("name")
    profile_apply.add_argument("--dry-run", action="store_true")

    check = commands.add_parser("check", help=tr("help.manage.check"))
    check.add_argument("source")
    install = commands.add_parser("install", help=tr("help.manage.install"))
    install.add_argument("source")
    install.add_argument("--allow-executables", action="store_true")
    rollback = commands.add_parser(
        "rollback", help=tr("help.manage.rollback")
    )
    rollback.add_argument("transaction_id")

    note_list = commands.add_parser(
        "note-list", help=tr("help.manage.note_list")
    )
    note_list.add_argument("package", nargs="?")
    note_add = commands.add_parser(
        "note-add", help=tr("help.manage.note_add")
    )
    note_add.add_argument("package")
    note_add.add_argument("--text", required=True,
                          help=tr("help.manage.note_text"))
    note_add.add_argument("--rule", help=tr("help.manage.note_rule"))
    note_remove = commands.add_parser(
        "note-remove", help=tr("help.manage.note_remove")
    )
    note_remove.add_argument("note_id")

    override_list = commands.add_parser(
        "override-list", help=tr("help.manage.override_list")
    )
    override_list.add_argument("package", nargs="?")
    override_list.add_argument("--rule")
    override_add = commands.add_parser(
        "override-add", help=tr("help.manage.override_add")
    )
    override_add.add_argument("package")
    override_add.add_argument("--rule", required=True,
                              help=tr("help.manage.override_rule"))
    override_add.add_argument(
        "--action", required=True, choices=("ignore", "downgrade")
    )
    override_add.add_argument("--reason")
    override_remove = commands.add_parser(
        "override-remove", help=tr("help.manage.override_remove")
    )
    override_remove.add_argument("override_id")
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = _build_parser().parse_args(argv)
    try:
        if args.command in {"note-list", "note-add", "note-remove"}:
            note_store = NoteStore(args.community_path, args.state_dir)
            if args.command == "note-list":
                result = note_store.list(args.package)
            elif args.command == "note-add":
                result = note_store.add(args.package, args.text, args.rule)
            else:
                result = note_store.remove(args.note_id)
            _print_json(result)
            return 0

        if args.command in {"override-list", "override-add", "override-remove"}:
            override_store = OverrideStore(args.community_path, args.state_dir)
            if args.command == "override-list":
                result = override_store.list(args.package, args.rule)
            elif args.command == "override-add":
                result = override_store.add(
                    args.package, args.rule, args.action, args.reason
                )
            else:
                result = override_store.remove(args.override_id)
            _print_json(result)
            return 0

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
    except (ManagementError, NoteStoreError, OverrideStoreError) as error:
        print(
            tr("cli.manage_failed", error=localize_text(str(error))),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
